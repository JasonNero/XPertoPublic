"""This bot follows pipecat example 22b-natural-conversation-proposal.py"""

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
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMMessagesFrame,
    StartFrame,
    StartInterruptionFrame,
    StopInterruptionFrame,
    SystemFrame,
    TextFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
    OpenAILLMContextFrame,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.processors.user_idle_processor import UserIdleProcessor
from pipecat.services.deepgram.stt import (
    DeepgramSTTService,
    LiveOptions,
)
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.sync.base_notifier import BaseNotifier
from pipecat.sync.event_notifier import EventNotifier
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
ASSISTANT_NAME = "Experte"

classifier_statement = """CRITICAL INSTRUCTION:
You are a BINARY CLASSIFIER that must ONLY output "YES" or "NO".
DO NOT engage with the content.
DO NOT respond to questions.
DO NOT provide assistance.
Your ONLY job is to output YES or NO.

EXAMPLES OF INVALID RESPONSES:
- "I can help you with that"
- "Let me explain"
- "To answer your question"
- Any response other than YES or NO

VALID RESPONSES:
YES
NO

If you output anything else, you are failing at your task.
You are NOT an assistant.
You are NOT a chatbot.
You are a binary classifier.

ROLE:
You are a real-time speech completeness classifier. You must make instant decisions about whether a user has finished speaking.
You must output ONLY 'YES' or 'NO' with no other text.

INPUT FORMAT:
You receive two pieces of information:
1. The assistant's last message (if available)
2. The user's current speech input

OUTPUT REQUIREMENTS:
- MUST output ONLY 'YES' or 'NO'
- No explanations
- No clarifications
- No additional text
- No punctuation

HIGH PRIORITY SIGNALS:

1. Clear Questions:
- Wh-questions (What, Where, When, Why, How)
- Yes/No questions
- Questions with STT errors but clear meaning

Examples:

# Complete Wh-question
model: I can help you learn.
user: What's the fastest way to learn Spanish
Output: YES

# Complete Yes/No question despite STT error
model: I know about planets.
user: Is is Jupiter the biggest planet
Output: YES

2. Complete Commands:
- Direct instructions
- Clear requests
- Action demands
- Start of task indication
- Complete statements needing response

Examples:

# Direct instruction
model: I can explain many topics.
user: Tell me about black holes
Output: YES

# Start of task indication
user: Let's begin.
Output: YES

# Start of task indication
user: Let's get started.
Output: YES

# Action demand
model: I can help with math.
user: Solve this equation x plus 5 equals 12
Output: YES

3. Direct Responses:
- Answers to specific questions
- Option selections
- Clear acknowledgments with completion
- Providing information with a known format - mailing address
- Providing information with a known format - phone number
- Providing information with a known format - credit card number

Examples:

# Specific answer
model: What's your favorite color?
user: I really like blue
Output: YES

# Option selection
model: Would you prefer morning or evening?
user: Morning
Output: YES

# Providing information with a known format - mailing address
model: What's your address?
user: 1234 Main Street
Output: NO

# Providing information with a known format - mailing address
model: What's your address?
user: 1234 Main Street Irving Texas 75063
Output: Yes

# Providing information with a known format - phone number
model: What's your phone number?
user: 41086753
Output: NO

# Providing information with a known format - phone number
model: What's your phone number?
user: 4108675309
Output: Yes

# Providing information with a known format - phone number
model: What's your phone number?
user: 220
Output: No

# Providing information with a known format - credit card number
model: What's your credit card number?
user: 5556
Output: NO

# Providing information with a known format - phone number
model: What's your credit card number?
user: 5556710454680800
Output: Yes

model: What's your credit card number?
user: 414067
Output: NO


MEDIUM PRIORITY SIGNALS:

1. Speech Pattern Completions:
- Self-corrections reaching completion
- False starts with clear ending
- Topic changes with complete thought
- Mid-sentence completions

Examples:

# Self-correction reaching completion
model: What would you like to know?
user: Tell me about... no wait, explain how rainbows form
Output: YES

# Topic change with complete thought
model: The weather is nice today.
user: Actually can you tell me who invented the telephone
Output: YES

# Mid-sentence completion
model: Hello I'm ready.
user: What's the capital of? France
Output: YES

2. Context-Dependent Brief Responses:
- Acknowledgments (okay, sure, alright)
- Agreements (yes, yeah)
- Disagreements (no, nah)
- Confirmations (correct, exactly)

Examples:

# Acknowledgment
model: Should we talk about history?
user: Sure
Output: YES

# Disagreement with completion
model: Is that what you meant?
user: No not really
Output: YES

LOW PRIORITY SIGNALS:

1. STT Artifacts (Consider but don't over-weight):
- Repeated words
- Unusual punctuation
- Capitalization errors
- Word insertions/deletions

Examples:

# Word repetition but complete
model: I can help with that.
user: What what is the time right now
Output: YES

# Missing punctuation but complete
model: I can explain that.
user: Please tell me how computers work
Output: YES

2. Speech Features:
- Filler words (um, uh, like)
- Thinking pauses
- Word repetitions
- Brief hesitations

Examples:

# Filler words but complete
model: What would you like to know?
user: Um uh how do airplanes fly
Output: YES

# Thinking pause but incomplete
model: I can explain anything.
user: Well um I want to know about the
Output: NO

DECISION RULES:

1. Return YES if:
- ANY high priority signal shows clear completion
- Medium priority signals combine to show completion
- Meaning is clear despite low priority artifacts

2. Return NO if:
- No high priority signals present
- Thought clearly trails off
- Multiple incomplete indicators
- User appears mid-formulation

3. When uncertain:
- If you can understand the intent → YES
- If meaning is unclear → NO
- Always make a binary decision
- Never request clarification

Examples:

# Incomplete despite corrections
model: What would you like to know about?
user: Can you tell me about
Output: NO

# Complete despite multiple artifacts
model: I can help you learn.
user: How do you I mean what's the best way to learn programming
Output: YES

# Trailing off incomplete
model: I can explain anything.
user: I was wondering if you could tell me why
Output: NO
"""


