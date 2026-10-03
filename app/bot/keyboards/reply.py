from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app import texts


def _row(*labels: str) -> list[KeyboardButton]:
    return [KeyboardButton(text=label) for label in labels]


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            _row(texts.BTN_NEW_CHAT, texts.BTN_NEW_REMINDER),
            _row(texts.BTN_ADD_EXPENSE, texts.BTN_TODAY_REPORT, texts.BTN_MONTH_REPORT),
            _row(texts.BTN_REMINDERS, texts.BTN_TODOS, texts.BTN_NOTES),
            _row(texts.BTN_EXPORT, texts.BTN_SETTINGS),
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=texts.INPUT_PLACEHOLDER,
    )
