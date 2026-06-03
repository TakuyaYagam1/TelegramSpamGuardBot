"""Public API for administrator command handlers"""

from app.bot.controller.v1.admin.callback import handle_action_mode_callback
from app.bot.controller.v1.admin.command import (
    handle_action_mode_command,
    handle_admin_panel_command,
    handle_notification_target_command,
    parse_action_mode_argument,
    parse_notification_target_argument,
)
from app.bot.controller.v1.admin.panel import (
    ACTION_MODE_CALLBACK_PREFIX,
    build_action_mode_keyboard,
    build_admin_panel_text,
    parse_action_mode_callback_data,
)
from app.bot.controller.v1.admin.permission import (
    is_admin_sender,
    is_authorized_admin_sender,
)
from app.bot.controller.v1.admin.router import router

__all__ = (
    "ACTION_MODE_CALLBACK_PREFIX",
    "build_action_mode_keyboard",
    "build_admin_panel_text",
    "handle_action_mode_callback",
    "handle_action_mode_command",
    "handle_admin_panel_command",
    "handle_notification_target_command",
    "is_admin_sender",
    "is_authorized_admin_sender",
    "parse_action_mode_argument",
    "parse_action_mode_callback_data",
    "parse_notification_target_argument",
    "router",
)
