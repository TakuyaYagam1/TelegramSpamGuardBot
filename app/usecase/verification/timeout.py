"""Verification timeout usecases for unverified members and join requests"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from typing import Any

from app.bot.util.telegram_api import call_telegram_api
from app.domain import PendingVerification
from app.observability.logging import get_logger, log_app_event
from app.usecase.contract import PendingVerificationStore
from app.usecase.verification.message import build_verification_timeout_message
from app.usecase.verification.task import (
    cancel_verification_task,
    register_verification_task,
)


async def call_telegram_api_best_effort(
    *,
    operation: str,
    call: Any,
    chat_id: int,
    user_id: int,
    logger: logging.Logger,
) -> None:
    try:
        await call_telegram_api(
            operation=operation,
            call=call,
            chat_id=chat_id,
            user_id=user_id,
            logger=logger,
        )
    except Exception:
        return


async def remove_unverified_user_after_timeout(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    await asyncio.sleep(timeout_seconds)

    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is None:
        return False

    event_logger = logger or get_logger("app")
    await call_telegram_api(
        operation="verification_timeout_ban",
        call=bot.ban_chat_member(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    await call_telegram_api(
        operation="verification_timeout_unban",
        call=bot.unban_chat_member(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    await pending_verification_repository.delete(chat_id=chat_id, user_id=user_id)
    cancel_verification_task(
        task_registry=countdown_task_registry,
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
        event="verification_timeout_removed",
        chat_id=chat_id,
        user_id=user_id,
        action="ban_unban",
        details="unverified user removed after verification timeout",
    )
    return True


async def block_unverified_join_request_after_timeout(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    await asyncio.sleep(timeout_seconds)

    pending = await pending_verification_repository.get(
        chat_id=chat_id, user_id=user_id
    )
    if pending is None:
        return False

    event_logger = logger or get_logger("app")
    if pending.verification_chat_id is not None:
        await call_telegram_api_best_effort(
            operation="send_verification_timeout_message",
            call=bot.send_message(
                chat_id=pending.verification_chat_id,
                text=build_verification_timeout_message(
                    timeout_seconds=timeout_seconds
                ),
            ),
            chat_id=chat_id,
            user_id=user_id,
            logger=event_logger,
        )
    await call_telegram_api_best_effort(
        operation="verification_timeout_decline_join_request",
        call=bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    await call_telegram_api_best_effort(
        operation="verification_timeout_ban_join_request",
        call=bot.ban_chat_member(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    await call_telegram_api_best_effort(
        operation="verification_timeout_unban_join_request",
        call=bot.unban_chat_member(chat_id=chat_id, user_id=user_id),
        chat_id=chat_id,
        user_id=user_id,
        logger=event_logger,
    )
    await pending_verification_repository.delete(chat_id=chat_id, user_id=user_id)
    cancel_verification_task(
        task_registry=countdown_task_registry,
        chat_id=chat_id,
        user_id=user_id,
    )

    log_app_event(
        event_logger,
        event="verification_timeout_blocked",
        chat_id=chat_id,
        user_id=user_id,
        action="decline_ban_unban",
        details="join request user removed after verification timeout",
    )
    return True


async def delete_pending_verification_message(
    *,
    bot: Any,
    pending: PendingVerification,
    chat_id: int,
    user_id: int,
    logger: logging.Logger,
) -> None:
    await call_telegram_api_best_effort(
        operation="delete_verification_message",
        call=bot.delete_message(
            chat_id=pending.verification_chat_id or pending.chat_id,
            message_id=pending.verification_message_id,
        ),
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
    )


def schedule_unverified_user_removal(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> asyncio.Task[bool]:
    task = asyncio.create_task(
        remove_unverified_user_after_timeout(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            timeout_seconds=timeout_seconds,
            countdown_task_registry=countdown_task_registry,
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


def schedule_join_request_timeout(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
    logger: logging.Logger | None = None,
) -> asyncio.Task[bool]:
    task = asyncio.create_task(
        block_unverified_join_request_after_timeout(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            timeout_seconds=timeout_seconds,
            countdown_task_registry=countdown_task_registry,
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
