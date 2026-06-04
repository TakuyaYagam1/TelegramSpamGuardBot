from __future__ import annotations

import asyncio

from app.domain import PendingVerification
from app.usecase.verification import (
    VERIFY_BUTTON_TEXT,
    VerificationTaskRegistry,
    build_verification_message,
    build_verification_timeout_message,
)
from app.usecase.verification.approval import pending_verification_is_expired
from app.usecase.verification.task import register_verification_task
from tests.support.verification import (
    sleep_forever as _sleep_forever,
)


def test_verification_message_uses_clear_emoji_statuses() -> None:
    message = build_verification_message(
        user_id=42,
        user_full_name="Test User",
        timeout_seconds=180,
        chat_id=-100123,
    )

    assert message.text.startswith("⚠️ Test User")
    assert VERIFY_BUTTON_TEXT == "✅ Я человек"
    assert message.reply_markup.inline_keyboard[0][0].text == "✅ Я человек"
    assert "У вас 3 минуты" in message.text
    assert "Осталось" not in message.text
    assert build_verification_timeout_message(timeout_seconds=180).startswith("❌")


def test_verification_task_registry_cancel_all_tasks() -> None:
    async def run() -> None:
        registries = VerificationTaskRegistry()
        timeout_task = asyncio.create_task(_sleep_forever())
        registries.timeout_task[(-100123, 42)] = timeout_task

        await registries.cancel_all()

        assert registries.timeout_task == {}
        assert timeout_task.cancelled()

    asyncio.run(run())


def test_failed_verification_task_clears_registry_entry() -> None:
    async def run() -> None:
        async def fail() -> bool:
            raise RuntimeError("redis failed")

        registry = VerificationTaskRegistry()
        task = asyncio.create_task(fail())
        register_verification_task(
            task=task,
            task_registry=registry.timeout_task,
            chat_id=-100123,
            user_id=42,
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert registry.timeout_task == {}

    asyncio.run(run())


def test_pending_verification_with_invalid_created_at_is_expired() -> None:
    pending = PendingVerification(
        user_id=42,
        chat_id=-100123,
        verification_message_id=777,
        created_at="not-a-date",
    )

    assert pending_verification_is_expired(pending, timeout_seconds=180) is True
