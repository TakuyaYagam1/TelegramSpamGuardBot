"""Verification message builders and callback payload helpers"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

VERIFY_CALLBACK_PREFIX = "verify_user"
VERIFY_BUTTON_TEXT = "✅ Я человек"
VERIFY_SUCCESS_CALLBACK_ANSWER = "✅ Готово, доступ открыт"
VERIFY_SUCCESS_PRIVATE_MESSAGE = "✅ Готово, доступ открыт. Добро пожаловать в чат"
VERIFY_WRONG_USER_CALLBACK_ANSWER = "❌ Эта кнопка не для вас"
VERIFY_EXPIRED_CALLBACK_ANSWER = "❌ Проверка уже недействительна"


@dataclass(frozen=True)
class VerificationMessage:
    text: str
    reply_markup: InlineKeyboardMarkup


@dataclass(frozen=True)
class VerifyCallbackPayload:
    user_id: int
    chat_id: int | None = None


def build_verify_callback_data(user_id: int, *, chat_id: int | None = None) -> str:
    if chat_id is None:
        return f"{VERIFY_CALLBACK_PREFIX}:{user_id}"
    return f"{VERIFY_CALLBACK_PREFIX}:{chat_id}:{user_id}"


def parse_verify_callback_payload(
    callback_data: str | None,
) -> VerifyCallbackPayload | None:
    if callback_data is None:
        return None

    parts = callback_data.split(":")
    if len(parts) == 2 and parts[0] == VERIFY_CALLBACK_PREFIX:
        try:
            return VerifyCallbackPayload(user_id=int(parts[1]))
        except ValueError:
            return None

    if len(parts) == 3 and parts[0] == VERIFY_CALLBACK_PREFIX:
        try:
            return VerifyCallbackPayload(chat_id=int(parts[1]), user_id=int(parts[2]))
        except ValueError:
            return None

    return None


def parse_verify_callback_data(callback_data: str | None) -> int | None:
    payload = parse_verify_callback_payload(callback_data)
    if payload is None:
        return None
    return payload.user_id


def format_minutes(minutes: int) -> str:
    normalized_minutes = max(1, minutes)
    if normalized_minutes % 10 == 1 and normalized_minutes % 100 != 11:
        return f"{normalized_minutes} минуту"
    if 2 <= normalized_minutes % 10 <= 4 and not 12 <= normalized_minutes % 100 <= 14:
        return f"{normalized_minutes} минуты"
    return f"{normalized_minutes} минут"


def format_countdown(seconds: float) -> str:
    normalized_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(normalized_seconds, 60)
    return f"{minutes}:{remaining_seconds:02d}"


def build_verification_message(
    *,
    user_id: int,
    user_full_name: str | None = None,
    timeout_seconds: int = 180,
    remaining_seconds: int | None = None,
    chat_id: int | None = None,
) -> VerificationMessage:
    timeout_text = format_minutes(timeout_seconds // 60)
    countdown_text = format_countdown(
        timeout_seconds if remaining_seconds is None else remaining_seconds
    )
    greeting = f"{user_full_name}, " if user_full_name else ""
    if chat_id is None:
        text = (
            f"⚠️ {greeting}подтвердите, что вы человек. "
            f"Нажмите кнопку «{VERIFY_BUTTON_TEXT}». "
            f"У вас {timeout_text}, иначе вы будете удалены из чата.\n\n"
            f"⏳ Осталось: {countdown_text}"
        )
    else:
        text = (
            f"⚠️ {greeting}подтвердите, что вы человек. "
            f"Нажмите кнопку «{VERIFY_BUTTON_TEXT}» в течение {timeout_text}. "
            "До подтверждения вы не можете читать и писать в группе. "
            "После проверки бот откроет доступ к чату.\n\n"
            f"⏳ Осталось: {countdown_text}"
        )
    reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=VERIFY_BUTTON_TEXT,
                    callback_data=build_verify_callback_data(
                        user_id,
                        chat_id=chat_id,
                    ),
                )
            ]
        ]
    )
    return VerificationMessage(text=text, reply_markup=reply_markup)


def build_verification_timeout_message(*, timeout_seconds: float) -> str:
    timeout_text = format_minutes(int(timeout_seconds) // 60)
    return (
        f"❌ Проверка не пройдена за {timeout_text}. "
        "Заявка отклонена, доступ к группе заблокирован."
    )
