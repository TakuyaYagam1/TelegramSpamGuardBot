"""Shared fakes and helpers for verification tests"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeRedis:
    values: dict[str, str] = field(default_factory=dict)
    expirations: dict[str, int] = field(default_factory=dict)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        else:
            self.expirations.pop(key, None)
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return int(existed)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def ttl(self, key: str) -> int:
        if key not in self.values:
            return -2
        return self.expirations.get(key, -1)

    async def scan_iter(self, match: str) -> object:
        prefix = match.removesuffix("*")
        for key in tuple(self.values):
            if key.startswith(prefix):
                yield key


@dataclass
class FakeBot:
    sent_messages: list[dict[str, Any]] = field(default_factory=list)
    deleted_messages: list[dict[str, int]] = field(default_factory=list)
    bans: list[dict[str, int]] = field(default_factory=list)
    unbans: list[dict[str, int]] = field(default_factory=list)
    restrictions: list[dict[str, Any]] = field(default_factory=list)
    approved_join_requests: list[dict[str, int]] = field(default_factory=list)
    declined_join_requests: list[dict[str, int]] = field(default_factory=list)

    async def send_message(self, **kwargs: Any) -> Any:
        self.sent_messages.append(kwargs)
        return SimpleNamespace(message_id=888)

    async def delete_message(self, **kwargs: int) -> None:
        self.deleted_messages.append(kwargs)

    async def ban_chat_member(self, **kwargs: int) -> None:
        self.bans.append(kwargs)

    async def unban_chat_member(self, **kwargs: int) -> None:
        self.unbans.append(kwargs)

    async def restrict_chat_member(self, **kwargs: Any) -> None:
        self.restrictions.append(kwargs)

    async def approve_chat_join_request(self, **kwargs: int) -> None:
        self.approved_join_requests.append(kwargs)

    async def decline_chat_join_request(self, **kwargs: int) -> None:
        self.declined_join_requests.append(kwargs)


class FailingVerificationMessageBot(FakeBot):
    async def send_message(self, **_kwargs: Any) -> Any:
        raise RuntimeError("send failed")


class FailingRestrictBot(FakeBot):
    async def restrict_chat_member(self, **kwargs: Any) -> None:
        self.restrictions.append(kwargs)
        raise RuntimeError("restrict failed")


class FailingRestorePermissionsBot(FakeBot):
    async def restrict_chat_member(self, **kwargs: Any) -> None:
        self.restrictions.append(kwargs)
        if kwargs["permissions"].can_send_messages:
            raise RuntimeError("restore failed")


class FailingUnbanBot(FakeBot):
    async def unban_chat_member(self, **kwargs: int) -> None:
        self.unbans.append(kwargs)
        raise RuntimeError("unban failed")


class FailingCreatePendingRepository:
    async def get(self, *, chat_id: int, user_id: int) -> None:
        return None

    async def create(self, **_kwargs: Any) -> None:
        raise RuntimeError("redis failed")


class FailingDeletePendingRepository:
    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self.delete_calls: list[dict[str, int]] = []

    async def get(self, *, chat_id: int, user_id: int) -> Any:
        return await self.repository.get(chat_id=chat_id, user_id=user_id)

    async def create(self, **kwargs: Any) -> Any:
        return await self.repository.create(**kwargs)

    async def delete(self, *, chat_id: int, user_id: int) -> bool:
        self.delete_calls.append({"chat_id": chat_id, "user_id": user_id})
        raise RuntimeError("pending delete failed")

    async def get_ttl(self, *, chat_id: int, user_id: int) -> int | None:
        return await self.repository.get_ttl(chat_id=chat_id, user_id=user_id)


class FailingVerifiedUserRepository:
    async def mark_verified(self, *, chat_id: int, user_id: int) -> None:
        raise RuntimeError("verified write failed")

    async def is_verified(self, *, chat_id: int, user_id: int) -> bool:
        return False


@dataclass
class FakeCallbackQuery:
    data: str
    from_user: Any
    message: Any
    answers: list[dict[str, Any]] = field(default_factory=list)

    async def answer(self, **kwargs: Any) -> None:
        self.answers.append(kwargs)


async def sleep_forever() -> bool:
    await asyncio.sleep(60)
    return True
