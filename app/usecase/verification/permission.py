"""Telegram member permission helpers for verification flows"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import ChatPermissions

from app.usecase.verification.timeout import call_telegram_api_best_effort

UNVERIFIED_MEMBER_PERMISSIONS = ChatPermissions(can_send_messages=False)
VERIFIED_MEMBER_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_react_to_messages=True,
)


async def restrict_unverified_member(
    *,
    bot: Any,
    chat_id: int,
    user_id: int,
    logger: logging.Logger,
) -> None:
    await call_telegram_api_best_effort(
        operation="restrict_unverified_member",
        call=bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=UNVERIFIED_MEMBER_PERMISSIONS,
        ),
        chat_id=chat_id,
        user_id=user_id,
        logger=logger,
    )
