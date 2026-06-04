"""Tests for startup restoration of pending verification timers"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.bootstrap.verification_timer import restore_pending_verification_timer
from app.config import Settings
from app.domain import ActionMode
from app.infrastructure.redis import (
    PendingVerificationRepository,
    VerifiedUserRepository,
)
from app.usecase.verification import VerificationTaskRegistry
from app.usecase.verification.message import build_verification_timeout_message
from tests.support.verification import FakeRedis


def build_settings() -> Settings:
    return Settings(
        bot_token="token",
        redis_url="redis://redis:6379/0",
        verify_timeout_seconds=180,
        action_mode=ActionMode.NOTIFY_ADMIN,
        admin_username="@admin",
        llm_api_key="llm-token",
        llm_base_url="https://api.example.com/v1",
        llm_model="model",
        llm_timeout_seconds=8,
        log_file="spam.log",
    )


class FakeBot:
    def __init__(self, *, member_status: str = "left") -> None:
        self.member_status = member_status
        self.member_lookups: list[dict[str, int]] = []
        self.sent_messages: list[dict[str, object]] = []
        self.deleted_messages: list[dict[str, int]] = []
        self.declined_join_requests: list[dict[str, int]] = []
        self.bans: list[dict[str, int]] = []
        self.unbans: list[dict[str, int]] = []

    async def get_chat_member(self, **kwargs: int) -> SimpleNamespace:
        self.member_lookups.append(kwargs)
        return SimpleNamespace(status=self.member_status)

    async def send_message(self, **kwargs: object) -> None:
        self.sent_messages.append(kwargs)

    async def delete_message(self, **kwargs: int) -> None:
        self.deleted_messages.append(kwargs)

    async def decline_chat_join_request(self, **kwargs: int) -> None:
        self.declined_join_requests.append(kwargs)

    async def ban_chat_member(self, **kwargs: int) -> None:
        self.bans.append(kwargs)

    async def unban_chat_member(self, **kwargs: int) -> None:
        self.unbans.append(kwargs)


def test_restore_skips_pending_record_when_user_is_already_verified() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=240)
        verified_repository = VerifiedUserRepository(redis)
        registry = VerificationTaskRegistry()
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
        )
        await verified_repository.mark_verified(chat_id=-100123, user_id=42)

        restored = await restore_pending_verification_timer(
            redis_client=redis,
            bot=FakeBot(),
            pending_verification_repository=pending_repository,
            verified_user_repository=verified_repository,
            verification_task_registry=registry,
            settings=build_settings(),
        )

        assert restored == 0
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert registry.timeout_task == {}

    asyncio.run(run())


def test_restore_skips_join_request_pending_record_when_user_already_joined() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=240)
        registry = VerificationTaskRegistry()
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        bot = FakeBot(member_status="member")

        restored = await restore_pending_verification_timer(
            redis_client=redis,
            bot=bot,
            pending_verification_repository=pending_repository,
            verification_task_registry=registry,
            settings=build_settings(),
        )

        assert restored == 0
        assert bot.member_lookups == [{"chat_id": -100123, "user_id": 42}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert registry.timeout_task == {}

    asyncio.run(run())


def test_restored_join_request_timeout_message_uses_configured_timeout() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=240)
        registry = VerificationTaskRegistry()
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        key = PendingVerificationRepository.key(-100123, 42)
        payload = json.loads(redis.values[key])
        payload["created_at"] = (datetime.now(UTC) - timedelta(seconds=181)).isoformat()
        redis.values[key] = json.dumps(payload, ensure_ascii=False)
        bot = FakeBot(member_status="left")

        restored = await restore_pending_verification_timer(
            redis_client=redis,
            bot=bot,
            pending_verification_repository=pending_repository,
            verification_task_registry=registry,
            settings=build_settings(),
        )
        removed = await registry.timeout_task[(-100123, 42)]

        assert restored == 1
        assert removed is True
        assert bot.sent_messages == [
            {
                "chat_id": 4242,
                "text": build_verification_timeout_message(timeout_seconds=180),
            }
        ]
        assert bot.declined_join_requests == [{"chat_id": -100123, "user_id": 42}]
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None

    asyncio.run(run())
