"""Moderation action usecase for delete, notify, warn and kick flows"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any

from app.bot.util.telegram_api import call_telegram_api
from app.config import Settings
from app.domain import ModerationAction, SpamDetectionResult
from app.observability.logging import get_logger, log_spam_event
from app.usecase.moderation.flood_action import (
    delete_message_after_delay,
    delete_messages,
    send_duplicate_warning,
)
from app.usecase.moderation.message import (
    build_message_reference,
    build_spam_notification_text,
    format_spammer,
    message_text_for_log,
)
from app.usecase.moderation.notification import (
    format_admin_target,
    resolve_notification_target,
    send_admin_notification,
)


class ModerationService:
    async def notify_admin_about_spam(
        self,
        *,
        bot: Any,
        message: Any,
        spam_result: SpamDetectionResult,
        settings: Settings,
        notification_target: str | None = None,
        logger: logging.Logger | None = None,
    ) -> SpamDetectionResult:
        chat_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        message_text = message_text_for_log(message)
        event_logger = logger or get_logger("app")
        admin_target = resolve_notification_target(
            settings=settings,
            runtime_target=notification_target,
        )
        admin_target_text = format_admin_target(admin_target)
        spammer = format_spammer(message.from_user)
        message_reference = build_message_reference(message)
        notification_text = build_spam_notification_text(
            admin_target_text=admin_target_text,
            spammer=spammer,
            user_id=user_id,
            reason=spam_result.reason,
            message_reference=message_reference,
            message_text=message_text,
        )
        await send_admin_notification(
            bot=bot,
            target=admin_target,
            group_chat_id=chat_id,
            message=message,
            text=notification_text,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )

        action = ModerationAction.NOTIFY_ADMIN.value
        details = (
            f"admin={admin_target_text}; "
            f"spammer={spammer}; "
            f"reason={spam_result.reason}; "
            f"llm_decision={spam_result.llm_decision.value}; "
            f"matched_term={spam_result.matched_term or '-'}"
        )
        log_spam_event(
            event_logger,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            action=action,
            details=details,
        )
        return replace(spam_result, moderation_action=ModerationAction.NOTIFY_ADMIN)

    async def delete_spam_message(
        self,
        *,
        bot: Any,
        message: Any,
        spam_result: SpamDetectionResult,
        logger: logging.Logger | None = None,
    ) -> SpamDetectionResult:
        chat_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        message_id = int(message.message_id)
        message_text = message_text_for_log(message)
        event_logger = logger or get_logger("app")

        await call_telegram_api(
            operation=ModerationAction.DELETE_MESSAGE.value,
            call=bot.delete_message(chat_id=chat_id, message_id=message_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )
        await call_telegram_api(
            operation=ModerationAction.BAN_UNBAN.value,
            call=bot.ban_chat_member(chat_id=chat_id, user_id=user_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )
        await call_telegram_api(
            operation=ModerationAction.BAN_UNBAN.value,
            call=bot.unban_chat_member(chat_id=chat_id, user_id=user_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )

        action = ModerationAction.DELETE_MESSAGE.value
        details = (
            f"reason={spam_result.reason}; "
            f"llm_decision={spam_result.llm_decision.value}; "
            f"matched_term={spam_result.matched_term or '-'}"
        )
        log_spam_event(
            event_logger,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            action=action,
            details=details,
        )
        return replace(spam_result, moderation_action=ModerationAction.DELETE_MESSAGE)

    async def warn_duplicate_flood(
        self,
        *,
        bot: Any,
        message: Any,
        spam_result: SpamDetectionResult,
        duplicate_message_ids: tuple[int, ...],
        warning_message_ttl_seconds: float | None = None,
        logger: logging.Logger | None = None,
    ) -> SpamDetectionResult:
        chat_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        message_text = message_text_for_log(message)
        event_logger = logger or get_logger("app")

        await delete_messages(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            message_ids=duplicate_message_ids,
            logger=event_logger,
        )
        warning_message = await send_duplicate_warning(
            bot=bot,
            message=message,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )
        warning_message_id = getattr(warning_message, "message_id", None)
        if warning_message_id is not None and warning_message_ttl_seconds is not None:
            asyncio.create_task(
                delete_message_after_delay(
                    bot=bot,
                    chat_id=chat_id,
                    message_id=int(warning_message_id),
                    delay_seconds=warning_message_ttl_seconds,
                    user_id=user_id,
                    message_text=message_text,
                    logger=event_logger,
                )
            )

        log_spam_event(
            event_logger,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            action=ModerationAction.WARN_USER.value,
            details=(
                f"reason={spam_result.reason}; "
                f"llm_decision={spam_result.llm_decision.value}; "
                f"matched_term={spam_result.matched_term or '-'}; "
                f"deleted_messages={len(duplicate_message_ids)}"
            ),
        )
        return replace(spam_result, moderation_action=ModerationAction.WARN_USER)

    async def kick_duplicate_flood(
        self,
        *,
        bot: Any,
        message: Any,
        spam_result: SpamDetectionResult,
        duplicate_message_ids: tuple[int, ...],
        logger: logging.Logger | None = None,
    ) -> SpamDetectionResult:
        chat_id = int(message.chat.id)
        user_id = int(message.from_user.id)
        message_text = message_text_for_log(message)
        event_logger = logger or get_logger("app")

        await delete_messages(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            message_ids=duplicate_message_ids,
            logger=event_logger,
        )
        await call_telegram_api(
            operation=ModerationAction.BAN_UNBAN.value,
            call=bot.ban_chat_member(chat_id=chat_id, user_id=user_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )
        await call_telegram_api(
            operation=ModerationAction.BAN_UNBAN.value,
            call=bot.unban_chat_member(chat_id=chat_id, user_id=user_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=event_logger,
        )

        log_spam_event(
            event_logger,
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            action=ModerationAction.BAN_UNBAN.value,
            details=(
                f"reason={spam_result.reason}; "
                f"llm_decision={spam_result.llm_decision.value}; "
                f"matched_term={spam_result.matched_term or '-'}; "
                f"deleted_messages={len(duplicate_message_ids)}"
            ),
        )
        return replace(spam_result, moderation_action=ModerationAction.BAN_UNBAN)
