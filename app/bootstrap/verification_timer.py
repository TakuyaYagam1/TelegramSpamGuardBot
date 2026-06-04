"""Pending verification timer restore entrypoint for application startup"""

from __future__ import annotations

import logging
from typing import Any

from app.bootstrap.verification_restore import restore_pending_verification_entry
from app.config import Settings
from app.infrastructure.redis import (
    PendingVerificationRepository,
    VerifiedUserRepository,
)
from app.observability.logging import get_logger
from app.usecase.verification import VerificationTaskRegistry

PENDING_VERIFICATION_TTL_GRACE_SECONDS = 60


def pending_verification_ttl_seconds(settings: Settings) -> int:
    return settings.verify_timeout_seconds + PENDING_VERIFICATION_TTL_GRACE_SECONDS


async def restore_pending_verification_timer(
    *,
    redis_client: Any,
    bot: Any,
    pending_verification_repository: PendingVerificationRepository,
    verification_task_registry: VerificationTaskRegistry,
    settings: Settings,
    verified_user_repository: VerifiedUserRepository | None = None,
    logger: logging.Logger | None = None,
) -> int:
    event_logger = logger or get_logger("app")
    restored = 0
    async for raw_key in redis_client.scan_iter(match="verify:*"):
        was_restored = await restore_pending_verification_entry(
            redis_client=redis_client,
            bot=bot,
            raw_key=raw_key,
            pending_verification_repository=pending_verification_repository,
            verification_task_registry=verification_task_registry,
            settings=settings,
            verified_user_repository=verified_user_repository,
            logger=event_logger,
        )
        restored += int(was_restored)
    return restored