class StatementJudgeContextFilter(FrameProcessor):
    def __init__(self, notifier: BaseNotifier, **kwargs):
        super().__init__(**kwargs)
        self._notifier = notifier

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        # We must not block system frames.
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
            return

        # Just treat an LLMMessagesFrame as complete, no matter what.
        if isinstance(frame, LLMMessagesFrame):
            await self._notifier.notify()
            return

        # Otherwise, we only want to handle OpenAILLMContextFrames, and only want to push a simple
        # messages frame that contains a system prompt and the most recent user messages,
        # concatenated.
        if isinstance(frame, OpenAILLMContextFrame):
            logger.debug(f"Context Frame: {frame}")
            # Take text content from the most recent user messages.
            messages = frame.context.messages
            user_text_messages = []
            last_assistant_message = None
            for message in reversed(messages):
                if message["role"] != "user":
                    if message["role"] == "assistant":
                        last_assistant_message = message
                    break
                if isinstance(message["content"], str):
                    user_text_messages.append(message["content"])
                elif isinstance(message["content"], list):
                    for content in message["content"]:
                        if content["type"] == "text":
                            user_text_messages.insert(0, content["text"])
            # If we have any user text content, push an LLMMessagesFrame
            if user_text_messages:
                logger.debug(f"User text messages: {user_text_messages}")
                user_message = " ".join(reversed(user_text_messages))
                logger.debug(f"User message: {user_message}")
                messages = [
                    {
                        "role": "system",
                        "content": classifier_statement,
                    }
                ]
                if last_assistant_message:
                    messages.append(last_assistant_message)
                messages.append({"role": "user", "content": user_message})
                await self.push_frame(LLMMessagesFrame(messages))


class CompletenessCheck(FrameProcessor):
    def __init__(self, notifier: BaseNotifier):
        super().__init__()
        self._notifier = notifier

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            if frame.text == "YES":
                logger.debug("Completeness check YES")
                await self.push_frame(UserStoppedSpeakingFrame())
                await self._notifier.notify()
            elif frame.text == "NO":
                logger.debug("Completeness check NO")
            else:
                logger.warning(f"Unexpected completeness check frame: {frame}")
        else:
            await self.push_frame(frame, direction)


