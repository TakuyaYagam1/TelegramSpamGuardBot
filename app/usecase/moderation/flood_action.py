"""Telegram actions for duplicate flood moderation flow"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.bot.util.telegram_api import call_telegram_api
from app.domain import ModerationAction

DUPLICATE_FLOOD_WARNING_TEXT = (
    "⚠️ Обнаружены одинаковые сообщения подряд. "
    "Повторный flood приведет к исключению из группы."
)


async def delete_messages(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
    message_text: str,
    message_ids: tuple[int, ...],
    logger: logging.Logger,
) -> None:
    for message_id in dict.fromkeys(message_ids):
        try:
            await call_telegram_api(
                operation=ModerationAction.DELETE_MESSAGE.value,
                call=bot.delete_message(chat_id=chat_id, message_id=int(message_id)),
                chat_id=chat_id,
                user_id=user_id,
                message_text=message_text,
                logger=logger,
            )
        except Exception:
            continue


async def send_duplicate_warning(
    *,
    bot: Any,
    message: Any,
    chat_id: int,
    user_id: int,
    message_text: str,
    logger: logging.Logger,
) -> Any:
    send_kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": DUPLICATE_FLOOD_WARNING_TEXT,
    }
    message_thread_id = getattr(message, "message_thread_id", None)
    if message_thread_id is not None:
        send_kwargs["message_thread_id"] = int(message_thread_id)

    return await call_telegram_api(
        operation=ModerationAction.WARN_USER.value,
        call=bot.send_message(**send_kwargs),
        chat_id=chat_id,
        user_id=user_id,
        message_text=message_text,
        logger=logger,
    )


async def delete_message_after_delay(
    *,
    bot: Any,
    chat_id: int,
    message_id: int,
    delay_seconds: float,
    user_id: int,
    message_text: str,
    logger: logging.Logger,
) -> None:
    await asyncio.sleep(delay_seconds)
    try:
        await call_telegram_api(
            operation=ModerationAction.DELETE_MESSAGE.value,
            call=bot.delete_message(chat_id=chat_id, message_id=message_id),
            chat_id=chat_id,
            user_id=user_id,
            message_text=message_text,
            logger=logger,
        )
    except Exception:
        return
