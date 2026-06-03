"""Bootstrap package for application composition and lifecycle wiring"""

from app.bootstrap.application import (
    ALLOWED_UPDATES,
    BotApplication,
    create_application,
    run_polling,
)

__all__ = [
    "ALLOWED_UPDATES",
    "BotApplication",
    "create_application",
    "run_polling",
]
