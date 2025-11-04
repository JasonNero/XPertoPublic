import datetime
from pathlib import Path
from typing import List, Optional

from loguru import logger
from pipecat.frames.frames import TranscriptionMessage, TranscriptionUpdateFrame
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.utils.time import time_now_iso8601


class TranscriptHandler:
    """Handles real-time transcript processing and output.

    Maintains a list of conversation messages and outputs them either to a log
    or to a file as they are received. Each message includes its timestamp and role.

    Attributes:
        messages: List of all processed transcript messages
        output_file: Optional path to file where transcript is saved. If None, outputs to log only.
    """

    def __init__(
        self,
        output_folder: Optional[Path] = Path("./transcripts"),
        output_name: str = "bot",
    ):
        """Initialize handler with optional file output.

        Args:
            output_file: Path to output file. If None, outputs to log only.
        """
        self.messages: List[TranscriptionMessage] = []
        self.output_file: Optional[Path] = None

        if output_folder is not None:
            output_folder.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_file = output_folder / f"{timestamp}_{output_name}.log"
            logger.info(f"Transcript will be saved to: {self.output_file.as_posix()}")

    async def handle_participant_joined(self, participant_id: str):
        """Handle a new participant joining the conversation.

        Args:
            participant_id: ID of the participant that joined
        """
        if self.output_file:
            try:
                with self.output_file.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{time_now_iso8601()}] Participant {participant_id} joined the call.\n"
                    )
            except Exception as e:
                logger.error(f"Error writing participant join message to file: {e}")

    async def handle_participant_left(self, participant_id: str):
        """Handle a participant leaving the conversation.

        Args:
            participant_id: ID of the participant that left
        """
        if self.output_file:
            try:
                with self.output_file.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{time_now_iso8601()}] Participant {participant_id} left the call.\n"
                    )
            except Exception as e:
                logger.error(f"Error writing participant leave message to file: {e}")

    async def save_message(self, message: TranscriptionMessage):
        """Save a single transcript message.

        Outputs the message to the log and optionally to a file.

        Args:
            message: The message to save
        """
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        line = f"{timestamp}{message.role} {message.user_id}: {message.content}"

        # Always log the message
        logger.info(f"Transcript: {line}")

        # Optionally write to file
        if self.output_file:
            try:
                with self.output_file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as e:
                logger.error(f"Error saving transcript message to file: {e}")

    async def on_transcript_update(
        self, processor: TranscriptProcessor, frame: TranscriptionUpdateFrame
    ):
        """Handle new transcript messages.

        Args:
            processor: The TranscriptProcessor that emitted the update
            frame: TranscriptionUpdateFrame containing new messages
        """
        logger.debug(
            f"Received transcript update with {len(frame.messages)} new messages"
        )

        for msg in frame.messages:
            self.messages.append(msg)
            await self.save_message(msg)
