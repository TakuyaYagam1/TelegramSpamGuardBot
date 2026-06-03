"""Verification task registry helpers for timeout and countdown jobs"""

from __future__ import annotations

import asyncio
from collections.abc import MutableMapping
from dataclasses import dataclass, field


@dataclass
class VerificationTaskRegistry:
    timeout_task: dict[tuple[int, int], asyncio.Task[bool]] = field(
        default_factory=dict
    )
    countdown_task: dict[tuple[int, int], asyncio.Task[bool]] = field(
        default_factory=dict
    )

    async def cancel_all(self) -> None:
        tasks = {
            task
            for registry in (self.timeout_task, self.countdown_task)
            for task in registry.values()
        }
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.timeout_task.clear()
        self.countdown_task.clear()


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

    task.add_done_callback(remove_completed_task)
