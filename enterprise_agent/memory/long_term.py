"""Long-term memory using Chroma vector database.

Provides semantic search capability for conversation history and user patterns.
Replaces MySQL-based long-term memory with vector-based storage.
"""

import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from enterprise_agent.db.chroma import (
    get_conversations_collection,
    get_patterns_collection,
    get_chroma_client,
)
from enterprise_agent.config.settings import settings
from enterprise_agent.memory.base import MemoryBase


class ChromaLongTermMemory(MemoryBase):
    """Long-term memory using Chroma vector database.

    Collections:
    - conversations: Message history with semantic search
    - user_patterns: User behavior patterns and preferences
    """

    def __init__(self, user_id: int = None):
        self.user_id = user_id
        self.conversations = get_conversations_collection()
        self.patterns = get_patterns_collection()

    async def store_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store a conversation message with embedding.

        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system/tool)
            content: Message content
            metadata: Additional metadata

        Returns:
            Document ID
        """
        doc_id = f"{session_id}:{uuid.uuid4().hex[:8]}"

        meta = {
            "user_id": self.user_id,
            "session_id": session_id,
            "role": role,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if metadata:
            meta.update(metadata)

        self.conversations.add(
            documents=[content],
            metadatas=[meta],
            ids=[doc_id],
        )

        return doc_id

    async def search_conversations(
        self,
        query: str,
        n_results: int = 10,
        session_id: str = None,
        role: str = None
    ) -> List[Dict[str, Any]]:
        """Search conversations semantically.

        Args:
            query: Search query
            n_results: Number of results
            session_id: Filter by session (optional)
            role: Filter by role (optional)

        Returns:
            List of matching conversations
        """
        where_filter = None
        if session_id or role or self.user_id:
            conditions = []
            if self.user_id:
                conditions.append({"user_id": self.user_id})
            if session_id:
                conditions.append({"session_id": session_id})
            if role:
                conditions.append({"role": role})

            if len(conditions) == 1:
                where_filter = conditions[0]
            elif len(conditions) > 1:
                where_filter = {"$and": conditions}

        results = self.conversations.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
        )

        # Format results
        messages = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                messages.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })

        return messages

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all messages for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages

        Returns:
            List of messages in chronological order
        """
        results = self.conversations.get(
            where={"session_id": session_id},
            limit=limit,
        )

        messages = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results.get("metadatas") else {}
                messages.append({
                    "role": meta.get("role", "unknown"),
                    "content": doc,
                    "metadata": meta,
                })

        # Sort by timestamp
        messages.sort(key=lambda m: m["metadata"].get("timestamp", ""))

        return messages

    async def store_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_value: Dict[str, Any],
        confidence: float = 1.0
    ) -> str:
        """Store a user behavior pattern.

        Args:
            pattern_type: Type of pattern (preference/workflow/shortcut)
            pattern_key: Pattern identifier
            pattern_value: Pattern data
            confidence: Confidence score (0-1)

        Returns:
            Pattern ID
        """
        pattern_id = f"pattern:{self.user_id}:{pattern_type}:{pattern_key}"

        # Create searchable text from pattern
        pattern_text = f"{pattern_type}: {pattern_key} = {json.dumps(pattern_value)}"

        meta = {
            "user_id": self.user_id,
            "pattern_type": pattern_type,
            "pattern_key": pattern_key,
            "confidence": confidence,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.patterns.add(
            documents=[pattern_text],
            metadatas=[meta],
            ids=[pattern_id],
        )

        return pattern_id

    async def search_patterns(
        self,
        query: str,
        pattern_type: str = None,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search user patterns semantically.

        Args:
            query: Search query
            pattern_type: Filter by type (optional)
            n_results: Number of results

        Returns:
            List of matching patterns
        """
        where_filter = {"user_id": self.user_id}
        if pattern_type:
            where_filter["pattern_type"] = pattern_type

        results = self.patterns.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
        )

        patterns = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                patterns.append({
                    "text": doc,
                    "pattern_type": meta.get("pattern_type"),
                    "pattern_key": meta.get("pattern_key"),
                    "confidence": meta.get("confidence"),
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })

        return patterns

    async def get_all_patterns(self) -> List[Dict[str, Any]]:
        """Get all patterns for user.

        Returns:
            List of all user patterns
        """
        results = self.patterns.get(
            where={"user_id": self.user_id},
        )

        patterns = []
        if results and results.get("metadatas"):
            for meta in results["metadatas"]:
                patterns.append({
                    "pattern_type": meta.get("pattern_type"),
                    "pattern_key": meta.get("pattern_key"),
                    "confidence": meta.get("confidence"),
                })

        return patterns

    # MemoryBase interface implementation
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        """Store data with given key (generic interface)."""
        await self.store_conversation(
            session_id=data.get("session_id", "unknown"),
            role=data.get("role", "unknown"),
            content=json.dumps(data),
            metadata={"key": key},
        )

    async def retrieve(self, key: str) -> Dict[str, Any]:
        """Retrieve data by key (generic interface)."""
        results = self.conversations.get(
            where={"key": key},
        )

        if results and results.get("documents"):
            return json.loads(results["documents"][0])
        return {}

    async def delete(self, key: str) -> None:
        """Delete data by key (generic interface)."""
        self.conversations.delete(
            where={"key": key},
        )


# Global instance factory
_long_term_memory: Optional[ChromaLongTermMemory] = None


def get_long_term_memory(user_id: int = None) -> ChromaLongTermMemory:
    """Get or create LongTermMemory instance.

    Args:
        user_id: User identifier for filtering

    Returns:
        ChromaLongTermMemory instance
    """
    global _long_term_memory

    if _long_term_memory is None or _long_term_memory.user_id != user_id:
        _long_term_memory = ChromaLongTermMemory(user_id=user_id)

    return _long_term_memory