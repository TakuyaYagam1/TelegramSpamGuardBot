"""Verification callback approval usecases"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

from app.bot.util.telegram_api import call_telegram_api
from app.domain import PendingVerification
from app.observability.logging import get_logger, log_app_event
from app.usecase.contract import PendingVerificationStore, VerifiedUserStore
from app.usecase.verification.message import (
    VERIFY_EXPIRED_CALLBACK_ANSWER,
    VERIFY_SUCCESS_CALLBACK_ANSWER,
    VERIFY_SUCCESS_PRIVATE_MESSAGE,
    VERIFY_WRONG_USER_CALLBACK_ANSWER,
    parse_verify_callback_payload,
)
from app.usecase.verification.permission import VERIFIED_MEMBER_PERMISSIONS
from app.usecase.verification.task import cancel_verification_task
from app.usecase.verification.timeout import (
    call_telegram_api_best_effort,
    delete_verification_message_best_effort,
)


async def complete_pending_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    verified_user_repository: VerifiedUserStore,
    chat_id: int,
    user_id: int,
    approve_join_request: bool = False,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
) -> bool:
    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is None:
        return False

    if approve_join_request:
        await call_telegram_api(
            operation="approve_chat_join_request",
            call=bot.approve_chat_join_request(
                chat_id=pending.chat_id,
                user_id=pending.user_id,
            ),
            chat_id=pending.chat_id,
            user_id=pending.user_id,
        )
    else:
        await call_telegram_api(
            operation="restore_verified_member_permissions",
            call=bot.restrict_chat_member(
                chat_id=pending.chat_id,
                user_id=pending.user_id,
                permissions=VERIFIED_MEMBER_PERMISSIONS,
            ),
            chat_id=pending.chat_id,
            user_id=pending.user_id,
            logger=get_logger("app"),
        )

    try:
        cancel_verification_task(
            task_registry=task_registry,
            chat_id=pending.chat_id,
            user_id=pending.user_id,
        )
        try:
            await verified_user_repository.mark_verified(
                chat_id=pending.chat_id,
                user_id=pending.user_id,
            )
        except Exception as exc:
            log_app_event(
                get_logger("app"),
                event="verified_user_mark_failed",
                chat_id=pending.chat_id,
                user_id=pending.user_id,
                action="mark_verified",
                details=f"error_type={type(exc).__name__}",
                level=logging.ERROR,
            )
    finally:
        await delete_pending_verification_best_effort(
            pending_verification_repository=pending_verification_repository,
            pending=pending,
        )
        await delete_verification_message_best_effort(
            bot=bot,
            target_chat_id=pending.verification_chat_id or pending.chat_id,
            message_id=pending.verification_message_id,
            operation="delete_verification_message",
            chat_id=pending.chat_id,
            user_id=pending.user_id,
            logger=get_logger("app"),
        )
        if pending.verification_chat_id is not None:
            await call_telegram_api_best_effort(
                operation="send_verification_success_message",
                call=bot.send_message(
                    chat_id=pending.verification_chat_id,
                    text=VERIFY_SUCCESS_PRIVATE_MESSAGE,
                ),
                chat_id=pending.chat_id,
                user_id=pending.user_id,
                logger=get_logger("app"),
            )
    return True


async def complete_verification_from_callback(
    *,
    callback_query: Any,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    verified_user_repository: VerifiedUserStore,
    timeout_seconds: int | None = None,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
) -> bool:
    payload = parse_verify_callback_payload(getattr(callback_query, "data", None))
    from_user = getattr(callback_query, "from_user", None)
    callback_user_id = getattr(from_user, "id", None)

    if payload is None or callback_user_id is None:
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    if payload.user_id != callback_user_id:
        await callback_query.answer(
            text=VERIFY_WRONG_USER_CALLBACK_ANSWER,
            show_alert=True,
        )
        return False

    chat_id = payload.chat_id
    if chat_id is None:
        message = getattr(callback_query, "message", None)
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)

    if chat_id is None:
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    pending = await pending_verification_repository.get(
        chat_id=int(chat_id),
        user_id=payload.user_id,
    )
    if pending is None:
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    if pending_verification_is_expired(pending, timeout_seconds=timeout_seconds):
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    completed = await complete_pending_verification(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        verified_user_repository=verified_user_repository,
        chat_id=pending.chat_id,
        user_id=pending.user_id,
        approve_join_request=payload.chat_id is not None,
        task_registry=task_registry,
    )
    if not completed:
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    await callback_query.answer(text=VERIFY_SUCCESS_CALLBACK_ANSWER)
    return True


async def delete_pending_verification_best_effort(
    *,
    pending_verification_repository: PendingVerificationStore,
    pending: PendingVerification,
) -> None:
    try:
        await pending_verification_repository.delete(
            chat_id=pending.chat_id,
            user_id=pending.user_id,
        )
    except Exception as exc:
        log_app_event(
            get_logger("app"),
            event="pending_verification_delete_failed",
            chat_id=pending.chat_id,
            user_id=pending.user_id,
            action="delete_pending_verification",
            details=f"error_type={type(exc).__name__}",
            level=logging.ERROR,
        )


def pending_verification_is_expired(
    pending: PendingVerification,
    *,
    timeout_seconds: int | None,
) -> bool:
    if timeout_seconds is None:
        return False

    try:
        created_at = datetime.fromisoformat(pending.created_at)
    except TypeError, ValueError:
        return True

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    elapsed_seconds = (datetime.now(UTC) - created_at.astimezone(UTC)).total_seconds()
    return elapsed_seconds >= timeout_seconds
