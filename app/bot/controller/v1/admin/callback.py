"""Administrator callback handlers for inline moderation controls"""

from __future__ import annotations

from typing import Any

from app.bot.controller.v1.admin.command import (
    ACTION_MODE_ALIASES,
    ACTION_MODE_RESET_ALIASES,
    current_notification_target,
)
from app.bot.controller.v1.admin.panel import (
    build_action_mode_keyboard,
    build_admin_panel_text,
    parse_action_mode_callback_data,
)
from app.bot.controller.v1.admin.permission import is_authorized_admin_sender
from app.config import Settings
from app.domain import ActionMode
from app.infrastructure.redis import RuntimeSettingsRepository


async def handle_action_mode_callback(
    *,
    callback_query: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    bot: Any | None = None,
) -> ActionMode | None:
    data = str(getattr(callback_query, "data", ""))
    argument, chat_id = parse_action_mode_callback_data(data)

    if not await is_authorized_admin_sender(
        message=callback_query,
        settings=settings,
        bot=bot,
        chat_id=chat_id,
    ):
        await callback_query.answer(
            text="❌ Недостаточно прав для изменения режима",
            show_alert=True,
        )
        return None

    if argument in ACTION_MODE_RESET_ALIASES:
        await runtime_settings_repository.reset_action_mode(chat_id=chat_id)
        current_mode = settings.action_mode
        answer_text = f"✅ Активен режим из env: {current_mode.value}"
    else:
        action_mode = ACTION_MODE_ALIASES.get(argument)
        if action_mode is None:
            await callback_query.answer(text="❌ Неверный режим", show_alert=True)
            return None

        await runtime_settings_repository.set_action_mode(action_mode, chat_id=chat_id)
        current_mode = action_mode
        answer_text = f"✅ Режим изменен: {current_mode.value}"

    message = getattr(callback_query, "message", None)
    if message is not None:
        try:
            notification_target = await current_notification_target(
                message=callback_query,
                settings=settings,
                runtime_settings_repository=runtime_settings_repository,
                chat_id=chat_id,
            )
            await message.edit_text(
                build_admin_panel_text(
                    current_mode=current_mode,
                    notification_target=notification_target,
                ),
                reply_markup=build_action_mode_keyboard(
                    current_mode=current_mode,
                    chat_id=chat_id,
                ),
            )
        except Exception:
            pass

    await callback_query.answer(text=answer_text)
    return current_mode
