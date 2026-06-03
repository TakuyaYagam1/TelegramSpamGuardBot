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
from app.usecase.verification.countdown import schedule_verification_countdown
from app.usecase.verification.permission import restrict_unverified_member
from app.usecase.verification.task import cancel_verification_task
from app.usecase.verification.timeout import (
    delete_pending_verification_message,
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


async def cleanup_pending_member_verification(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationStore,
    chat_id: int,
    user_id: int,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None = None,
    countdown_task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]]
    | None = None,
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
        event="member_verification_cleanup",
        chat_id=chat_id,
        user_id=user_id,
        action="delete_challenge",
        details="pending verification removed after member left before approval",
    )
    return True
