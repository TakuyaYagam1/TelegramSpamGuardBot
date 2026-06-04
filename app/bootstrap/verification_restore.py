"""Pending verification restore helpers for startup timer recovery"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.domain import PendingVerification
from app.infrastructure.redis import (
    PendingVerificationRepository,
    VerifiedUserRepository,
)
from app.observability.logging import log_app_event
from app.usecase.verification import (
    VerificationTaskRegistry,
    schedule_join_request_timeout,
    schedule_unverified_user_removal,
)

RESTORED_TIMER_SAFETY_MARGIN_SECONDS = 0.25
JOINED_MEMBER_STATUSES = frozenset(("member", "administrator", "creator"))


def redis_key_text(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode("utf-8", errors="replace")
    return str(key)


def parse_pending_verification_key(key: str) -> tuple[int, int] | None:
    parts = key.split(":")
    if len(parts) != 3 or parts[0] != "verify":
        return None

    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def parse_pending_created_at(created_at_text: str) -> datetime:
    created_at = datetime.fromisoformat(created_at_text)
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)


def restored_timer_delay(
    pending: PendingVerification,
    *,
    timeout_seconds: int,
) -> float:
    elapsed_seconds = (
        datetime.now(UTC) - parse_pending_created_at(pending.created_at)
    ).total_seconds()
    remaining_seconds = timeout_seconds - elapsed_seconds
    if remaining_seconds <= 1:
        return 0
    return max(0, remaining_seconds - RESTORED_TIMER_SAFETY_MARGIN_SECONDS)


async def delete_unrestorable_verification_key(
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


def telegram_member_status_text(member: Any) -> str:
    status = getattr(member, "status", None)
    status_value = getattr(status, "value", status)
    return str(status_value).lower()


async def verified_marker_exists(
    *,
    verified_user_repository: VerifiedUserRepository | None,
    chat_id: int,
    user_id: int,
    logger: logging.Logger,
) -> bool:
    if verified_user_repository is None:
        return False

    try:
        return await verified_user_repository.is_verified(
            chat_id=chat_id, user_id=user_id
        )
    except Exception as exc:
        log_app_event(
            logger,
            event="verified_user_restore_lookup_failed",
            chat_id=chat_id,
            user_id=user_id,
            action="lookup_verified_user",
            details=f"error_type={type(exc).__name__}",
            level=logging.ERROR,
        )
        return False


async def join_request_user_already_joined(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
) -> bool:
    get_chat_member = getattr(bot, "get_chat_member", None)
    if not callable(get_chat_member):
        return False

    try:
        member = await get_chat_member(chat_id=chat_id, user_id=user_id)
    except Exception:
        return False

    return telegram_member_status_text(member) in JOINED_MEMBER_STATUSES


def schedule_restored_verification_timer(
    *,
    bot: Any,
    pending_verification_repository: PendingVerificationRepository,
    verification_task_registry: VerificationTaskRegistry,
    settings: Settings,
    pending: PendingVerification,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
    logger: logging.Logger,
) -> None:
    if pending.verification_chat_id is None:
        schedule_unverified_user_removal(
            bot=bot,
            pending_verification_repository=pending_verification_repository,
            chat_id=chat_id,
            user_id=user_id,
            timeout_seconds=timeout_seconds,
            task_registry=verification_task_registry.timeout_task,
            logger=logger,
        )
        return

    schedule_join_request_timeout(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        configured_timeout_seconds=settings.verify_timeout_seconds,
        task_registry=verification_task_registry.timeout_task,
        logger=logger,
    )


async def restore_pending_verification_entry(
    *,
    redis_client: Any,
    bot: Any,
    raw_key: Any,
    pending_verification_repository: PendingVerificationRepository,
    verification_task_registry: VerificationTaskRegistry,
    settings: Settings,
    verified_user_repository: VerifiedUserRepository | None,
    logger: logging.Logger,
) -> bool:
    key = redis_key_text(raw_key)
    parsed_key = parse_pending_verification_key(key)
    if parsed_key is None:
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="invalid_key",
            logger=logger,
        )
        return False
    chat_id, user_id = parsed_key

    ttl = await redis_client.ttl(key)
    if ttl <= 0:
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason=f"invalid_ttl:{ttl}",
            logger=logger,
        )
        return False

    try:
        pending = await pending_verification_repository.get(
            chat_id=chat_id,
            user_id=user_id,
        )
    except KeyError, TypeError, ValueError:
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="invalid_payload",
            logger=logger,
        )
        return False

    if pending is None:
        log_app_event(
            logger,
            event="pending_verification_restore_skipped",
            chat_id=chat_id,
            user_id=user_id,
            action="skip_pending_verification",
            details="pending record disappeared before timer restore",
        )
        return False

    if pending.chat_id != chat_id or pending.user_id != user_id:
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="payload_key_mismatch",
            logger=logger,
        )
        return False

    if await verified_marker_exists(
        verified_user_repository=verified_user_repository,
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
    ):
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="already_verified",
            logger=logger,
        )
        return False

    if (
        pending.verification_chat_id is not None
        and await join_request_user_already_joined(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
        )
    ):
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="join_request_already_approved",
            logger=logger,
        )
        return False

    try:
        timeout_seconds = restored_timer_delay(
            pending,
            timeout_seconds=settings.verify_timeout_seconds,
        )
    except TypeError, ValueError:
        await delete_unrestorable_verification_key(
            redis_client=redis_client,
            key=key,
            reason="invalid_created_at",
            logger=logger,
        )
        return False

    schedule_restored_verification_timer(
        bot=bot,
        pending_verification_repository=pending_verification_repository,
        verification_task_registry=verification_task_registry,
        settings=settings,
        pending=pending,
        chat_id=chat_id,
        user_id=user_id,
        timeout_seconds=timeout_seconds,
        logger=logger,
    )
    return True
