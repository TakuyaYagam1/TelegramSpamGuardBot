"""Telegram command menu registration for administrator scopes"""

from __future__ import annotations

from typing import Any

from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from app.config import Settings

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="admin", description="панель администратора"),
    BotCommand(command="help", description="помощь по командам"),
    BotCommand(command="mode", description="режим модерации"),
    BotCommand(command="notify", description="получатель уведомлений"),
)


async def set_bot_commands(bot: Any, settings: Settings) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(
        list(BOT_COMMANDS),
        scope=BotCommandScopeAllChatAdministrators(),
    )
    if settings.admin_id is not None:
        await bot.set_my_commands(
            list(BOT_COMMANDS),
            scope=BotCommandScopeChat(chat_id=settings.admin_id),
        )
