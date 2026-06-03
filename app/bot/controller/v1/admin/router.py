"""Aiogram router bindings for administrator commands and callbacks"""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.controller.v1.admin.callback import handle_action_mode_callback
from app.bot.controller.v1.admin.command import (
    handle_action_mode_command,
    handle_admin_panel_command,
    handle_notification_target_command,
)
from app.bot.controller.v1.admin.panel import ACTION_MODE_CALLBACK_PREFIX
from app.config import Settings
from app.infrastructure.redis import RuntimeSettingsRepository

router = Router(name="admin")


@router.message(Command("mode"))
async def on_action_mode_command(
    message: Message,
    bot: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
) -> None:
    await handle_action_mode_command(
        message=message,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        bot=bot,
    )


@router.message(Command("admin"))
@router.message(Command("help"))
async def on_admin_panel_command(
    message: Message,
    bot: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
) -> None:
    await handle_admin_panel_command(
        message=message,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        bot=bot,
    )


@router.message(Command("notify"))
async def on_notification_target_command(
    message: Message,
    bot: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
) -> None:
    await handle_notification_target_command(
        message=message,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        bot=bot,
    )


@router.callback_query(F.data.startswith(f"{ACTION_MODE_CALLBACK_PREFIX}:"))
async def on_action_mode_callback(
    callback_query: CallbackQuery,
    bot: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
) -> None:
    await handle_action_mode_callback(
        callback_query=callback_query,
        settings=settings,
        runtime_settings_repository=runtime_settings_repository,
        bot=bot,
    )
