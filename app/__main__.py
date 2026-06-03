"""Command-line entrypoint for running the bot application"""

from __future__ import annotations

import argparse
import asyncio

from app.bootstrap.application import (
    ALLOWED_UPDATES,
    BotApplication,
    create_application,
    run_polling,
)
from app.bootstrap.command import BOT_COMMANDS, set_bot_commands
from app.bootstrap.verification_timer import (
    pending_verification_ttl_seconds,
    restore_pending_verification_timer,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Run TelegramSpamGuardBot",
    )
    return parser


def main() -> None:
    build_parser().parse_args()
    asyncio.run(run_polling())


__all__ = [
    "ALLOWED_UPDATES",
    "BOT_COMMANDS",
    "BotApplication",
    "build_parser",
    "create_application",
    "main",
    "pending_verification_ttl_seconds",
    "restore_pending_verification_timer",
    "run_polling",
    "set_bot_commands",
]


if __name__ == "__main__":
    main()
