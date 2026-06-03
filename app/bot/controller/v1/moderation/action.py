"""Moderation action mode application for Telegram controller"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from app.config import Settings
from app.domain import ActionMode, SpamDetectionResult
from app.usecase.contract import RuntimeSettingsStore
from app.usecase.moderation import ModerationService


async def apply_moderation_action(
    *,
    message: Message,
    result: SpamDetectionResult,
    settings: Settings | None,
    moderation_service: ModerationService | None,
    runtime_settings_repository: RuntimeSettingsStore | None,
    bot: Any | None,
) -> SpamDetectionResult:
    if (
        not result.is_spam
        or settings is None
        or moderation_service is None
        or bot is None
    ):
        return result

    action_mode = settings.action_mode
    if runtime_settings_repository is not None:
        action_mode = await runtime_settings_repository.get_action_mode(
            default=settings.action_mode,
            chat_id=int(message.chat.id),
        )

    if action_mode == ActionMode.DELETE:
        return await moderation_service.delete_spam_message(
            bot=bot,
            message=message,
            spam_result=result,
        )

    if action_mode == ActionMode.NOTIFY_ADMIN:
        notification_target = None
        if runtime_settings_repository is not None:
            notification_target = (
                await runtime_settings_repository.get_notification_target(
                    chat_id=int(message.chat.id)
                )
            )
        return await moderation_service.notify_admin_about_spam(
            bot=bot,
            message=message,
            spam_result=result,
            settings=settings,
            notification_target=notification_target,
        )
