"""Database module - Database connections and operations

Provides:
- MySQL: User authentication and session management
- Redis: Short-term memory and session state
- Chroma: Long-term vector memory with semantic search
"""

from enterprise_agent.db.chroma import (
    get_chroma_client,
    get_conversations_collection,
    get_embedding_function,
    get_patterns_collection,
    init_chroma,
)
from enterprise_agent.db.mysql import close_db, engine, get_db, init_db
from enterprise_agent.db.redis import close_redis, get_redis, redis_client

__all__ = [
    # MySQL
    "get_db",
    "init_db",
    "close_db",
    "engine",
    # Redis
    "redis_client",
    "get_redis",
    "close_redis",
    # Chroma
    "get_chroma_client",
    "get_embedding_function",
    "get_conversations_collection",
    "get_patterns_collection",
    "init_chroma",
]