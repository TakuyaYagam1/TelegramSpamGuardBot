from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.infrastructure.redis import (
    PendingVerificationRepository,
    VerifiedUserRepository,
)
from app.usecase.verification import (
    VERIFY_EXPIRED_CALLBACK_ANSWER,
    VERIFY_SUCCESS_CALLBACK_ANSWER,
    VERIFY_SUCCESS_PRIVATE_MESSAGE,
    complete_verification_from_callback,
)
from tests.support.verification import (
    FailingDeletePendingRepository,
    FailingRestorePermissionsBot,
    FailingVerifiedUserRepository,
    FakeBot,
    FakeCallbackQuery,
    FakeRedis,
)
from tests.support.verification import (
    sleep_forever as _sleep_forever,
)


def test_complete_verification_from_callback_marks_verified_and_cleans_pending() -> (
    None
):
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        verified_repository = VerifiedUserRepository(redis)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=555,
        )
        task = asyncio.create_task(_sleep_forever())
        task_registry = {(-100123, 42): task}
        callback = FakeCallbackQuery(
            data="verify_user:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=-100123)),
        )
        bot = FakeBot()

        completed = await complete_verification_from_callback(
            callback_query=callback,
            bot=bot,
            pending_verification_repository=pending_repository,
            verified_user_repository=verified_repository,
            task_registry=task_registry,
        )

        assert completed is True
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert await verified_repository.is_verified(chat_id=-100123, user_id=42)
        assert bot.restrictions[0]["chat_id"] == -100123
        assert bot.restrictions[0]["user_id"] == 42
        assert bot.restrictions[0]["permissions"].can_send_messages is True
        assert bot.deleted_messages == [{"chat_id": -100123, "message_id": 777}]
        assert bot.sent_messages == []
        assert callback.answers == [{"text": VERIFY_SUCCESS_CALLBACK_ANSWER}]
        assert task_registry == {}
        assert task.cancelled() or task.cancelling() > 0

    asyncio.run(run())


def test_complete_member_verification_keeps_pending_when_restore_fails() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        verified_repository = VerifiedUserRepository(redis)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=555,
        )
        task = asyncio.create_task(_sleep_forever())
        task_registry = {(-100123, 42): task}
        callback = FakeCallbackQuery(
            data="verify_user:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=-100123)),
        )
        bot = FailingRestorePermissionsBot()

        with pytest.raises(RuntimeError, match="restore failed"):
            await complete_verification_from_callback(
                callback_query=callback,
                bot=bot,
                pending_verification_repository=pending_repository,
                verified_user_repository=verified_repository,
                task_registry=task_registry,
            )

        assert await pending_repository.get(chat_id=-100123, user_id=42) is not None
        assert not await verified_repository.is_verified(chat_id=-100123, user_id=42)
        assert bot.restrictions[0]["permissions"].can_send_messages is True
        assert bot.deleted_messages == []
        assert callback.answers == []
        assert task_registry == {(-100123, 42): task}
        assert not task.cancelled()
        task.cancel()

    asyncio.run(run())


def test_expired_callback_is_rejected_even_when_pending_key_still_exists() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=240)
        verified_repository = VerifiedUserRepository(redis)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=777,
            message_thread_id=555,
        )
        key = PendingVerificationRepository.key(-100123, 42)
        payload = json.loads(redis.values[key])
        payload["created_at"] = (datetime.now(UTC) - timedelta(seconds=181)).isoformat()
        redis.values[key] = json.dumps(payload, ensure_ascii=False)
        callback = FakeCallbackQuery(
            data="verify_user:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=-100123)),
        )
        bot = FakeBot()

        completed = await complete_verification_from_callback(
            callback_query=callback,
            bot=bot,
            pending_verification_repository=pending_repository,
            verified_user_repository=verified_repository,
            timeout_seconds=180,
        )

        assert completed is False
        assert not await verified_repository.is_verified(chat_id=-100123, user_id=42)
        assert bot.restrictions == []
        assert callback.answers == [
            {"text": VERIFY_EXPIRED_CALLBACK_ANSWER, "show_alert": True}
        ]

    asyncio.run(run())


