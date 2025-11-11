import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext


@dataclass
class ContextInfo:
    session_id: str
    timestamp: datetime.datetime
    participant_count: int
    message_count: int
    config_used: str
    file_path: Path


class ConversationContextManager:
    """Manages saving and loading conversation contexts for session resumption."""

    def __init__(self, contexts_dir: Path = Path("~/.xperto/contexts").expanduser()):
        self.contexts_dir = contexts_dir
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self, config_name: str = "default") -> str:
        """Generate a unique session ID based on timestamp and config."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{config_name}"

    def save_context(
        self,
        context: OpenAILLMContext,
        session_id: str,
        config_name: str = "default",
        participant_count: int = 1,
    ) -> Path:
        """Save conversation context to file.

        Args:
            context: The OpenAI LLM context to save
            session_id: Unique identifier for this session
            config_name: Name of config used for this session
            participant_count: Number of participants in conversation

        Returns:
            Path to the saved context file
        """
        context_file = self.contexts_dir / f"{session_id}.json"

        # Prepare context data
        context_data = {
            "session_id": session_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "config_used": config_name,
            "participant_count": participant_count,
            "message_count": len(context.messages),
            "messages": context.messages,
            "tools": context.tools,
            "metadata": {
                "saved_at": datetime.datetime.now().isoformat(),
                "version": "1.0",
            },
        }

        try:
            with context_file.open("w", encoding="utf-8") as f:
                json.dump(context_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Context saved to: {context_file}")
            return context_file

        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            raise

    def load_context(self, session_id: str) -> tuple[OpenAILLMContext, Dict[str, Any]]:
        """Load conversation context from file.

        Args:
            session_id: Session ID to load (can be partial match)

        Returns:
            Tuple of (OpenAILLMContext, metadata dict)

        Raises:
            FileNotFoundError: If context file doesn't exist
            ValueError: If multiple contexts match partial session_id
        """
        context_file = self._resolve_context_file(session_id)

        try:
            with context_file.open("r", encoding="utf-8") as f:
                context_data = json.load(f)

            # Create new context and populate with messages
            context = OpenAILLMContext()
            # Clear existing messages and extend with loaded messages
            context.messages.clear()
            context.messages.extend(context_data["messages"])
            tools = context_data.get("tools", [])
            if tools:
                context.set_tools(tools)

            # Extract metadata
            metadata = {
                "session_id": context_data["session_id"],
                "timestamp": context_data["timestamp"],
                "config_used": context_data["config_used"],
                "participant_count": context_data["participant_count"],
                "message_count": context_data["message_count"],
            }

            logger.info(f"Context loaded from: {context_file}")
            logger.info(f"Resuming session with {len(context.messages)} messages")

            return context, metadata

        except Exception as e:
            logger.error(f"Failed to load context: {e}")
            raise

    def list_saved_contexts(self) -> List[ContextInfo]:
        """List all available saved contexts.

        Returns:
            List of ContextInfo objects sorted by timestamp (newest first)
        """
        contexts = []

        for context_file in self.contexts_dir.glob("*.json"):
            try:
                with context_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                contexts.append(
                    ContextInfo(
                        session_id=data["session_id"],
                        timestamp=datetime.datetime.fromisoformat(data["timestamp"]),
                        participant_count=data["participant_count"],
                        message_count=data["message_count"],
                        config_used=data["config_used"],
                        file_path=context_file,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to read context file {context_file}: {e}")
                continue

        # Sort by timestamp, newest first
        contexts.sort(key=lambda x: x.timestamp, reverse=True)
        return contexts

    def _resolve_context_file(self, session_id: str) -> Path:
        """Resolve session_id to actual context file path.

        Supports exact matches and partial matches (if unique).

        Args:
            session_id: Full or partial session ID

        Returns:
            Path to context file

        Raises:
            FileNotFoundError: If no matching context found
            ValueError: If multiple contexts match partial session_id
        """
        # Try exact match first
        exact_file = self.contexts_dir / f"{session_id}.json"
        if exact_file.exists():
            return exact_file

        # Try partial match
        matching_files = list(self.contexts_dir.glob(f"*{session_id}*.json"))

        if not matching_files:
            raise FileNotFoundError(f"No context found matching: {session_id}")

        if len(matching_files) > 1:
            matches = [f.stem for f in matching_files]
            raise ValueError(f"Multiple contexts match '{session_id}': {matches}")

        return matching_files[0]
