import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def hello_cache_key(session_id: str) -> str:
    return f"session:{session_id}:hello"


async def get_cached_hello(redis_client: Redis, session_id: str) -> str | None:
    key = hello_cache_key(session_id)
    try:
        value = await redis_client.get(key)
    except RedisError:
        logger.exception("Redis get failed for key %s", key)
        return None

    if value:
        logger.info("Cache hit: %s", key)
        return value

    logger.info("Cache miss: %s", key)
    return None


async def set_cached_hello(
    redis_client: Redis,
    session_id: str,
    message: str,
    cache_ttl: int,
) -> None:
    key = hello_cache_key(session_id)
    try:
        await redis_client.set(key, message, ex=cache_ttl)
        logger.info("Greeting stored in Redis with TTL=%s", cache_ttl)
    except RedisError:
        logger.exception("Redis set failed for key %s", key)
