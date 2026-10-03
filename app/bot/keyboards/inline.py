from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.config import Calendar


class SettingsCb(CallbackData, prefix="settings"):
    action: str


def settings_menu(current_calendar: Calendar) -> InlineKeyboardMarkup:
    other = Calendar.GREGORIAN if current_calendar == Calendar.JALALI else Calendar.JALALI
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_SWITCH_CALENDAR.format(calendar=texts.CALENDAR_NAMES[other]),
                    callback_data=SettingsCb(action="toggle_calendar").pack(),
                )
            ]
        ]
    )
