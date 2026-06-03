"""Public exports for version 1 Telegram moderation controller"""

from app.bot.controller.v1.moderation.router import handle_text_message, router

__all__ = ("handle_text_message", "router")
