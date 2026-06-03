"""Telegram message extraction helpers for moderation controller"""

from __future__ import annotations

from typing import Any

GROUP_CHAT_TYPES = {"group", "supergroup"}
FILE_CONTENT_FIELDS = (
    "sticker",
    "animation",
    "video",
    "document",
    "audio",
    "voice",
    "video_note",
)
FILE_METADATA_FIELDS = ("file_name", "mime_type", "emoji", "set_name")
CONTROL_COMMANDS = {"admin", "help", "mode", "notify"}


def chat_type(message: Any) -> str:
    chat = getattr(message, "chat", None)
    raw_chat_type = getattr(chat, "type", "")
    return str(getattr(raw_chat_type, "value", raw_chat_type)).lower()


def is_bot_message(message: Any) -> bool:
    from_user = getattr(message, "from_user", None)
    return bool(getattr(from_user, "is_bot", False))


def message_text(message: Any) -> str | None:
    text = getattr(message, "text", None)
    if text:
        return str(text)

    caption = getattr(message, "caption", None)
    if caption:
        return str(caption)

    return None


def file_unique_content_key(message: Any) -> str | None:
    for field in FILE_CONTENT_FIELDS:
        value = getattr(message, field, None)
        file_unique_id = getattr(value, "file_unique_id", None)
        if file_unique_id:
            return f"{field}:{file_unique_id}"

    photos = getattr(message, "photo", None)
    if photos:
        file_unique_id = getattr(photos[-1], "file_unique_id", None)
        if file_unique_id:
            return f"photo:{file_unique_id}"

    return None


def normalize_content_key(content_key: str) -> str:
    return " ".join(content_key.casefold().split())


def duplicate_content_key(message: Any) -> str | None:
    file_content_key = file_unique_content_key(message)
    if file_content_key:
        return file_content_key

    text = message_text(message)
    if text:
        return f"text:{normalize_content_key(text)}"

    return None


def file_metadata_text(message: Any) -> str | None:
    parts: list[str] = []
    for field in FILE_CONTENT_FIELDS:
        value = getattr(message, field, None)
        if value is None:
            continue

        for metadata_field in FILE_METADATA_FIELDS:
            metadata_value = getattr(value, metadata_field, None)
            if metadata_value:
                parts.append(str(metadata_value))

    if not parts:
        return None

    return " ".join(parts)


def entity_url_text(message: Any) -> str | None:
    urls: list[str] = []
    for field in ("entities", "caption_entities"):
        entities = getattr(message, field, None) or ()
        for entity in entities:
            url = getattr(entity, "url", None)
            if url:
                urls.append(str(url))

    if not urls:
        return None
    return " ".join(urls)


def message_spam_text(message: Any) -> str | None:
    parts = [
        part
        for part in (
            message_text(message),
            file_metadata_text(message),
            entity_url_text(message),
        )
        if part
    ]
    if not parts:
        return None
    return " ".join(parts)


def is_control_command_message(message: Any) -> bool:
    text = getattr(message, "text", None)
    if not isinstance(text, str):
        return False

    command = text.strip().split(maxsplit=1)[0].casefold()
    if not command.startswith("/"):
        return False

    command_name = command[1:].split("@", maxsplit=1)[0]
    return command_name in CONTROL_COMMANDS


def should_ignore_message(message: Any) -> bool:
    return (
        chat_type(message) not in GROUP_CHAT_TYPES
        or is_bot_message(message)
        or is_control_command_message(message)
    )
