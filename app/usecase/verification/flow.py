"""Verification start and cleanup orchestration usecases"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from typing import Any

from app.observability.logging import get_logger, log_app_event
from app.usecase.contract import PendingVerificationStore
from app.usecase.verification.challenge import (
    send_join_request_verification_message,
    send_verification_message,
)
from app.usecase.verification.permission import restrict_unverified_member
from app.usecase.verification.task import cancel_verification_task
from app.usecase.verification.timeout import (
    ban_unban_user_best_effort,
    call_telegram_api_best_effort,
    delete_pending_verification_message,
    delete_verification_message_best_effort,
    schedule_join_request_timeout,
    schedule_unverified_user_removal,
)


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
    logger: logging.Logger | None = None,
) -> bool:
    event_logger = logger or get_logger("app")
    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is not None:
        return False

    verification_message_id: int | None = None
    try:
        sent_message = await send_join_request_verification_message(
            bot,
            chat_id=chat_id,
            user_chat_id=user_chat_id,
            user_id=user_id,
            user_full_name=user_full_name,
            timeout_seconds=timeout_seconds,
        )
        verification_message_id = int(sent_message.message_id)
        await pending_verification_repository.create(
            user_id=user_id,
            chat_id=chat_id,
            verification_message_id=verification_message_id,
            verification_chat_id=user_chat_id,
        )
    except Exception:
        await cleanup_failed_join_request_verification_start(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            user_chat_id=user_chat_id,
            verification_message_id=verification_message_id,
            logger=event_logger,
        )
        raise
    schedule_join_request_timeout(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        configured_timeout_seconds=timeout_seconds,
        task_registry=task_registry,
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


async def cleanup_failed_join_request_verification_start(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
    user_chat_id: int,
    verification_message_id: int | None,
    logger: logging.Logger,
) -> None:
    if verification_message_id is not None:
        await delete_verification_message_best_effort(
            bot=bot,
            target_chat_id=user_chat_id,
            message_id=verification_message_id,
            operation="delete_failed_join_request_verification_message",
            chat_id=chat_id,
            user_id=user_id,
            logger=logger,
        )

    await call_telegram_api_best_effort(
        operation="failed_join_request_verification_start_decline",
        call=bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
    )


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
    logger: logging.Logger | None = None,
) -> bool:
    event_logger = logger or get_logger("app")
    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is not None:
        return False

    verification_message_id: int | None = None
    try:
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
        verification_message_id = int(sent_message.message_id)
        await pending_verification_repository.create(
            user_id=user_id,
            chat_id=chat_id,
            verification_message_id=verification_message_id,
            message_thread_id=message_thread_id,
        )
    except Exception:
        await cleanup_failed_member_verification_start(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            verification_message_id=verification_message_id,
            logger=event_logger,
        )
        raise

    schedule_unverified_user_removal(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        task_registry=task_registry,
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


async def cleanup_failed_member_verification_start(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
    verification_message_id: int | None,
    logger: logging.Logger,
) -> None:
    if verification_message_id is not None:
        await delete_verification_message_best_effort(
            bot=bot,
            target_chat_id=chat_id,
            message_id=verification_message_id,
            operation="delete_failed_verification_message",
            chat_id=chat_id,
            user_id=user_id,
            logger=logger,
        )

    await ban_unban_user_best_effort(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
        ban_operation="failed_verification_start_ban",
        unban_operation="failed_verification_start_unban",
    )


async def cleanup_pending_member_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    pending = await pending_verification_repository.get(
        chat_id=chat_id,
        user_id=user_id,
    )
    if pending is None:
        return False

    event_logger = logger or get_logger("app")
    await pending_verification_repository.delete(chat_id=chat_id, user_id=user_id)
    cancel_verification_task(
        task_registry=task_registry,
        chat_id=chat_id,
        user_id=user_id,
    )
    await delete_pending_verification_message(
        bot=bot,
        pending=pending,
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    log_app_event(
        event_logger,
        event="member_verification_cleanup",
        chat_id=chat_id,
        user_id=user_id,
        action="delete_challenge",
        details="pending verification removed after member left before approval",
    )
    return True
