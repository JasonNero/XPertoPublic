#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import re
import time
from enum import Enum

from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class WakeCheckBuffer(FrameProcessor):
    """This filter looks for wake phrases in transcription frames from any participant and maintains
    a single shared wake state. Frames are buffered until a wake phrase is detected, then all
    buffered frames are released in order. Once awakened, subsequent frames are passed through
    immediately until the keepalive timeout expires.
    """

    class WakeState(Enum):
        IDLE = 1
        AWAKE = 2

    def __init__(self, wake_phrases: list[str], keepalive_timeout_secs: float = 3):
        super().__init__()
        self._state = WakeCheckBuffer.WakeState.AWAKE
        self._wake_timer = time.time()
        self._frame_buffer = []
        self._combined_text = ""
        self._keepalive_timeout_secs = keepalive_timeout_secs
        self._wake_patterns = []
        for name in wake_phrases:
            pattern = re.compile(
                r"\b" + r"\s*".join(re.escape(word) for word in name.split()) + r"\b",
                re.IGNORECASE,
            )
            self._wake_patterns.append(pattern)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        try:
            if isinstance(frame, TranscriptionFrame):
                # If we have been AWAKE within the last keepalive_timeout seconds, pass
                # the frame through immediately
                if self._state == WakeCheckBuffer.WakeState.AWAKE:
                    if time.time() - self._wake_timer < self._keepalive_timeout_secs:
                        logger.debug(
                            f"Wake phrase keepalive timeout has not expired. Pushing {frame}"
                        )

                        # TODO: Rethink when we want to reset the wake timer.
                        #       The current logic only puts the bot to sleep if
                        #       no user speech is detected within 30sec.
                        #       But shouldn't it be 30sec after the last detected
                        #       wake word (or even better bot response)?
                        # NOTE: Leaving it as is to not screw up the Connectival demo ...

                        self._wake_timer = time.time()
                        await self.push_frame(frame)
                        return
                    else:
                        logger.debug(
                            "Wake phrase keepalive timeout expired. Setting to IDLE"
                        )
                        self._state = WakeCheckBuffer.WakeState.IDLE
                        self._frame_buffer.clear()
                        self._combined_text = ""

                # Buffer the frame while IDLE
                self._frame_buffer.append(frame)

                # Incrementally add new frame text to combined text
                if self._combined_text:
                    self._combined_text += " " + frame.text
                else:
                    self._combined_text = frame.text
                # Check combined text for wake phrases
                for pattern in self._wake_patterns:
                    match = pattern.search(self._combined_text)
                    if match:
                        logger.debug(f"Wake phrase triggered: {match.group()}")
                        # Found the wake phrase, set to AWAKE and release all buffered frames
                        self._state = WakeCheckBuffer.WakeState.AWAKE
                        self._wake_timer = time.time()

                        # Push all buffered frames in order
                        for buffered_frame in self._frame_buffer:
                            await self.push_frame(buffered_frame)

                        # Clear the buffer and combined text
                        self._frame_buffer.clear()
                        self._combined_text = ""
                        return
            else:
                await self.push_frame(frame, direction)
        except Exception as e:
            error_msg = f"Error in wake word filter: {e}"
            logger.exception(error_msg)
            await self.push_error(ErrorFrame(error_msg))
