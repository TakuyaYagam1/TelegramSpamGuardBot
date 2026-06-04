"""Verification task registry helpers for timeout jobs"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from dataclasses import dataclass, field

from app.observability.logging import get_logger, log_app_event


@dataclass
class VerificationTaskRegistry:
    timeout_task: dict[tuple[int, int], asyncio.Task[bool]] = field(
        default_factory=dict
    )

    async def cancel_all(self) -> None:
        tasks = set(self.timeout_task.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.timeout_task.clear()


def cancel_verification_task(
    *,
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None,
    chat_id: int,
    user_id: int,
) -> None:
    if task_registry is None:
        return

    task = task_registry.pop((chat_id, user_id), None)
    if task is not None and not task.done():
        task.cancel()


def register_verification_task(
    *,
    task: asyncio.Task[bool],
    task_registry: MutableMapping[tuple[int, int], asyncio.Task[bool]] | None,
    chat_id: int,
    user_id: int,
    logger: logging.Logger | None = None,
) -> None:
    if task_registry is None:
        return

    key = (chat_id, user_id)
    previous_task = task_registry.get(key)
    if previous_task is not None and not previous_task.done():
        previous_task.cancel()
    task_registry[key] = task

    def remove_completed_task(completed_task: asyncio.Task[bool]) -> None:
        if task_registry.get(key) is completed_task:
            task_registry.pop(key, None)
        log_failed_verification_task(
            completed_task,
            chat_id=chat_id,
            user_id=user_id,
            logger=logger,
        )

    task.add_done_callback(remove_completed_task)


def log_failed_verification_task(
    completed_task: asyncio.Task[bool],
    *,
    chat_id: int,
    user_id: int,
    logger: logging.Logger | None,
) -> None:
    if completed_task.cancelled():
        return

    exception = completed_task.exception()
    if exception is None:
        return

    log_app_event(
        logger or get_logger("app"),
        event="verification_timeout_task_failed",
        chat_id=chat_id,
        user_id=user_id,
        action="run_verification_timeout_task",
        details=f"error_type={type(exception).__name__}",
        level=logging.ERROR,
    )
