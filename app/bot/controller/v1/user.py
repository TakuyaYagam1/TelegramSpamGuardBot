"""User-facing router that combines verification and moderation handlers"""

from aiogram import Router

from app.bot.controller.v1.moderation import router as moderation_router
from app.bot.controller.v1.verification import router as verification_router

router = Router(name="user")
router.include_router(verification_router)
router.include_router(moderation_router)

__all__ = ("router",)
