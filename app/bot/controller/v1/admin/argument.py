"""Administrator command argument parsing and runtime target helpers"""

from __future__ import annotations

from typing import Any

from app.bot.controller.v1.admin.permission import (
    chat_id_from_message,
    sender_id_from_message,
)
from app.config import Settings
from app.domain import ActionMode
from app.infrastructure.redis import RuntimeSettingsRepository

ACTION_MODE_ALIASES = {
    "delete": ActionMode.DELETE,
    "notify": ActionMode.NOTIFY_ADMIN,
    "notify_admin": ActionMode.NOTIFY_ADMIN,
}
ACTION_MODE_RESET_ALIASES = {"default", "env", "reset"}
NOTIFICATION_TARGET_RESET_ALIASES = {"default", "env", "reset"}


def parse_command_argument(text: str | None) -> str | None:
    if not text:
        return None

    parts = text.strip().split(maxsplit=1)
    if len(parts) == 1:
        return None
    return parts[1].strip() or None


def parse_action_mode_argument(text: str | None) -> str | None:
    argument = parse_command_argument(text)
    if argument is None:
        return None
    return argument.split(maxsplit=1)[0].casefold()


def parse_notification_target_argument(text: str | None) -> str | None:
    return parse_command_argument(text)


def settings_notification_target(settings: Settings) -> str | None:
    if settings.admin_id is not None:
        return str(settings.admin_id)
    if settings.admin_username:
        username = settings.admin_username.strip()
        return username if username.startswith("@") else f"@{username}"
    return None


async def current_notification_target(
    *,
    message: Any,
    settings: Settings,
    runtime_settings_repository: RuntimeSettingsRepository,
    chat_id: int | None = None,
) -> str | None:
    chat_id = chat_id or chat_id_from_message(message)
    if chat_id is None:
        return settings_notification_target(settings)

    runtime_target = await runtime_settings_repository.get_notification_target(
        chat_id=chat_id
    )
    return runtime_target or settings_notification_target(settings)


def normalize_notification_target_argument(
    *,
    argument: str,
    message: Any,
) -> str | None:
    normalized = argument.strip()
    if not normalized:
        return None

    if normalized.casefold() == "me":
        sender_id = sender_id_from_message(message)
        return None if sender_id is None else str(sender_id)

    if normalized.startswith("@") and len(normalized) > 1:
        return normalized

    if normalized.lstrip("-").isdigit():
        return str(int(normalized))

    return None
