"""Pending verification timer restore logic for application startup"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.domain import PendingVerification
from app.infrastructure.redis import PendingVerificationRepository
from app.observability.logging import get_logger, log_app_event
from app.usecase.verification import (
    VerificationTaskRegistry,
    schedule_join_request_timeout,
    schedule_unverified_user_removal,
)

RESTORED_TIMER_SAFETY_MARGIN_SECONDS = 0.25
PENDING_VERIFICATION_TTL_GRACE_SECONDS = 60


def pending_verification_ttl_seconds(settings: Settings) -> int:
    return settings.verify_timeout_seconds + PENDING_VERIFICATION_TTL_GRACE_SECONDS


def _redis_key_text(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode("utf-8", errors="replace")
    return str(key)


def _parse_pending_verification_key(key: str) -> tuple[int, int] | None:
    parts = key.split(":")
    if len(parts) != 3 or parts[0] != "verify":
        return None

    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _parse_pending_created_at(created_at_text: str) -> datetime:
    created_at = datetime.fromisoformat(created_at_text)
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)


def _restored_timer_delay(
    pending: PendingVerification,
    *,
    timeout_seconds: int,
) -> float:
    elapsed_seconds = (
        datetime.now(UTC) - _parse_pending_created_at(pending.created_at)
    ).total_seconds()
    remaining_seconds = timeout_seconds - elapsed_seconds
    if remaining_seconds <= 1:
        return 0
    return max(0, remaining_seconds - RESTORED_TIMER_SAFETY_MARGIN_SECONDS)


async def _delete_unrestorable_verification_key(
    *,
    redis_client: Any,
    key: str,
    reason: str,
    logger: logging.Logger,
) -> None:
    await redis_client.delete(key)
    log_app_event(
        logger,
        event="pending_verification_restore_skipped",
        action="delete_pending_verification",
        details=f"key={key}; reason={reason}",
    )


async def restore_pending_verification_timer(
    *,
    redis_client: Any,
    bot: Any,
    pending_verification_repository: PendingVerificationRepository,
    verification_task_registry: VerificationTaskRegistry,
    settings: Settings,
    logger: logging.Logger | None = None,
) -> int:
    event_logger = logger or get_logger("app")
    restored = 0
    async for raw_key in redis_client.scan_iter(match="verify:*"):
        key = _redis_key_text(raw_key)
        parsed_key = _parse_pending_verification_key(key)
        if parsed_key is None:
            await _delete_unrestorable_verification_key(
                redis_client=redis_client,
                key=key,
                reason="invalid_key",
                logger=event_logger,
            )
            continue
        chat_id, user_id = parsed_key

        ttl = await redis_client.ttl(key)
        if ttl <= 0:
            await _delete_unrestorable_verification_key(
                redis_client=redis_client,
                key=key,
                reason=f"invalid_ttl:{ttl}",
                logger=event_logger,
            )
            continue

        try:
            pending = await pending_verification_repository.get(
                chat_id=chat_id,
                user_id=user_id,
            )
        except KeyError, TypeError, ValueError:
            await _delete_unrestorable_verification_key(
                redis_client=redis_client,
                key=key,
                reason="invalid_payload",
                logger=event_logger,
            )
            continue

        if pending is None:
            log_app_event(
                event_logger,
                event="pending_verification_restore_skipped",
                chat_id=chat_id,
                user_id=user_id,
                action="skip_pending_verification",
                details="pending record disappeared before timer restore",
            )
            continue

        if pending.chat_id != chat_id or pending.user_id != user_id:
            await _delete_unrestorable_verification_key(
                redis_client=redis_client,
                key=key,
                reason="payload_key_mismatch",
                logger=event_logger,
            )
            continue

        try:
            timeout_seconds = _restored_timer_delay(
                pending,
                timeout_seconds=settings.verify_timeout_seconds,
            )
        except TypeError, ValueError:
            await _delete_unrestorable_verification_key(
                redis_client=redis_client,
                key=key,
                reason="invalid_created_at",
                logger=event_logger,
            )
            continue

        if pending.verification_chat_id is None:
            schedule_unverified_user_removal(
                bot=bot,
                pending_verification_repository=pending_verification_repository,
                chat_id=chat_id,
                user_id=user_id,
                timeout_seconds=timeout_seconds,
                task_registry=verification_task_registry.timeout_task,
                logger=event_logger,
            )
        else:
            schedule_join_request_timeout(
                bot=bot,
                pending_verification_repository=pending_verification_repository,
                chat_id=chat_id,
                user_id=user_id,
                timeout_seconds=timeout_seconds,
                task_registry=verification_task_registry.timeout_task,
                logger=event_logger,
            )
        restored += 1
    return restored
