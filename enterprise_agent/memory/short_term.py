import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import redis.asyncio as redis

from enterprise_agent.config.settings import settings
from enterprise_agent.memory.base import MemoryBase


class ShortTermMemory(MemoryBase):
    """Redis短期记忆存储 - 会话状态和对话历史缓存"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = timedelta(hours=settings.SHORT_TERM_TTL_HOURS)
        self.max_messages = settings.MAX_MESSAGES_PER_SESSION

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Dict = None
    ) -> None:
        """追加消息到会话历史"""
        key = f"session:{session_id}:messages"
        message = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.redis.rpush(key, json.dumps(message))
        await self.redis.ltrim(key, -self.max_messages, -1)
        await self.redis.expire(key, self.default_ttl)

    async def get_messages(
        self,
        session_id: str,
        limit: int = None
    ) -> List[Dict]:
        """获取会话消息"""
        key = f"session:{session_id}:messages"
        if limit:
            raw_messages = await self.redis.lrange(key, -limit, -1)
        else:
            raw_messages = await self.redis.lrange(key, 0, -1)
        return [json.loads(m) for m in raw_messages]

    async def clear_messages(self, session_id: str) -> None:
        """清空会话消息"""
        key = f"session:{session_id}:messages"
        await self.redis.delete(key)

    async def get_state(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态（todos、当前任务等）"""
        key = f"session:{session_id}:state"
        state = await self.redis.hgetall(key)
        if state:
            return {k: json.loads(v) for k, v in state.items()}
        return {}

    async def set_state(
        self,
        session_id: str,
        state: Dict[str, Any]
    ) -> None:
        """设置会话状态"""
        key = f"session:{session_id}:state"
        await self.redis.delete(key)
        if state:
            mapping = {k: json.dumps(v) for k, v in state.items()}
            await self.redis.hset(key, mapping=mapping)
            await self.redis.expire(key, self.default_ttl)

    async def acquire_lock(self, session_id: str, timeout: int = 30) -> bool:
        """获取会话锁（防止并发修改）"""
        key = f"lock:session:{session_id}"
        return await self.redis.set(key, "1", ex=timeout, nx=True)

    async def release_lock(self, session_id: str) -> None:
        """释放会话锁"""
        key = f"lock:session:{session_id}"
        await self.redis.delete(key)

    async def cache_tool_result(
        self,
        session_id: str,
        tool_name: str,
        tool_input_hash: str,
        result: Any,
        ttl_seconds: int = 3600
    ) -> None:
        """缓存工具执行结果"""
        key = f"session:{session_id}:tools_cache:{tool_name}:{tool_input_hash}"
        await self.redis.set(key, json.dumps(result), ex=ttl_seconds)

    async def get_cached_tool_result(
        self,
        session_id: str,
        tool_name: str,
        tool_input_hash: str
    ) -> Optional[Any]:
        """获取缓存的工具结果"""
        key = f"session:{session_id}:tools_cache:{tool_name}:{tool_input_hash}"
        result = await self.redis.get(key)
        return json.loads(result) if result else None

    # MemoryBase接口实现
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        await self.redis.set(key, json.dumps(data), ex=self.default_ttl)

    async def retrieve(self, key: str) -> Dict[str, Any]:
        result = await self.redis.get(key)
        return json.loads(result) if result else {}

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)