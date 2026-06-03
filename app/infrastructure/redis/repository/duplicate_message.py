"""Redis adapter for duplicate message and warning state"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from redis.asyncio import Redis

from app.domain import DuplicateMessageState
from app.infrastructure.redis.client import redis_value_to_str

DUPLICATE_MESSAGE_KEY_PREFIX = "duplicate_message"
DUPLICATE_MESSAGE_WARNING_KEY_PREFIX = "duplicate_message_warning"


class DuplicateMessageRepository:
    def __init__(
        self,
        redis: Redis,
        *,
        ttl_seconds: int,
        warning_ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._warning_ttl_seconds = warning_ttl_seconds

    @staticmethod
    def normalize_content_key(content_key: str) -> str:
        return " ".join(content_key.casefold().split())

    @classmethod
    def digest_content_key(cls, content_key: str) -> str:
        normalized_content_key = cls.normalize_content_key(content_key)
        return hashlib.sha256(normalized_content_key.encode("utf-8")).hexdigest()

    @staticmethod
    def key(chat_id: int, user_id: int) -> str:
        return f"{DUPLICATE_MESSAGE_KEY_PREFIX}:{chat_id}:{user_id}"

    @staticmethod
    def warning_key(chat_id: int, user_id: int) -> str:
        return f"{DUPLICATE_MESSAGE_WARNING_KEY_PREFIX}:{chat_id}:{user_id}"

    async def record_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        message_id: int,
        content_key: str,
    ) -> DuplicateMessageState:
        normalized_content_key = self.normalize_content_key(content_key)
        digest = self.digest_content_key(content_key)
        previous = await self.get(chat_id=chat_id, user_id=user_id)
        message_ids: tuple[int, ...] = (message_id,)
        if previous is not None and previous.digest == digest:
            message_ids = (*previous.message_ids, message_id)

        state = DuplicateMessageState(
            user_id=user_id,
            chat_id=chat_id,
            digest=digest,
            content_key=normalized_content_key,
            message_ids=message_ids,
        )
        await self._redis.set(
            self.key(chat_id, user_id),
            json.dumps(asdict(state), ensure_ascii=False),
            ex=self._ttl_seconds,
        )
        return state

    async def get(
        self,
        *,
        chat_id: int,
        user_id: int,
    ) -> DuplicateMessageState | None:
        raw = await self._redis.get(self.key(chat_id, user_id))
        if raw is None:
            return None
        return DuplicateMessageState.from_mapping(json.loads(raw))

    async def clear(self, *, chat_id: int, user_id: int) -> None:
        await self._redis.delete(self.key(chat_id, user_id))

    async def get_warning_digest(self, *, chat_id: int, user_id: int) -> str | None:
        raw = await self._redis.get(self.warning_key(chat_id, user_id))
        return redis_value_to_str(raw)

    async def mark_warned(
        self,
        *,
        chat_id: int,
        user_id: int,
        digest: str,
    ) -> None:
        await self._redis.set(
            self.warning_key(chat_id, user_id),
            digest,
            ex=self._warning_ttl_seconds,
        )

    async def mark_warned_once(
        self,
        *,
        chat_id: int,
        user_id: int,
        digest: str,
    ) -> bool:
        was_set = await self._redis.set(
            self.warning_key(chat_id, user_id),
            digest,
            ex=self._warning_ttl_seconds,
            nx=True,
        )
        return bool(was_set)

    async def clear_warning(self, *, chat_id: int, user_id: int) -> None:
        await self._redis.delete(self.warning_key(chat_id, user_id))
