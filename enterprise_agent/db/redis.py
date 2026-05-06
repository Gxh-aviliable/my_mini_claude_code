import redis.asyncio as redis

from enterprise_agent.config.settings import settings

# Redis connection pool
redis_pool = redis.ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    max_connections=50,
    decode_responses=True
)

redis_client = redis.Redis(connection_pool=redis_pool)


async def get_redis() -> redis.Redis:
    """Get Redis client for dependency injection"""
    return redis_client


async def close_redis() -> None:
    """Close Redis connection pool"""
    await redis_pool.aclose()