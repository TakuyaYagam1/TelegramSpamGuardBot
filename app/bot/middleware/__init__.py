"""Middleware package exports for aiogram dependency injection"""

from app.bot.middleware.redis import RedisMiddleware

__all__ = ("RedisMiddleware",)
