"""Administrator command usecase adapters for runtime settings"""

from __future__ import annotations

from typing import Any

from app.bot.controller.v1.admin.argument import (
    ACTION_MODE_ALIASES,
    ACTION_MODE_RESET_ALIASES,
    NOTIFICATION_TARGET_RESET_ALIASES,
    current_notification_target,
    normalize_notification_target_argument,
    parse_action_mode_argument,
    parse_notification_target_argument,
    settings_notification_target,
)
from app.bot.controller.v1.admin.panel import (
    build_action_mode_keyboard,
    build_admin_panel_text,
)
from app.bot.controller.v1.admin.permission import (
    chat_id_from_message,
    deny_admin_command,
    is_authorized_admin_sender,
    send_admin_response,
)
from app.config import Settings
from app.domain import ActionMode
from app.infrastructure.redis import RuntimeSettingsRepository


async def send_admin_panel(
    *,
    message: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    bot: Any | None = None,
    chat_id: int | None = None,
) -> ActionMode:
    current_mode = await runtime_settings_repository.get_action_mode(
        default=settings.action_mode,
        chat_id=chat_id,
    )
    notification_target = await current_notification_target(
        message=message,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        chat_id=chat_id,
    )
    await send_admin_response(
        message=message,
        bot=bot,
        text=build_admin_panel_text(
            current_mode=current_mode,
            notification_target=notification_target,
        ),
        reply_markup=build_action_mode_keyboard(
            current_mode=current_mode,
            chat_id=chat_id,
        ),
    )
    return current_mode


async def handle_action_mode_command(
    *,
    message: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    bot: Any | None = None,
) -> ActionMode | None:
    if not await is_authorized_admin_sender(
        message=message,
        settings=settings,
        bot=bot,
    ):
        await deny_admin_command(
            message=message,
            bot=bot,
            text="❌ Недостаточно прав для изменения режима модерации",
        )
        return None

    chat_id = chat_id_from_message(message)
    argument = parse_action_mode_argument(getattr(message, "text", None))
    if argument is None:
        return await send_admin_panel(
            message=message,
            settings=settings,
            runtime_settings_repository=runtime_settings_repository,
            bot=bot,
            chat_id=chat_id,
        )

    if argument in ACTION_MODE_RESET_ALIASES:
        await runtime_settings_repository.reset_action_mode(chat_id=chat_id)
        await send_admin_response(
            message=message,
            bot=bot,
            text=f"✅ Runtime-режим сброшен. Активен режим из env: {settings.action_mode.value}",
            reply_markup=build_action_mode_keyboard(
                current_mode=settings.action_mode,
                chat_id=chat_id,
            ),
        )
        return settings.action_mode

    action_mode = ACTION_MODE_ALIASES.get(argument)
    if action_mode is None:
        await send_admin_response(
            message=message,
            bot=bot,
            text="❌ Неверный режим. Доступно: delete или notify_admin",
        )
        return None

    await runtime_settings_repository.set_action_mode(action_mode, chat_id=chat_id)
    await send_admin_response(
        message=message,
        bot=bot,
        text=f"✅ Режим модерации изменен: {action_mode.value}",
        reply_markup=build_action_mode_keyboard(
            current_mode=action_mode,
            chat_id=chat_id,
        ),
    )
    return action_mode


async def handle_admin_panel_command(
    *,
    message: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    bot: Any | None = None,
) -> ActionMode | None:
    if not await is_authorized_admin_sender(
        message=message,
        settings=settings,
        bot=bot,
    ):
        await deny_admin_command(
            message=message,
            bot=bot,
            text="❌ Недостаточно прав для панели администратора",
        )
        return None

    return await send_admin_panel(
        message=message,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        bot=bot,
        chat_id=chat_id_from_message(message),
    )


async def handle_notification_target_command(
    *,
    message: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    bot: Any | None = None,
) -> str | None:
    if not await is_authorized_admin_sender(
        message=message,
        settings=settings,
        bot=bot,
    ):
        await deny_admin_command(
            message=message,
            bot=bot,
            text="❌ Недостаточно прав для изменения уведомлений",
        )
        return None

    chat_id = chat_id_from_message(message)
    if chat_id is None:
        await send_admin_response(
            message=message,
            bot=bot,
            text="❌ Команда доступна только в чате",
        )
        return None

    argument = parse_notification_target_argument(getattr(message, "text", None))
    if argument is None:
        current_target = await current_notification_target(
            message=message,
            settings=settings,
            runtime_settings_repository=runtime_settings_repository,
            chat_id=chat_id,
        )
        await send_admin_response(
            message=message,
            bot=bot,
            text="Текущий получатель уведомлений: "
            f"{current_target or 'env/default'}\n\n"
            "Команды:\n"
            "/notify me\n"
            "/notify @username\n"
            "/notify 123456789\n"
            "/notify reset",
        )
        return current_target

    if argument.casefold() in NOTIFICATION_TARGET_RESET_ALIASES:
        await runtime_settings_repository.reset_notification_target(chat_id=chat_id)
        target = settings_notification_target(settings)
        await send_admin_response(
            message=message,
            bot=bot,
            text=f"✅ Получатель уведомлений сброшен: {target or 'env/default'}",
        )
        return target

    target = normalize_notification_target_argument(
        argument=argument,
        message=message,
    )
    if target is None:
        await send_admin_response(
            message=message,
            bot=bot,
            text="❌ Укажи @username, numeric user_id, me или reset",
        )
        return None

    await runtime_settings_repository.set_notification_target(
        chat_id=chat_id,
        target=target,
    )
    await send_admin_response(
        message=message,
        bot=bot,
        text=f"✅ Получатель уведомлений изменен: {target}",
    )
    return target
