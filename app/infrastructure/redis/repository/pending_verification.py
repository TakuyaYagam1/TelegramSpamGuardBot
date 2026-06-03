"""Redis adapter for pending verification records with TTL"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

from redis.asyncio import Redis

from app.domain import PendingVerification


class PendingVerificationRepository:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key(chat_id: int, user_id: int) -> str:
        return f"verify:{chat_id}:{user_id}"

    async def create(
        self,
        *,
        user_id: int,
        chat_id: int,
        verification_message_id: int,
        message_thread_id: int | None = None,
        verification_chat_id: int | None = None,
    ) -> PendingVerification:
        pending = PendingVerification(
            user_id=user_id,
            chat_id=chat_id,
            verification_message_id=verification_message_id,
            created_at=datetime.now(UTC).isoformat(),
            message_thread_id=message_thread_id,
            verification_chat_id=verification_chat_id,
        )
        await self._redis.set(
            self.key(chat_id, user_id),
            json.dumps(asdict(pending), ensure_ascii=False),
            ex=self._ttl_seconds,
        )
        return pending

    async def get(self, *, chat_id: int, user_id: int) -> PendingVerification | None:
        raw = await self._redis.get(self.key(chat_id, user_id))
        if raw is None:
            return None
        return PendingVerification.from_mapping(json.loads(raw))

    async def delete(self, *, chat_id: int, user_id: int) -> bool:
        deleted = await self._redis.delete(self.key(chat_id, user_id))
        return deleted > 0

    async def get_ttl(self, *, chat_id: int, user_id: int) -> int | None:
        ttl = await self._redis.ttl(self.key(chat_id, user_id))
        if ttl < 0:
            return None
        return ttl
