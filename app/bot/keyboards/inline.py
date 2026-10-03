from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes

CHATS_PAGE_SIZE = 10


# --- Settings ---


class SettingsCb(CallbackData, prefix="settings"):
    action: str


def settings_menu(current_calendar: Calendar, briefing: bool = True) -> InlineKeyboardMarkup:
    other = Calendar.GREGORIAN if current_calendar == Calendar.JALALI else Calendar.JALALI
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_SWITCH_CALENDAR.format(calendar=texts.CALENDAR_NAMES[other]),
                    callback_data=SettingsCb(action="toggle_calendar").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_BRIEFING_OFF if briefing else texts.BTN_BRIEFING_ON,
                    callback_data=SettingsCb(action="toggle_briefing").pack(),
                )
            ],
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


# --- Reminders ---


class RemCb(CallbackData, prefix="rem"):
    # Creating: ampm | time | alert | alerts_done | alert_other | save | star | edit | cancel
    # Notifications: done | snooze — List: open | delete | confirm_delete | list | item_edit
    action: str
    value: str = ""
    rid: int = 0


def _btn(text: str, action: str, value: str = "", rid: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=RemCb(action=action, value=value, rid=rid).pack()
    )


def reminder_ampm(am: str, pm: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_AM.format(time=am), "ampm", "am"),
                _btn(texts.BTN_PM.format(time=pm), "ampm", "pm"),
            ],
            [_btn(texts.BTN_CANCEL, "cancel")],
        ]
    )


def reminder_times(day_times: DayTimes) -> InlineKeyboardMarkup:
    """Part-of-day buttons when a clock time is needed."""
    rows = [
        [
            _btn(
                texts.BTN_PART_TIMES[part].format(time=f"{day_times.of(part):%H:%M}"),
                "time",
                part,
            )
        ]
        for part in ("morning", "noon", "afternoon", "evening", "night")
    ]
    rows.append([_btn(texts.BTN_CANCEL, "cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alert_options(
    all_day: bool, event_time: str | None, day_times: DayTimes
) -> list[tuple[str, str]]:
    """(spec, label) choices for "when should I remind you?".

    The order is stable because buttons refer to options by index.
    """
    morning = f"{day_times.morning:%H:%M}"
    night = f"{day_times.night:%H:%M}"
    options: list[tuple[str, str]] = []
    if not all_day:
        options += [
            ("at", texts.ALERT_LABELS["at"]),
            ("before:15", texts.ALERT_LABELS["before:15"]),
            ("before:60", texts.ALERT_LABELS["before:60"]),
        ]
    if all_day or (event_time and event_time > morning):
        options.append((f"same_day:{morning}", texts.ALERT_LABELS["same_day"].format(time=morning)))
    options.append((f"day_before:{night}", texts.ALERT_LABELS["day_before"].format(time=night)))
    return options


def reminder_alerts(options: list[tuple[str, str]], selected: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [_btn((texts.BTN_SELECTED if spec in selected else "") + label, "alert", str(i))]
        for i, (spec, label) in enumerate(options)
    ]
    rows.append([_btn(texts.BTN_OTHER_TIME, "alert_other")])
    rows.append([_btn(texts.BTN_ALERTS_DONE, "alerts_done"), _btn(texts.BTN_CANCEL, "cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_confirm(important: bool) -> InlineKeyboardMarkup:
    star = texts.BTN_IMPORTANT_ON if important else texts.BTN_IMPORTANT_OFF
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(texts.BTN_SAVE, "save"), _btn(star, "star")],
            [_btn(texts.BTN_EDIT, "edit"), _btn(texts.BTN_CANCEL, "cancel")],
        ]
    )


def reminder_notification(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_NOTIFY_DONE, "done", rid=reminder_id),
                _btn(texts.BTN_SNOOZE_10, "snooze", "10", reminder_id),
                _btn(texts.BTN_SNOOZE_60, "snooze", "60", reminder_id),
            ]
        ]
    )


def reminders_list(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(label, "open", rid=rid)] for rid, label in items]
    )


def reminder_detail(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_EDIT, "item_edit", rid=reminder_id),
                _btn(texts.BTN_DELETE, "delete", rid=reminder_id),
            ],
            [_btn(texts.BTN_BACK, "list")],
        ]
    )


def reminder_delete_confirm(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_YES_DELETE, "confirm_delete", rid=reminder_id),
                _btn(texts.BTN_CANCEL, "open", rid=reminder_id),
            ]
        ]
    )