def test_join_request_callback_approves_user_and_deletes_private_challenge() -> None:
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        verified_repository = VerifiedUserRepository(redis)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        task = asyncio.create_task(_sleep_forever())
        task_registry = {(-100123, 42): task}
        callback = FakeCallbackQuery(
            data="verify_user:-100123:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=4242)),
        )
        bot = FakeBot()

        completed = await complete_verification_from_callback(
            callback_query=callback,
            bot=bot,
            pending_verification_repository=pending_repository,
            verified_user_repository=verified_repository,
            task_registry=task_registry,
        )

        assert completed is True
        assert bot.approved_join_requests == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == [{"chat_id": 4242, "message_id": 888}]
        assert bot.sent_messages == [
            {"chat_id": 4242, "text": VERIFY_SUCCESS_PRIVATE_MESSAGE}
        ]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert await verified_repository.is_verified(chat_id=-100123, user_id=42)
        assert callback.answers == [{"text": VERIFY_SUCCESS_CALLBACK_ANSWER}]
        assert task_registry == {}
        assert task.cancelled() or task.cancelling() > 0

    asyncio.run(run())


def test_join_request_callback_cleans_pending_after_telegram_approval_even_if_verified_write_fails() -> (
    None
):
    async def run() -> None:
        redis = FakeRedis()
        pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        task = asyncio.create_task(_sleep_forever())
        task_registry = {(-100123, 42): task}
        callback = FakeCallbackQuery(
            data="verify_user:-100123:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=4242)),
        )
        bot = FakeBot()

        completed = await complete_verification_from_callback(
            callback_query=callback,
            bot=bot,
            pending_verification_repository=pending_repository,
            verified_user_repository=FailingVerifiedUserRepository(),
            task_registry=task_registry,
        )

        assert completed is True
        assert bot.approved_join_requests == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == [{"chat_id": 4242, "message_id": 888}]
        assert bot.sent_messages == [
            {"chat_id": 4242, "text": VERIFY_SUCCESS_PRIVATE_MESSAGE}
        ]
        assert callback.answers == [{"text": VERIFY_SUCCESS_CALLBACK_ANSWER}]
        assert await pending_repository.get(chat_id=-100123, user_id=42) is None
        assert task_registry == {}
        assert task.cancelled() or task.cancelling() > 0

    asyncio.run(run())


def test_join_request_callback_finishes_when_pending_cleanup_fails_after_approval() -> (
    None
):
    async def run() -> None:
        redis = FakeRedis()
        real_pending_repository = PendingVerificationRepository(redis, ttl_seconds=180)
        pending_repository = FailingDeletePendingRepository(real_pending_repository)
        verified_repository = VerifiedUserRepository(redis)
        await pending_repository.create(
            user_id=42,
            chat_id=-100123,
            verification_message_id=888,
            verification_chat_id=4242,
        )
        task = asyncio.create_task(_sleep_forever())
        task_registry = {(-100123, 42): task}
        callback = FakeCallbackQuery(
            data="verify_user:-100123:42",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=4242)),
        )
        bot = FakeBot()

        completed = await complete_verification_from_callback(
            callback_query=callback,
            bot=bot,
            pending_verification_repository=pending_repository,
            verified_user_repository=verified_repository,
            task_registry=task_registry,
        )

        assert completed is True
        assert pending_repository.delete_calls == [{"chat_id": -100123, "user_id": 42}]
        assert bot.approved_join_requests == [{"chat_id": -100123, "user_id": 42}]
        assert bot.deleted_messages == [{"chat_id": 4242, "message_id": 888}]
        assert bot.sent_messages == [
            {"chat_id": 4242, "text": VERIFY_SUCCESS_PRIVATE_MESSAGE}
        ]
        assert (
            await real_pending_repository.get(chat_id=-100123, user_id=42) is not None
        )
        assert await verified_repository.is_verified(chat_id=-100123, user_id=42)
        assert callback.answers == [{"text": VERIFY_SUCCESS_CALLBACK_ANSWER}]
        assert task_registry == {}
        assert task.cancelled() or task.cancelling() > 0

    asyncio.run(run())
