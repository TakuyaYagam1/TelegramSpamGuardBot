from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.bot.controller.v1.verification import handle_chat_member_update
from app.infrastructure.redis import (
    PendingVerificationRepository,
)
from app.usecase.verification import (
    VerificationTaskRegistry,
    block_unverified_join_request_after_timeout,
    build_verification_timeout_message,
    cleanup_pending_member_verification,
    remove_unverified_user_after_timeout,
)
from tests.support.verification import (
    FailingUnbanBot,
    FakeBot,
    FakeRedis,
)
from tests.support.verification import (
    sleep_forever as _sleep_forever,
)


def test_timeout_removes_unverified_user_with_mocked_bot() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=None,
        )
        bot = FakeBot()

        removed = await remove_unverified_user_after_timeout(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            timeout_seconds=0,
        )

        assert removed is True
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None

    asyncio.run(run())


def test_timeout_cleans_pending_even_when_unban_fails() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=None,
        )
        bot = FailingUnbanBot()

        removed = await remove_unverified_user_after_timeout(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            timeout_seconds=0,
        )

        assert removed is True
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == [{"chat_id": -100123, "message_id": 777}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None

    asyncio.run(run())


def test_join_request_timeout_declines_kicks_and_cleans_pending() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        bot = FakeBot()

        removed = await block_unverified_join_request_after_timeout(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            timeout_seconds=0,
        )

        assert removed is True
        assert bot.sent_messages == [
            {
                "chat_id": 4242,
                "text": build_verification_timeout_message(timeout_seconds=0),
            }
        ]
        assert bot.declined_join_requests == [{"chat_id": -100123, "user_id": 42}]
        assert bot.bans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.unbans == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == [{"chat_id": 4242, "message_id": 888}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None

    asyncio.run(run())


def test_cleanup_pending_member_verification_deletes_challenge_and_cancels_tasks() -> (
    None
):
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=None,
        )
        timeout_task = asyncio.create_task(_sleep_forever())
        timeout_tasks = {(-100123, 42): timeout_task}
        bot = FakeBot()

        cleaned = await cleanup_pending_member_verification(
            bot=bot,
            pending_verification_repository=pending_repository,
            chat_id=-100123,
            user_id=42,
            task_registry=timeout_tasks,
        )

        assert cleaned is True
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert bot.deleted_messages == [{"chat_id": -100123, "message_id": 777}]
        assert timeout_tasks == {}
        assert timeout_task.cancelled() or timeout_task.cancelling() > 0

    asyncio.run(run())


def test_chat_member_leave_update_cleans_pending_verification_challenge() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=None,
        )
        registries = VerificationTaskRegistry()
        registries.timeout_task[(-100123, 42)] = asyncio.create_task(_sleep_forever())
        bot = FakeBot()
        update = SimpleNamespace(
            chat=SimpleNamespace(id=-100123),
            old_chat_member=SimpleNamespace(
                status="restricted",
                user=SimpleNamespace(id=42, is_bot=False, full_name="Test User"),
            ),
            new_chat_member=SimpleNamespace(
                status="left",
                user=SimpleNamespace(id=42, is_bot=False, full_name="Test User"),
            ),
        )

        cleaned = await handle_chat_member_update(
            update=update,
            bot=bot,
            pending_verification_repository=pending_repository,
            settings=SimpleNamespace(verify_timeout_seconds=180),
            verification_task_registry=registries,
        )

        assert cleaned is True
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert bot.deleted_messages == [{"chat_id": -100123, "message_id": 777}]
        assert registries.timeout_task == {}

    asyncio.run(run())
