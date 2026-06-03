"""Startup and shutdown hooks for runtime resources"""

from __future__ import annotations

import logging
from typing import Any

from app.bootstrap.command import set_bot_commands
from app.bootstrap.verification_timer import restore_pending_verification_timer
from app.config import Settings
from app.infrastructure.redis import PendingVerificationRepository
from app.usecase.verification import VerificationTaskRegistry


async def on_startup(
    *,
    bot: Any,
    redis_client: Any,
    pending_verification_repository: PendingVerificationRepository,
    verification_task_registry: VerificationTaskRegistry,
    settings: Settings,
    logger: logging.Logger | None = None,
    **_: Any,
) -> None:
    await redis_client.ping()
    await set_bot_commands(bot, settings)
    await restore_pending_verification_timer(
        redis_client=redis_client,
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        verification_task_registry=verification_task_registry,
        settings=settings,
        logger=logger,
    )


async def on_shutdown(
    *,
    bot: Any,
    redis_client: Any,
    verification_task_registry: VerificationTaskRegistry,
    **_: Any,
) -> None:
    await verification_task_registry.cancel_all()
    await bot.session.close()
    try:
        await redis_client.aclose(close_connection_pool=True)
    except TypeError:
        await redis_client.aclose()
