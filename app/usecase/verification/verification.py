"""Verification approval usecase for join requests and callback confirmation"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

from aiogram.types import ChatPermissions, Message

from app.bot.util.telegram_api import call_telegram_api
from app.domain import PendingVerification
from app.observability.logging import get_logger, log_app_event
from app.usecase.contract import (
    PendingVerificationStore,
    VerifiedUserStore,
)
from app.usecase.verification.message import (
    VERIFY_EXPIRED_CALLBACK_ANSWER,
    VERIFY_SUCCESS_CALLBACK_ANSWER,
    VERIFY_SUCCESS_PRIVATE_MESSAGE,
    VERIFY_WRONG_USER_CALLBACK_ANSWER,
    build_verification_message,
    parse_verify_callback_payload,
)
from app.usecase.verification.task import (
    cancel_verification_task,
    register_verification_task,
)
from app.usecase.verification.timeout import (
    call_telegram_api_best_effort,
    schedule_join_request_timeout,
    schedule_unverified_user_removal,
)

COUNTDOWN_INTERVAL_SECONDS = 1
UNVERIFIED_MEMBER_PERMISSIONS = ChatPermissions(can_send_messages=False)
VERIFIED_MEMBER_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_react_to_messages=True,
)


async def send_verification_message(
    bot: Any,
    *,
    chat_id: int,
    user_id: int,
    user_full_name: str | None = None,
    message_thread_id: int | None = None,
    timeout_seconds: int = 180,
) -> Message:
    verification_message = build_verification_message(
        user_id=user_id,
        user_full_name=user_full_name,
        timeout_seconds=timeout_seconds,
    )
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": verification_message.text,
        "reply_markup": verification_message.reply_markup,
    }
    if message_thread_id is not None:
        kwargs["message_thread_id"] = message_thread_id

    return await call_telegram_api(
        operation="send_verification_message",
        call=bot.send_message(**kwargs),
        chat_id=chat_id,
        user_id=user_id,
    )


async def send_join_request_verification_message(
    bot: Any,
    *,
    chat_id: int,
    user_chat_id: int,
    user_id: int,
    user_full_name: str | None = None,
    timeout_seconds: int = 180,
) -> Message:
    verification_message = build_verification_message(
        user_id=user_id,
        user_full_name=user_full_name,
        timeout_seconds=timeout_seconds,
        chat_id=chat_id,
    )
    return await call_telegram_api(
        operation="send_join_request_verification_message",
        call=bot.send_message(
            chat_id=user_chat_id,
            text=verification_message.text,
            reply_markup=verification_message.reply_markup,
        ),
        chat_id=chat_id,
        user_id=user_id,
    )


async def _complete_pending_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    verified_user_repository: VerifiedUserStore,
    chat_id: int,
    user_id: int,
    approve_join_request: bool = False,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
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
        await call_telegram_api_best_effort(
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

    await verified_user_repository.mark_verified(
        chat_id=pending.chat_id,
        user_id=pending.user_id,
    )
    await pending_verification_repository.delete(
        chat_id=pending.chat_id,
        user_id=pending.user_id,
    )
    cancel_verification_task(
        task_registry=task_registry,
        chat_id=pending.chat_id,
        user_id=pending.user_id,
    )
    cancel_verification_task(
        task_registry=countdown_task_registry,
        chat_id=pending.chat_id,
        user_id=pending.user_id,
    )
    await call_telegram_api_best_effort(
        operation="delete_verification_message",
        call=bot.delete_message(
            chat_id=pending.verification_chat_id or pending.chat_id,
            message_id=pending.verification_message_id,
        ),
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
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
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

    if _pending_verification_is_expired(pending, timeout_seconds=timeout_seconds):
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    completed = await _complete_pending_verification(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        verified_user_repository=verified_user_repository,
        chat_id=pending.chat_id,
        user_id=pending.user_id,
        approve_join_request=payload.chat_id is not None,
        task_registry=task_registry,
        countdown_task_registry=countdown_task_registry,
    )
    if not completed:
        await callback_query.answer(
            text=VERIFY_EXPIRED_CALLBACK_ANSWER, show_alert=True
        )
        return False

    await callback_query.answer(text=VERIFY_SUCCESS_CALLBACK_ANSWER)
    return True


def _pending_verification_is_expired(
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


async def restrict_unverified_member(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
    logger: logging.Logger,
) -> None:
    await call_telegram_api_best_effort(
        operation="restrict_unverified_member",
        call=bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=UNVERIFIED_MEMBER_PERMISSIONS,
        ),
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
    )


async def update_verification_countdown(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    user_full_name: str | None,
    timeout_seconds: int,
    join_request: bool = False,
    logger: logging.Logger | None = None,
) -> bool:
    event_logger = logger or get_logger("app")
    for remaining_seconds in range(timeout_seconds - 1, 0, -1):
        await asyncio.sleep(COUNTDOWN_INTERVAL_SECONDS)
        pending = await pending_verification_repository.get(
            chat_id=chat_id,
            user_id=user_id,
        )
        if pending is None:
            return False

        verification_message = build_verification_message(
            user_id=user_id,
            user_full_name=user_full_name,
            timeout_seconds=timeout_seconds,
            remaining_seconds=remaining_seconds,
            chat_id=chat_id if join_request else None,
        )
        await call_telegram_api_best_effort(
            operation="edit_verification_countdown",
            call=bot.edit_message_text(
                chat_id=pending.verification_chat_id or pending.chat_id,
                message_id=pending.verification_message_id,
                text=verification_message.text,
                reply_markup=verification_message.reply_markup,
            ),
            chat_id=chat_id,
            user_id=user_id,
            logger=event_logger,
        )
    return True


def schedule_verification_countdown(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    user_full_name: str | None,
    timeout_seconds: int,
    join_request: bool = False,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    logger: logging.Logger | None = None,
) -> asyncio.Task[bool]:
    task = asyncio.create_task(
        update_verification_countdown(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            user_full_name=user_full_name,
            timeout_seconds=timeout_seconds,
            join_request=join_request,
            logger=logger,
        )
    )
    register_verification_task(
        task=task,
        task_registry=task_registry,
        chat_id=chat_id,
        user_id=user_id,
    )
    return task


async def start_join_request_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    user_chat_id: int,
    user_full_name: str | None,
    timeout_seconds: int,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    event_logger = logger or get_logger("app")
    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is not None:
        return False

    sent_message = await send_join_request_verification_message(
        bot,
        chat_id=chat_id,
        user_chat_id=user_chat_id,
        user_id=user_id,
        user_full_name=user_full_name,
        timeout_seconds=timeout_seconds,
    )
    await pending_verification_repository.create(
        user_id=user_id,
        chat_id=chat_id,
        verification_message_id=int(sent_message.message_id),
        verification_chat_id=user_chat_id,
    )
    schedule_join_request_timeout(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        task_registry=task_registry,
        countdown_task_registry=countdown_task_registry,
        logger=event_logger,
    )
    if countdown_task_registry is not None:
        schedule_verification_countdown(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            user_full_name=user_full_name,
            timeout_seconds=timeout_seconds,
            join_request=True,
            task_registry=countdown_task_registry,
            logger=event_logger,
        )
    log_app_event(
        event_logger,
        event="join_request_verification_started",
        chat_id=chat_id,
        user_id=user_id,
        action="send_private_challenge",
        details=f"user_chat_id={user_chat_id}",
    )
    return True


async def start_member_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    user_full_name: str | None,
    timeout_seconds: int,
    message_thread_id: int | None = None,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    event_logger = logger or get_logger("app")
    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is not None:
        return False

    await restrict_unverified_member(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    sent_message = await send_verification_message(
        bot,
        chat_id=chat_id,
        user_id=user_id,
        user_full_name=user_full_name,
        message_thread_id=message_thread_id,
        timeout_seconds=timeout_seconds,
    )
    await pending_verification_repository.create(
        user_id=user_id,
        chat_id=chat_id,
        verification_message_id=int(sent_message.message_id),
        message_thread_id=message_thread_id,
    )
    schedule_unverified_user_removal(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        task_registry=task_registry,
        countdown_task_registry=countdown_task_registry,
        logger=event_logger,
    )
    if countdown_task_registry is not None:
        schedule_verification_countdown(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            user_full_name=user_full_name,
            timeout_seconds=timeout_seconds,
            task_registry=countdown_task_registry,
            logger=event_logger,
        )
    log_app_event(
        event_logger,
        event="member_verification_started",
        chat_id=chat_id,
        user_id=user_id,
        action="restrict_and_send_group_challenge",
        details="normal member join fallback",
    )
    return True
