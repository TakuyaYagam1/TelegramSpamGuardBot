"""Redis adapter for verified user markers"""

from __future__ import annotations

from redis.asyncio import Redis


class VerifiedUserRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def key(chat_id: int, user_id: int) -> str:
        return f"verified:{chat_id}:{user_id}"

    async def mark_verified(self, *, chat_id: int, user_id: int) -> None:
        await self._redis.set(self.key(chat_id, user_id), "1")

    async def is_verified(self, *, chat_id: int, user_id: int) -> bool:
        exists = await self._redis.exists(self.key(chat_id, user_id))
        return exists > 0
