"""Domain models for spam detection decisions and duplicate state"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.moderation import ModerationAction


class LLMDecision(str, Enum):
    SPAM = "spam"
    NOT_SPAM = "not_spam"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DuplicateMessageState:
    user_id: int
    chat_id: int
    digest: str
    content_key: str
    message_ids: tuple[int, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> DuplicateMessageState:
        return cls(
            user_id=int(data["user_id"]),
            chat_id=int(data["chat_id"]),
            digest=str(data["digest"]),
            content_key=str(data.get("content_key") or data["normalized_text"]),
            message_ids=tuple(int(message_id) for message_id in data["message_ids"]),
        )


@dataclass(frozen=True)
class StopWordCheckResult:
    matched: bool
    matched_term: str | None = None


@dataclass(frozen=True)
class SpamDetectionResult:
    is_spam: bool
    reason: str
    stop_word: StopWordCheckResult = field(
        default_factory=lambda: StopWordCheckResult(matched=False)
    )
    llm_decision: LLMDecision = LLMDecision.UNKNOWN
    moderation_action: ModerationAction = ModerationAction.NONE
    matched_term: str | None = None
