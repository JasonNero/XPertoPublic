#
# Copyright (c) 2025, Jason Schuehlein
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn import LocalSmartTurnAnalyzer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.observers.turn_tracking_observer import TurnTrackingObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram.stt import (
    DeepgramSTTService,
    LiveOptions,
)
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

from ..utils.audiobuffer_handler import AudioBufferHandler
from ..utils.select_audio_device import AudioDevice, run_device_selector
from ..utils.transcript_handler import TranscriptHandler

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

LANGUAGE = "DE"
# LANGUAGE = "EN"

# Free Tier contains 3 community voice-slots:
VOICE_ID = "kaGxVtjLwllv1bi2GFag"  # David (GER)
# VOICE_ID = "z1EhmmPwF0ENGYE8dBE6"  # Christian (GER)
# VOICE_ID = "yUy9CCX9brt8aPVvIWy3"  # Ramona (GER)

ASSISTANT = "Experto"
ASSISTANT_NAMES = [ASSISTANT, "Experte", "Expertin"]


async def main(input_device: int, output_device: int):
    smart_turn_model_path = os.getenv("LOCAL_SMART_TURN_MODEL_PATH", "../smart-turn")

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            input_device_index=input_device,
            output_device_index=output_device,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzer(
                smart_turn_model_path=smart_turn_model_path,
                params=SmartTurnParams(
                    stop_secs=6.0,  # duration of silence before forcing a turn
                ),
            ),
        )
    )

    audiobuffer = AudioBufferProcessor()
    audiobuffer_handler = AudioBufferHandler(
        output_folder=Path("./recordings"),
        output_name=Path(__file__).stem,
    )

    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        audio_passthrough=True,  # Required for audio recording
        live_options=LiveOptions(
            language=LANGUAGE,
            model="nova-2-general",
            diarize=True,
        ),
    )

    if LANGUAGE == "DE":
        # NOTE: ~20min per month free with Turbo/Flash
        tts = ElevenLabsTTSService(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=VOICE_ID,
            model="eleven_flash_v2_5",
            params=ElevenLabsTTSService.InputParams(
                language="de",
            ),
        )
    elif LANGUAGE == "EN":
        # NOTE: No german voices available, only english
        tts = DeepgramTTSService(
            api_key=os.getenv("DEEPGRAM_API_KEY"), voice="aura-helios-en"
        )

    llm = OpenAILLMService(
        api_key=os.getenv("GDWG_API_KEY"),
        base_url=os.getenv("GDWG_BASE_URL"),
        organization="openai",
        # model="meta-llama-3.1-8b-instruct",
        model="llama-3.3-70b-instruct",
    )

    # NOTE: See https://elevenlabs.io/docs/conversational-ai/best-practices/prompting-guide
    with (Path(__file__).parent.parent / f"personas/{ASSISTANT}_{LANGUAGE}.md").open(
        "r"
    ) as f:
        system_prompt = f.read()

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Create transcript processor and handler
    transcript = TranscriptProcessor()
    transcript_handler = TranscriptHandler(
        output_folder=Path("./transcripts"),
        output_name=Path(__file__).stem,
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            transcript.user(),
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            audiobuffer,
            transcript.assistant(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=True,
        ),
        observers=[
            # DebugLogObserver(frame_types=(OpenAILLMContextFrame,)),
            TurnTrackingObserver()
        ],
    )

    # Register event handlers for audio recording
    audiobuffer.add_event_handler("on_audio_data", audiobuffer_handler.on_audio_data)
    audiobuffer.add_event_handler(
        "on_track_audio_data", audiobuffer_handler.on_track_audio_data
    )

    # Register event handler for saving transcript messages
    @transcript.event_handler("on_transcript_update")
    async def on_transcript_update(processor, frame):
        await transcript_handler.on_transcript_update(processor, frame)

    # Startup sequence, might turn this into a `first_client_connected` event

    if LANGUAGE == "DE":
        intro = "Bitte stelle dich vor und weise darauf hin dass das Gespräch aufgezeichnet wird. Frage dann nach Anzahl und Namen der Teilnehmer. Wenn die genannte Anzahl nicht mit der Anzahl der Speaker IDs im Transkript übereinstimmt oder Namen fehlen, frage erneut nach."
    elif LANGUAGE == "EN":
        intro = "Please introduce yourself and mention that the conversation is being recorded. Then ask for the number and names of the participants. If the mentioned number does not match the number of speaker IDs in the transcript or if names are missing, ask again."

    messages.append(
        {
            "role": "system",
            "content": intro,
        }
    )

    await audiobuffer.start_recording()
    await task.queue_frames([context_aggregator.user().get_context_frame()])

    runner = PipelineRunner()

    await runner.run(task)


def select_device_and_run():
    res: Tuple[AudioDevice, AudioDevice, int] = asyncio.run(
        run_device_selector()  # runs the textual app that allows to select input device
    )

    asyncio.run(main(res[0].index, res[1].index))


if __name__ == "__main__":
    select_device_and_run()
