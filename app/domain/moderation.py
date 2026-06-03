"""Domain models for moderation modes and actions"""

from __future__ import annotations

from enum import Enum


class ActionMode(str, Enum):
    DELETE = "delete"
    NOTIFY_ADMIN = "notify_admin"


class ModerationAction(str, Enum):
    NONE = "none"
    DELETE_MESSAGE = "delete_message"
    NOTIFY_ADMIN = "notify_admin"
    BAN_UNBAN = "ban_unban"
    WARN_USER = "warn_user"
