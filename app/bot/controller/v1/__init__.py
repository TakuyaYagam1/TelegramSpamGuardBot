"""Version 1 Telegram controller router exports"""

from app.bot.controller.v1.admin import router as admin_router
from app.bot.controller.v1.moderation import router as moderation_router
from app.bot.controller.v1.user import router as user_router
from app.bot.controller.v1.verification import router as verification_router

__all__ = (
    "admin_router",
    "moderation_router",
    "user_router",
    "verification_router",
)
