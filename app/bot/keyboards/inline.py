from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.config import Calendar

CHATS_PAGE_SIZE = 10


# --- Settings ---


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


# --- Previous chats ---


class ChatsCb(CallbackData, prefix="chats"):
    action: str  # page | open | delete | confirm_delete
    chat_id: int = 0
    page: int = 0


def chats_list(
    chats: list[tuple[int, str]], page: int, total: int, current_id: int | None
) -> InlineKeyboardMarkup:
    """One button per chat (`(id, label)`), plus ◀️ / ▶️ when there is more than one page."""
    rows = [
        [
            InlineKeyboardButton(
                text=(texts.CHATS_CURRENT_MARK if chat_id == current_id else "") + label,
                callback_data=ChatsCb(action="open", chat_id=chat_id, page=page).pack(),
            )
        ]
        for chat_id, label in chats
    ]
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text=texts.BTN_PREV, callback_data=ChatsCb(action="page", page=page - 1).pack()
            )
        )
    if (page + 1) * CHATS_PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text=texts.BTN_NEXT, callback_data=ChatsCb(action="page", page=page + 1).pack()
            )
        )
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_opened(chat_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_DELETE,
                    callback_data=ChatsCb(action="delete", chat_id=chat_id, page=page).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_BACK_TO_CHATS,
                    callback_data=ChatsCb(action="page", page=page).pack(),
                ),
            ]
        ]
    )


def chat_delete_confirm(chat_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_YES_DELETE,
                    callback_data=ChatsCb(
                        action="confirm_delete", chat_id=chat_id, page=page
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_CANCEL,
                    callback_data=ChatsCb(action="open", chat_id=chat_id, page=page).pack(),
                ),
            ]
        ]
    )
