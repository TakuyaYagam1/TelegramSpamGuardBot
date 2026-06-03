"""Administrator permission checks and private response helpers"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup

from app.config import Settings

ADMIN_STATUSES = {"administrator", "creator"}
GROUP_CHAT_TYPES = {"group", "supergroup"}


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.strip().lstrip("@").casefold() or None


def is_admin_sender(*, message: Any, settings: Settings) -> bool:
    sender = getattr(message, "from_user", None)
    if sender is None:
        return False

    sender_id = getattr(sender, "id", None)
    if settings.admin_id is not None and sender_id is not None:
        if int(sender_id) == settings.admin_id:
            return True

    expected_username = normalize_username(settings.admin_username)
    sender_username = normalize_username(getattr(sender, "username", None))
    return expected_username is not None and expected_username == sender_username


def sender_id_from_message(message: Any) -> int | None:
    sender = getattr(message, "from_user", None)
    sender_id = getattr(sender, "id", None)
    return None if sender_id is None else int(sender_id)


def chat_id_from_message(message: Any) -> int | None:
    chat = getattr(message, "chat", None)
    if chat is None:
        nested_message = getattr(message, "message", None)
        chat = getattr(nested_message, "chat", None)

    raw_chat_id = getattr(chat, "id", None)
    return None if raw_chat_id is None else int(raw_chat_id)


def is_group_chat(message: Any) -> bool:
    chat = getattr(message, "chat", None)
    if chat is None:
        nested_message = getattr(message, "message", None)
        chat = getattr(nested_message, "chat", None)

    raw_chat_type = getattr(chat, "type", "")
    chat_type = str(getattr(raw_chat_type, "value", raw_chat_type)).lower()
    return chat_type in GROUP_CHAT_TYPES


def is_group_context(*, message: Any, chat_id: int | None) -> bool:
    return is_group_chat(message) or (chat_id is not None and chat_id < 0)


async def delete_command_message(message: Any) -> None:
    delete = getattr(message, "delete", None)
    if not callable(delete):
        return

    try:
        await delete()
    except Exception:
        pass


async def deny_admin_command(*, message: Any, bot: Any | None, text: str) -> None:
    if bot is not None and is_group_chat(message):
        await delete_command_message(message)
        return

    await message.answer(text)


async def send_admin_response(
    *,
    message: Any,
    bot: Any | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if bot is not None and is_group_chat(message):
        await delete_command_message(message)
        sender_id = sender_id_from_message(message)
        if sender_id is None:
            return

        try:
            await bot.send_message(
                chat_id=sender_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception:
            return
        return

    await message.answer(text, reply_markup=reply_markup)


async def is_authorized_admin_sender(
    *,
    message: Any,
    settings: Settings,
    bot: Any | None = None,
    chat_id: int | None = None,
) -> bool:
    chat_id = chat_id or chat_id_from_message(message)
    sender_id = sender_id_from_message(message)
    if bot is not None and chat_id is not None and sender_id is not None:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=sender_id)
        except Exception:
            member = None

        status = getattr(member, "status", None)
        status_value = str(getattr(status, "value", status)).lower()
        if status_value in ADMIN_STATUSES:
            return True
        if is_group_context(message=message, chat_id=chat_id):
            return False

    return is_admin_sender(message=message, settings=settings)
