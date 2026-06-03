"""Verification countdown edit usecases"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from typing import Any

from app.observability.logging import get_logger
from app.usecase.contract import PendingVerificationStore
from app.usecase.verification.message import build_verification_message
from app.usecase.verification.task import register_verification_task
from app.usecase.verification.timeout import call_telegram_api_best_effort

COUNTDOWN_INTERVAL_SECONDS = 1


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