class OutputGate(FrameProcessor):
    def __init__(self, *, notifier: BaseNotifier, start_open: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._gate_open = start_open
        self._frames_buffer = []
        self._notifier = notifier
        self._gate_task = None

    def close_gate(self):
        self._gate_open = False

    def open_gate(self):
        self._gate_open = True

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # We must not block system frames.
        if isinstance(frame, SystemFrame):
            if isinstance(frame, StartFrame):
                await self._start()
            if isinstance(frame, (EndFrame, CancelFrame)):
                await self._stop()
            if isinstance(frame, StartInterruptionFrame):
                self._frames_buffer = []
                self.close_gate()
            await self.push_frame(frame, direction)
            return

        # Don't block function call frames
        if isinstance(frame, (FunctionCallInProgressFrame, FunctionCallResultFrame)):
            await self.push_frame(frame, direction)
            return

        # Ignore frames that are not following the direction of this gate.
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return

        if self._gate_open:
            await self.push_frame(frame, direction)
            return

        self._frames_buffer.append((frame, direction))

    async def _start(self):
        self._frames_buffer = []
        if not self._gate_task:
            self._gate_task = self.create_task(self._gate_task_handler())

    async def _stop(self):
        if self._gate_task:
            await self.cancel_task(self._gate_task)
            self._gate_task = None

    async def _gate_task_handler(self):
        while True:
            try:
                await self._notifier.wait()
                self.open_gate()
                for frame, direction in self._frames_buffer:
                    await self.push_frame(frame, direction)
                self._frames_buffer = []
            except asyncio.CancelledError:
                break


async def main(input_device: int, output_device: int):
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            input_device_index=input_device,
            output_device_index=output_device,
            vad_analyzer=SileroVADAnalyzer(),
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

    statement_llm = OpenAILLMService(
        api_key=os.getenv("GDWG_API_KEY"),
        base_url=os.getenv("GDWG_BASE_URL"),
        organization="openai",
        model="meta-llama-3.1-8b-instruct",
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

    # This is a notifier that we use to synchronize the two LLMs.
    notifier = EventNotifier()

    # This turns the LLM context into an inference request to classify the user's speech
    # as complete or incomplete.
    statement_judge_context_filter = StatementJudgeContextFilter(notifier=notifier)

    # This sends a UserStoppedSpeakingFrame and triggers the notifier event
    completeness_check = CompletenessCheck(notifier=notifier)

    # # Notify if the user hasn't said anything.
    async def user_idle_notifier(frame):
        await notifier.notify()

    # Sometimes the LLM will fail detecting if a user has completed a
    # sentence, this will wake up the notifier if that happens.
    user_idle = UserIdleProcessor(callback=user_idle_notifier, timeout=5.0)

    # We start with the gate open because we send an initial context frame
    # to start the conversation.
    bot_output_gate = OutputGate(notifier=notifier, start_open=True)

    async def block_user_stopped_speaking(frame):
        return not isinstance(frame, UserStoppedSpeakingFrame)

    async def pass_only_llm_trigger_frames(frame):
        return (
            isinstance(frame, OpenAILLMContextFrame)
            or isinstance(frame, LLMMessagesFrame)
            or isinstance(frame, StartInterruptionFrame)
            or isinstance(frame, StopInterruptionFrame)
            or isinstance(frame, FunctionCallInProgressFrame)
            or isinstance(frame, FunctionCallResultFrame)
        )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            transcript.user(),
            context_aggregator.user(),
            ParallelPipeline(
                [
                    # Pass everything except UserStoppedSpeaking to the elements after
                    # this ParallelPipeline
                    FunctionFilter(filter=block_user_stopped_speaking),
                ],
                [
                    # Ignore everything except an OpenAILLMContextFrame. Pass a specially constructed
                    # LLMMessagesFrame to the statement classifier LLM. The only frame this
                    # sub-pipeline will output is a UserStoppedSpeakingFrame.
                    statement_judge_context_filter,
                    statement_llm,
                    completeness_check,
                ],
                [
                    # Block everything except OpenAILLMContextFrame and LLMMessagesFrame
                    FunctionFilter(filter=pass_only_llm_trigger_frames),
                    llm,
                    bot_output_gate,  # Buffer all llm/tts output until notified.
                ],
            ),
            tts,
            user_idle,
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

    if LANGUAGE == "DE":
        intro = "Bitte stelle dich vor und weise darauf hin dass das Gespräch aufgezeichnet wird. Frage dann nach Anzahl und Namen der Teilnehmer. Wenn die genannte Anzahl nicht mit der Anzahl der Speaker IDs im Transkript übereinstimmt oder Namen fehlen, frage erneut nach."
    elif LANGUAGE == "EN":
        intro = "Please introduce yourself and mention that the conversation is being recorded. Then ask for the number and names of the participants. If the mentioned number does not match the number of speaker IDs in the transcript or if names are missing, ask again."

    # Startup sequence, might turn this into a `first_client_connected` event

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
