"""Administrator panel text and inline keyboard builders"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain import ActionMode

ACTION_MODE_CALLBACK_PREFIX = "admin_mode"


def action_mode_callback_data(*, action: str, chat_id: int | None = None) -> str:
    if chat_id is None:
        return f"{ACTION_MODE_CALLBACK_PREFIX}:{action}"
    return f"{ACTION_MODE_CALLBACK_PREFIX}:{action}:{chat_id}"


def parse_action_mode_callback_data(data: str) -> tuple[str, int | None]:
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != ACTION_MODE_CALLBACK_PREFIX:
        return "", None

    chat_id = None
    if len(parts) >= 3:
        try:
            chat_id = int(parts[2])
        except ValueError:
            chat_id = None

    return parts[1].casefold(), chat_id


def build_action_mode_keyboard(
    *,
    current_mode: ActionMode,
    chat_id: int | None = None,
) -> InlineKeyboardMarkup:
    delete_text = (
        "✅ Удалять спам" if current_mode == ActionMode.DELETE else "Удалять спам"
    )
    notify_text = (
        "✅ Только уведомлять"
        if current_mode == ActionMode.NOTIFY_ADMIN
        else "Только уведомлять"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=delete_text,
                    callback_data=action_mode_callback_data(
                        action="delete",
                        chat_id=chat_id,
                    ),
                ),
                InlineKeyboardButton(
                    text=notify_text,
                    callback_data=action_mode_callback_data(
                        action="notify_admin",
                        chat_id=chat_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Сбросить к env",
                    callback_data=action_mode_callback_data(
                        action="reset",
                        chat_id=chat_id,
                    ),
                )
            ],
        ]
    )


def build_admin_panel_text(
    *,
    current_mode: ActionMode,
    notification_target: str | None = None,
) -> str:
    target_text = notification_target or "env/default"
    return (
        "⚙️ Панель администратора\n\n"
        f"Текущий режим модерации: {current_mode.value}\n\n"
        f"Получатель уведомлений: {target_text}\n\n"
        "Команды:\n"
        "/mode\n"
        "/mode delete\n"
        "/mode notify_admin\n"
        "/mode reset\n"
        "/notify\n"
        "/notify me\n"
        "/notify @username\n"
        "/notify 123456789\n"
        "/notify reset"
    )
