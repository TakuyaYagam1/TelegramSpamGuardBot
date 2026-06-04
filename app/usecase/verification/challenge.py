"""Verification challenge message sending usecases"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from app.bot.util.telegram_api import call_telegram_api
from app.bot.util.telegram_message import build_send_message_kwargs
from app.usecase.verification.message import build_verification_message


async def send_verification_message(
    bot: Any,
    *,
    chat_id: int,
    user_id: int,
    user_full_name: str | None = None,
    message_thread_id: int | None = None,
    timeout_seconds: int = 180,
) -> Message:
    verification_message = build_verification_message(
        user_id=user_id,
        user_full_name=user_full_name,
        timeout_seconds=timeout_seconds,
    )
    kwargs = build_send_message_kwargs(
        chat_id=chat_id,
        text=verification_message.text,
        reply_markup=verification_message.reply_markup,
        message_thread_id=message_thread_id,
    )

    return await call_telegram_api(
        operation="send_verification_message",
        call=bot.send_message(**kwargs),
        chat_id=chat_id,
        user_id=user_id,
    )


async def send_join_request_verification_message(
    bot: Any,
    *,
    chat_id: int,
    user_chat_id: int,
    user_id: int,
    user_full_name: str | None = None,
    timeout_seconds: int = 180,
) -> Message:
    verification_message = build_verification_message(
        user_id=user_id,
        user_full_name=user_full_name,
        timeout_seconds=timeout_seconds,
        chat_id=chat_id,
    )
    return await call_telegram_api(
        operation="send_join_request_verification_message",
        call=bot.send_message(
            **build_send_message_kwargs(
                chat_id=user_chat_id,
                text=verification_message.text,
                reply_markup=verification_message.reply_markup,
            )
        ),
        chat_id=chat_id,
        user_id=user_id,
    )
