"""Domain model for pending Telegram verification state"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PendingVerification:
    user_id: int
    chat_id: int
    verification_message_id: int
    created_at: str
    message_thread_id: int | None = None
    verification_chat_id: int | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> PendingVerification:
        return cls(
            user_id=int(data["user_id"]),
            chat_id=int(data["chat_id"]),
            verification_message_id=int(data["verification_message_id"]),
            created_at=str(data["created_at"]),
            message_thread_id=(
                None
                if data.get("message_thread_id") is None
                else int(data["message_thread_id"])
            ),
            verification_chat_id=(
                None
                if data.get("verification_chat_id") is None
                else int(data["verification_chat_id"])
            ),
        )
