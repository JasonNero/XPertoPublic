#
# Copyright (c) 2025, Jason Schuehlein
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import BotInterruptionFrame, LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.llm_service import LLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.local.audio import LocalAudioTransport
from pipecat_tail.runner import TailRunner

from ..config import APIKeysConfig, AppConfig
from ..utils.audiobuffer_handler import AudioBufferHandler
from ..utils.context_manager import ConversationContextManager
from ..utils.context_saver import ContextSaverProcessor
from ..utils.transcript_handler import TranscriptHandler
from ..utils.wake_check_buffer import WakeCheckBuffer
from ..utils.function_calling import web_fetch, web_fetch_schema, web_search, web_search_schema

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class SimpleBot:
    def __init__(
        self,
        config: AppConfig,
        api_keys: APIKeysConfig,
        resume_session_id: Optional[str] = None,
    ):
        self.config = config
        self.api_keys = api_keys
        self.resume_session_id = resume_session_id

        self.context: Optional[OpenAILLMContext] = None
        self.context_aggregator = None
        self.task: Optional[PipelineTask] = None
        self.transcript_handler: Optional[TranscriptHandler] = None
        self.context_manager = ConversationContextManager(self.config.paths.contexts)
        self.context_saver: Optional[ContextSaverProcessor] = None
        self.session_id: Optional[str] = None
        self.session_metadata: Optional[dict] = None

    async def run(self, transport: BaseTransport) -> None:
        audiobuffer = AudioBufferProcessor()
        audiobuffer_handler = AudioBufferHandler(
            output_folder=Path(self.config.paths.recordings),
            output_name=Path(__file__).stem,
        )

        stt = self._create_stt_service()
        tts = self._create_tts_service()
        llm = self._create_llm_service()

        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            if self.config.bot.language == "DE":
                phrase = "Einen Moment bitte, ich schaue das mal nach."
            else:
                phrase = "One moment please, let me look that up."
            await tts.queue_frame(TTSSpeakFrame(phrase))

        # Load existing context or create new one
        if self.resume_session_id:
            try:
                self.context, self.session_metadata = self.context_manager.load_context(
                    self.resume_session_id
                )
                self.session_id = self.session_metadata["session_id"]
                logger.info(f"Resumed session: {self.session_id}")
            except Exception as e:
                logger.error(f"Failed to resume session {self.resume_session_id}: {e}")
                logger.info("Starting new session instead")
                self.context = OpenAILLMContext()
                self.session_id = self.context_manager.generate_session_id()
        else:
            self.context = OpenAILLMContext()
            self.session_id = self.context_manager.generate_session_id()

        standard_tools = []
        for tool in self.config.services.llm.tools:
            match tool:
                case "web_search":
                    llm.register_function("web_search", web_search, cancel_on_interruption=True)
                    standard_tools.append(web_search_schema)
                case "web_fetch":
                    llm.register_function("web_fetch", web_fetch, cancel_on_interruption=True)
                    standard_tools.append(web_fetch_schema)

        tools = ToolsSchema(standard_tools=standard_tools)
        self.context.set_tools(tools)
        self.context_aggregator = llm.create_context_aggregator(self.context)

        # Create context saver processor
        self.context_saver = ContextSaverProcessor(
            context=self.context,
            context_manager=self.context_manager,
            session_id=self.session_id,
            config_name=self.config.config_name,
            save_interval=60.0,  # Save every minute
        )

        wake_check = WakeCheckBuffer(
            wake_phrases=self.config.bot.assistant_names,
            keepalive_timeout_secs=self.config.bot.keepalive_timeout_secs,
        )

        transcript = TranscriptProcessor()
        self.transcript_handler = TranscriptHandler(
            output_folder=Path(self.config.paths.transcripts),
            output_name=Path(__file__).stem,
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                transcript.user(),
                wake_check,
                self.context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                # TODO: Expose audio recording via config instead of commenting out.
                # audiobuffer,
                transcript.assistant(),
                self.context_aggregator.assistant(),
                self.context_saver,
            ]
        )

        self.task = PipelineTask(
            pipeline,
            idle_timeout_secs=self.config.bot.idle_timeout_secs,
            cancel_on_idle_timeout=True,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
                report_only_initial_ttfb=True,
            ),
        )

        audiobuffer.add_event_handler(
            "on_audio_data", audiobuffer_handler.on_audio_data
        )
        audiobuffer.add_event_handler(
            "on_track_audio_data", audiobuffer_handler.on_track_audio_data
        )

        @transcript.event_handler("on_transcript_update")
        async def on_transcript_update(processor, frame):
            await self.transcript_handler.on_transcript_update(processor, frame)

        @transport.event_handler("on_participant_joined")
        async def on_participant_joined(transport, participant):
            await self._handle_participant_joined(participant)

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            await self._handle_participant_left(participant)

        if isinstance(transport, LocalAudioTransport):
            await on_participant_joined(transport, {"id": "0"})

        runner = TailRunner()
        await runner.run(self.task)

    def _create_stt_service(self) -> STTService:
        match self.config.services.stt.provider:
            case "deepgram":
                from pipecat.services.deepgram.stt import (
                    DeepgramSTTService,
                    LiveOptions,
                )

                return DeepgramSTTService(
                    api_key=self.api_keys.deepgram_api_key,
                    audio_passthrough=True,
                    live_options=LiveOptions(
                        language=self.config.bot.language,
                        model=self.config.services.stt.model,
                        diarize=True,
                    ),
                )
            case "speechmatics":
                from pipecat.services.speechmatics.stt import SpeechmaticsSTTService

                return SpeechmaticsSTTService(
                    api_key=self.api_keys.speechmatics_api_key,
                    params=SpeechmaticsSTTService.InputParams(
                        language=self.config.bot.language.lower(),
                        enable_diarization=True,
                        end_of_utterance_silence_trigger=0.5,
                        speaker_active_format="<{speaker_id}>{text}</{speaker_id}>",
                        speaker_passive_format="<PASSIVE><{speaker_id}>{text}</{speaker_id}></PASSIVE>",
                    ),
                )
            case _:
                raise ValueError(
                    f"Unsupported STT provider: {self.config.services.stt.provider}"
                )

    def _create_tts_service(self) -> TTSService:
        match self.config.services.tts.provider:
            case "elevenlabs":
                from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

                return ElevenLabsTTSService(
                    api_key=self.api_keys.elevenlabs_api_key,
                    voice_id=self.config.services.tts.voice,
                    model=self.config.services.tts.model,
                    params=ElevenLabsTTSService.InputParams(
                        language=self.config.bot.language.lower(),
                    ),
                )
            case "deepgram":
                from pipecat.services.deepgram.tts import DeepgramTTSService

                return DeepgramTTSService(
                    api_key=self.api_keys.deepgram_api_key,
                    voice=self.config.services.tts.voice,
                )
            case _:
                raise ValueError(
                    f"Unsupported TTS provider: {self.config.services.tts.provider}"
                )

    def _create_llm_service(self) -> LLMService:
        match self.config.services.llm.provider:
            case "openai":
                return OpenAILLMService(
                    api_key=self.api_keys.openai_api_key,
                    model=self.config.services.llm.model,
                )
            case _:
                raise ValueError(
                    f"Unsupported LLM provider: {self.config.services.llm.provider}"
                )

    async def _handle_participant_joined(self, participant):
        """Reset the context and send startup message (unless resuming)"""
        logger.info(f"Participant {participant} joined the call.")
        await self.transcript_handler.handle_participant_joined(participant["id"])

        # Only reset context if we're not resuming an existing session
        if not self.resume_session_id or not self.session_metadata:
            logger.info("Starting new session, resetting context")
            await self.context_aggregator.user().reset()
            await self.context_aggregator.assistant().reset()
            self.context.messages.clear()

            self.context.messages.extend(
                [
                    {
                        "role": "system",
                        "content": self.config.load_persona_prompt(),
                    },
                    {
                        "role": "system",
                        "content": self.config.load_intro_prompt(),
                    },
                ]
            )
        else:
            logger.info(
                f"Resuming session with {len(self.context.messages)} existing messages"
            )

        await self.task.queue_frames([LLMRunFrame()])

    async def _handle_participant_left(self, participant):
        """Stop all processing."""
        await self.transcript_handler.handle_participant_left(participant["id"])
        await self.task.queue_frame(BotInterruptionFrame())
