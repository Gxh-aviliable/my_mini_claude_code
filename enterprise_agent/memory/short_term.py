import json
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis

from enterprise_agent.config.settings import settings
from enterprise_agent.memory.base import MemoryBase


class ShortTermMemory(MemoryBase):
    """Redis短期记忆存储 - 会话状态锁、工具缓存等辅助功能

    对话消息持久化已由 LangGraph RedisSaver checkpointer 自动管理。
    本类保留以下功能：
    - 会话状态管理 (get_state / set_state)
    - 分布式锁 (acquire_lock / release_lock)
    - 工具结果缓存 (cache_tool_result / get_cached_tool_result)
    - MemoryBase 接口 (store / retrieve / delete)
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = timedelta(hours=settings.SHORT_TERM_TTL_HOURS)

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

    async def acquire_lock(self, session_id: str, timeout: int = 30) -> Optional[str]:
        """获取会话锁，返回锁 token（None 表示获取失败）"""
        lock_id = str(uuid.uuid4())
        key = f"lock:session:{session_id}"
        acquired = await self.redis.set(key, lock_id, ex=timeout, nx=True)
        return lock_id if acquired else None

    _RELEASE_LOCK_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    async def release_lock(self, session_id: str, lock_id: str) -> bool:
        """释放会话锁（仅当归属匹配时）"""
        key = f"lock:session:{session_id}"
        result = await self.redis.eval(
            self._RELEASE_LOCK_SCRIPT, 1, key, lock_id
        )
        return bool(result)

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