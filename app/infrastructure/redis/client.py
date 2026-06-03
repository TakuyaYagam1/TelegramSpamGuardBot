"""Redis client factory and lifecycle helpers"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis


def redis_value_to_str(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


class RedisClientLifecycle:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self.client: Redis | None = None

    async def startup(self) -> Redis:
        if self.client is None:
            self.client = create_redis_client(self._redis_url)
        await self.client.ping()
        return self.client

    async def shutdown(self) -> None:
        if self.client is None:
            return

        await self.client.aclose(close_connection_pool=True)
        self.client = None


@asynccontextmanager
async def redis_lifespan(redis_url: str) -> AsyncIterator[Redis]:
    lifecycle = RedisClientLifecycle(redis_url)
    client = await lifecycle.startup()
    try:
        yield client
    finally:
        await lifecycle.shutdown()
