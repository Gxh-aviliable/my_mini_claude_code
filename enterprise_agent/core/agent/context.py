"""Context management for conversation compression.

Implements:
- Microcompact: Clear old tool results to prevent output bloat
- Auto compact: Summarize when token threshold exceeded, save transcript
- Token estimation: Estimate tokens from messages
- Transcript persistence: Save conversation history before compression
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise_agent.config.settings import settings
from enterprise_agent.core.agent.llm_factory import get_llm

# Transcript storage directory
TRANSCRIPT_DIR_NAME = ".transcripts"


class TranscriptManager:
    """Manages conversation transcript persistence.

    Saves full conversation history before compression for later reference.
    """

    def __init__(self, workdir: Path = None):
        self.workdir = workdir or Path.cwd()
        self.transcript_dir = self.workdir / TRANSCRIPT_DIR_NAME
        self.transcript_dir.mkdir(exist_ok=True)

    def save(self, messages: List[Dict], session_id: str = None) -> Path:
        """Save messages to transcript file.

        Args:
            messages: List of conversation messages
            session_id: Optional session identifier

        Returns:
            Path to saved transcript file
        """
        timestamp = int(time.time())
        filename = f"transcript_{timestamp}"
        if session_id:
            filename = f"transcript_{session_id}_{timestamp}"
        filename += ".jsonl"

        path = self.transcript_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            for msg in messages:
                # Convert message to serializable format
                if hasattr(msg, "to_json"):
                    serialized = msg.to_json()
                elif isinstance(msg, dict):
                    serialized = msg
                else:
                    serialized = {
                        "role": getattr(msg, "role", "unknown"),
                        "content": str(getattr(msg, "content", ""))
                    }
                f.write(json.dumps(serialized, default=str) + "\n")

        return path

    def load(self, path: Path) -> List[Dict]:
        """Load messages from transcript file.

        Args:
            path: Path to transcript file

        Returns:
            List of messages
        """
        if not path.exists():
            return []

        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    messages.append(json.loads(line))
        return messages

    def list_transcripts(self) -> List[Dict]:
        """List all saved transcripts.

        Returns:
            List of transcript metadata
        """
        transcripts = []
        for f in self.transcript_dir.glob("transcript_*.jsonl"):
            stat = f.stat()
            transcripts.append({
                "path": str(f),
                "filename": f.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        return sorted(transcripts, key=lambda x: x["created"], reverse=True)


class ContextManager:
    """Manages conversation context compression.

    Provides:
    - Token estimation
    - Microcompact (tool result cleanup)
    - Auto compact (full summarization with transcript)
    """

    def __init__(
        self,
        llm=None,
        transcript_manager: TranscriptManager = None
    ):
        self.llm = llm or get_llm()
        self.transcript_manager = transcript_manager or TranscriptManager()
        self.token_threshold = settings.TOKEN_THRESHOLD

    def estimate_tokens(self, messages: List[Any]) -> int:
        """Estimate token count from messages.

        Uses simple estimation: 1 token ≈ 4 characters.

        Args:
            messages: List of messages (can be dict or LangChain message objects)

        Returns:
            Estimated token count
        """
        total_chars = 0
        for msg in messages:
            if isinstance(msg, dict):
                total_chars += len(json.dumps(msg, default=str))
            elif hasattr(msg, "content"):
                # LangChain message object
                content = str(msg.content) if msg.content else ""
                total_chars += len(content)
                # Add overhead for role, metadata
                total_chars += 50
            else:
                total_chars += len(str(msg))

        return total_chars // 4

    def microcompact(self, messages: List[Dict], keep_last: int = 3) -> List[Dict]:
        """Clear old tool results to prevent output bloat.

        Only clears tool_result content in user messages, keeping structure.
        Preserves the most recent 'keep_last' tool results.

        Args:
            messages: List of messages
            keep_last: Number of recent tool results to keep

        Returns:
            Modified messages list (in-place modification)
        """
        # Find all tool_result blocks in user messages
        tool_results = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for part in msg.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append((i, part))

        # Clear old tool results (keep last N)
        if len(tool_results) <= keep_last:
            return messages

        for idx, part in tool_results[:-keep_last]:
            if isinstance(part.get("content"), str) and len(part.get("content", "")) > 100:
                part["content"] = "[cleared - see transcript for full output]"

        return messages

    def microcompact_langchain(
        self,
        messages: List[Any],
        keep_last: int = 3
    ) -> List[Any]:
        """Microcompact for LangChain message objects.

        Args:
            messages: List of LangChain message objects or dicts
            keep_last: Number of recent tool results to keep

        Returns:
            Modified messages list
        """
        # Convert to dict format if needed, then process
        dict_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                dict_messages.append(msg)
            elif hasattr(msg, "type"):
                # LangChain message
                content = msg.content
                if msg.type == "tool":
                    dict_messages.append({
                        "role": "tool",
                        "content": str(content),
                        "tool_call_id": getattr(msg, "tool_call_id", "")
                    })
                else:
                    dict_messages.append({
                        "role": msg.type,
                        "content": str(content) if content else ""
                    })
            else:
                dict_messages.append({"role": "unknown", "content": str(msg)})

        return self.microcompact(dict_messages, keep_last)

    async def auto_compact(
        self,
        messages: List[Any],
        session_id: str = None
    ) -> Dict[str, Any]:
        """Perform full context compression.

        1. Save transcript to file
        2. Generate summary using LLM
        3. Return compressed state

        Args:
            messages: List of messages to compress
            session_id: Optional session identifier for transcript

        Returns:
            Dict with compressed messages, summary, and transcript path
        """
        # Save transcript first
        transcript_path = self.transcript_manager.save(messages, session_id)

        # Extract last portion for summarization
        # Take last 80KB of text to fit in summarization context
        messages_text = json.dumps(messages, default=str)
        if len(messages_text) > settings.CONTEXT_SUMMARY_TRIGGER_CHARS:
            messages_text = messages_text[-settings.CONTEXT_SUMMARY_TRIGGER_CHARS:]

        # Generate summary
        summary_prompt = f"""Summarize the following conversation for context continuity.
Preserve key information: decisions made, code written, files modified, current task status, and any important findings.

Conversation:
{messages_text}

Provide a concise summary that allows continuing the work seamlessly."""

        response = await self.llm.ainvoke([{"role": "user", "content": summary_prompt}])
        summary = response.content

        # Return compressed state
        return {
            "compressed_messages": [
                {
                    "role": "system",
                    "content": f"""[Context Compressed - Transcript saved to: {transcript_path}]

Previous conversation summary:
{summary}

Continue working from this summary. Reference the transcript file if needed for detailed history."""
                }
            ],
            "context_summary": summary,
            "transcript_path": str(transcript_path),
            "token_count_reset": 0
        }

    async def manual_compress(
        self,
        messages: List[Any],
        session_id: str = None
    ) -> Dict[str, Any]:
        """Manually triggered compression.

        Same as auto_compact but always executes regardless of threshold.

        Args:
            messages: List of messages
            session_id: Session identifier

        Returns:
            Compression result
        """
        return await self.auto_compact(messages, session_id)


# Global instance
_context_manager: Optional[ContextManager] = None
_transcript_manager: Optional[TranscriptManager] = None


def get_context_manager() -> ContextManager:
    """Get or create ContextManager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


def get_transcript_manager() -> TranscriptManager:
    """Get or create TranscriptManager instance."""
    global _transcript_manager
    if _transcript_manager is None:
        _transcript_manager = TranscriptManager()
    return _transcript_manager