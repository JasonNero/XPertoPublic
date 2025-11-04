import asyncio
import time
from typing import Optional

from loguru import logger
from pipecat.frames.frames import CancelFrame, Frame
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .context_manager import ConversationContextManager


class ContextSaverProcessor(FrameProcessor):
    """
    A frame processor that passes all frames through while periodically saving
    conversation context and responding to CancelFrame for final saves.
    """

    def __init__(
        self,
        context: OpenAILLMContext,
        context_manager: ConversationContextManager,
        session_id: str,
        config_name: str = "default",
        save_interval: float = 60.0,  # Save every minute
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.context = context
        self.context_manager = context_manager
        self.session_id = session_id
        self.config_name = config_name
        self.save_interval = save_interval

        self.last_save_time = time.time()
        self.participant_count = 1
        self._save_task: Optional[asyncio.Task] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and handle context saving."""
        await super().process_frame(frame, direction)

        # Handle CancelFrame - save context before cancellation
        if isinstance(frame, CancelFrame):
            logger.info("CancelFrame detected, saving context before cancellation")
            await self._save_context_now()
            await self.push_frame(frame, direction)
            return

        # Check if it's time for periodic save
        current_time = time.time()
        if current_time - self.last_save_time >= self.save_interval:
            # Don't block the pipeline - save asynchronously
            if self._save_task is None or self._save_task.done():
                self._save_task = asyncio.create_task(self._save_context_periodic())

        # Pass frame through unchanged
        await self.push_frame(frame, direction)

    async def _save_context_now(self) -> bool:
        """Save context immediately (synchronous save)."""
        try:
            if (
                len(self.context.messages) > 2
            ):  # Only save if there's actual conversation
                file_path = self.context_manager.save_context(
                    self.context,
                    self.session_id,
                    config_name=self.config_name,
                    participant_count=self.participant_count,
                )
                self.last_save_time = time.time()
                logger.debug(f"Context saved to: {file_path}")
                return True
            else:
                logger.debug("No conversation to save yet")
                return False

        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            return False

    async def _save_context_periodic(self):
        """Save context periodically (asynchronous save)."""
        try:
            if (
                len(self.context.messages) > 2
            ):  # Only save if there's actual conversation
                file_path = self.context_manager.save_context(
                    self.context,
                    self.session_id,
                    config_name=self.config_name,
                    participant_count=self.participant_count,
                )
                self.last_save_time = time.time()
                logger.info(f"Periodic context save completed: {file_path}")
            else:
                logger.debug("No conversation to save yet")
                self.last_save_time = time.time()  # Update time anyway

        except Exception as e:
            logger.error(f"Failed to save context periodically: {e}")

    def set_participant_count(self, count: int):
        """Update participant count for context metadata."""
        self.participant_count = count

    async def cleanup(self):
        """Clean up any pending save tasks."""
        if self._save_task and not self._save_task.done():
            try:
                await self._save_task
            except Exception as e:
                logger.error(f"Error during context saver cleanup: {e}")
