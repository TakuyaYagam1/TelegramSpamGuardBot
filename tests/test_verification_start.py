from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.redis import (
    PendingVerificationRepository,
)
from app.usecase.verification import (
    start_join_request_verification,
    start_member_verification,
)
from tests.support.verification import (
    FailingCreatePendingRepository,
    FailingRestrictBot,
    FailingVerificationMessageBot,
    FakeBot,
    FakeRedis,
)


def test_start_member_verification_restricts_and_sends_group_challenge() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        bot = FakeBot()
        task_registry: dict[tuple[int, int], asyncio.Task[bool]] = {}

        started = await start_member_verification(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            user_full_name="Test User",
            timeout_seconds=180,
            task_registry=task_registry,
        )

        assert started is True
        assert bot.restrictions[0]["chat_id"] == -100123
        assert bot.restrictions[0]["user_id"] == 42
        assert bot.restrictions[0]["permissions"].can_send_messages is False
        assert bot.sent_messages[0]["chat_id"] == -100123
        assert str(bot.sent_messages[0]["text"]).startswith("⚠️ Test User")
        assert await pending_repository.get(chat_id=-100123, user_id=42) is not None
        assert (-100123, 42) in task_registry

        for task in task_registry.values():
            task.cancel()

    asyncio.run(run())


def test_start_member_verification_kicks_user_when_challenge_send_fails() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        bot = FailingVerificationMessageBot()

        with pytest.raises(RuntimeError, match="send failed"):
            await start_member_verification(
                bot=bot,
                pending_verification_repository=pending_repository,
                chat_id=-100123,
                user_id=42,
                user_full_name="Test User",
                timeout_seconds=180,
            )

        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert bot.restrictions[0]["permissions"].can_send_messages is False
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == []

    asyncio.run(run())


def test_start_member_verification_kicks_user_when_restrict_fails() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        bot = FailingRestrictBot()

        with pytest.raises(RuntimeError, match="restrict failed"):
            await start_member_verification(
                bot=bot,
                pending_verification_repository=pending_repository,
                chat_id=-100123,
                user_id=42,
                user_full_name="Test User",
                timeout_seconds=180,
            )

        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert bot.restrictions[0]["permissions"].can_send_messages is False
        assert bot.sent_messages == []
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]

    asyncio.run(run())


def test_start_member_verification_cleans_challenge_when_pending_create_fails() -> None:
    async def run() -> None:
        bot = FakeBot()

        with pytest.raises(RuntimeError, match="redis failed"):
            await start_member_verification(
                bot=bot,
                pending_verification_repository=FailingCreatePendingRepository(),
                chat_id=-100123,
                user_id=42,
                user_full_name="Test User",
                timeout_seconds=180,
            )

        assert bot.sent_messages[0]["chat_id"] == -100123
        assert bot.deleted_messages == [{"chat_id": -100123, "message_id": 888}]
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]

    asyncio.run(run())


def test_start_join_request_verification_sends_private_challenge() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        task_registry: dict[tuple[int, int], asyncio.Task[bool]] = {}
        bot = FakeBot()

        started = await start_join_request_verification(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            user_chat_id=4242,
            user_full_name="Test User",
            timeout_seconds=180,
            task_registry=task_registry,
        )

        pending = await pending_repository.get(chat_id=-100123, user_id=42)
        assert started is True
        assert pending is not None
        assert pending.verification_message_id == 888
        assert pending.verification_chat_id == 4242
        assert bot.sent_messages[0]["chat_id"] == 4242
        assert str(bot.sent_messages[0]["text"]).startswith("⚠️ Test User")
        assert (
            bot.sent_messages[0]["reply_markup"].inline_keyboard[0][0].text
            == "✅ Я человек"
        )
        assert task_registry.keys() == {(-100123, 42)}

        task = task_registry.pop((-100123, 42))
        task.cancel()

    asyncio.run(run())


def test_start_join_request_verification_declines_when_challenge_send_fails() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        bot = FailingVerificationMessageBot()

        with pytest.raises(RuntimeError, match="send failed"):
            await start_join_request_verification(
                bot=bot,
                pending_verification_repository=pending_repository,
                chat_id=-100123,
                user_id=42,
                user_chat_id=4242,
                user_full_name="Test User",
                timeout_seconds=180,
            )

        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert bot.deleted_messages == []
        assert bot.declined_join_requests == [{"chat_id": -100123, "user_id": 42}]

    asyncio.run(run())


def test_start_join_request_verification_cleans_challenge_when_pending_create_fails() -> (
    None
):
    async def run() -> None:
        bot = FakeBot()

        with pytest.raises(RuntimeError, match="redis failed"):
            await start_join_request_verification(
                bot=bot,
                pending_verification_repository=FailingCreatePendingRepository(),
                chat_id=-100123,
                user_id=42,
                user_chat_id=4242,
                user_full_name="Test User",
                timeout_seconds=180,
            )

        assert bot.sent_messages[0]["chat_id"] == 4242
        assert bot.deleted_messages == [{"chat_id": 4242, "message_id": 888}]
        assert bot.declined_join_requests == [{"chat_id": -100123, "user_id": 42}]

    asyncio.run(run())
