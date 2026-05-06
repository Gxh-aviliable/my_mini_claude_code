"""Memory module - Hierarchical memory management system

Provides:
- ShortTermMemory: Redis-based session locks, tool cache, and state helpers
- LongTermMemory: Chroma-based vector storage with semantic search

对话消息持久化由 LangGraph RedisSaver checkpointer 自动管理（见 core/agent/graph.py）。
"""

from enterprise_agent.memory.base import MemoryBase
from enterprise_agent.memory.long_term import ChromaLongTermMemory, get_long_term_memory
from enterprise_agent.memory.short_term import ShortTermMemory

__all__ = [
    "MemoryBase",
    "ShortTermMemory",
    "ChromaLongTermMemory",
    "get_long_term_memory",
]