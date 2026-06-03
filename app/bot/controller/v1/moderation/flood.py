"""Duplicate flood orchestration for Telegram moderation controller"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from app.config import Settings
from app.domain import LLMDecision, SpamDetectionResult, StopWordCheckResult
from app.usecase.contract import DuplicateMessageStore
from app.usecase.moderation import ModerationService


async def handle_duplicate_flood(
    *,
    message: Message,
    duplicate_message_repository: DuplicateMessageStore | None,
    settings: Settings | None,
    moderation_service: ModerationService | None,
    bot: Any | None,
    content_key: str | None,
) -> SpamDetectionResult | None:
    if (
        duplicate_message_repository is None
        or settings is None
        or moderation_service is None
        or bot is None
        or content_key is None
    ):
        return None

    message_id = getattr(message, "message_id", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    if message_id is None or chat_id is None or user_id is None:
        return None

    state = await duplicate_message_repository.record_message(
        chat_id=int(chat_id),
        user_id=int(user_id),
        message_id=int(message_id),
        content_key=content_key,
    )
    warned_digest = await duplicate_message_repository.get_warning_digest(
        chat_id=int(chat_id),
        user_id=int(user_id),
    )
    if warned_digest == state.digest or (
        warned_digest is not None
        and len(state.message_ids) >= settings.duplicate_message_warn_threshold
    ):
        return await kick_repeated_duplicate_flood(
            message=message,
            duplicate_message_repository=duplicate_message_repository,
            moderation_service=moderation_service,
            bot=bot,
            duplicate_message_ids=state.message_ids,
            chat_id=int(chat_id),
            user_id=int(user_id),
        )

    if len(state.message_ids) < settings.duplicate_message_warn_threshold:
        return None

    marked_warning = await duplicate_message_repository.mark_warned_once(
        chat_id=int(chat_id),
        user_id=int(user_id),
        digest=state.digest,
    )
    if not marked_warning:
        warned_digest = await duplicate_message_repository.get_warning_digest(
            chat_id=int(chat_id),
            user_id=int(user_id),
        )
        if warned_digest is not None:
            return await kick_repeated_duplicate_flood(
                message=message,
                duplicate_message_repository=duplicate_message_repository,
                moderation_service=moderation_service,
                bot=bot,
                duplicate_message_ids=state.message_ids,
                chat_id=int(chat_id),
                user_id=int(user_id),
            )
        return None

    result = SpamDetectionResult(
        is_spam=True,
        reason="duplicate_flood",
        stop_word=StopWordCheckResult(matched=False),
        llm_decision=LLMDecision.UNKNOWN,
        matched_term="duplicate_content",
    )
    moderation_result = await moderation_service.warn_duplicate_flood(
        bot=bot,
        message=message,
        spam_result=result,
        duplicate_message_ids=state.message_ids,
        warning_message_ttl_seconds=settings.duplicate_warning_message_ttl_seconds,
    )
    await duplicate_message_repository.clear(chat_id=int(chat_id), user_id=int(user_id))
    return moderation_result


async def kick_repeated_duplicate_flood(
    *,
    message: Message,
    duplicate_message_repository: DuplicateMessageStore,
    moderation_service: ModerationService,
    bot: Any,
    duplicate_message_ids: tuple[int, ...],
    chat_id: int,
    user_id: int,
) -> SpamDetectionResult:
    result = SpamDetectionResult(
        is_spam=True,
        reason="duplicate_flood_repeated_after_warning",
        stop_word=StopWordCheckResult(matched=False),
        llm_decision=LLMDecision.SPAM,
        matched_term="duplicate_content",
    )
    moderation_result = await moderation_service.kick_duplicate_flood(
        bot=bot,
        message=message,
        spam_result=result,
        duplicate_message_ids=duplicate_message_ids,
    )
    await duplicate_message_repository.clear(chat_id=chat_id, user_id=user_id)
    await duplicate_message_repository.clear_warning(chat_id=chat_id, user_id=user_id)
    return moderation_result
