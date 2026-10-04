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
            [
                InlineKeyboardButton(
                    text=texts.BTN_CATEGORIES, callback_data=CatCb(action="list").pack()
                ),
                InlineKeyboardButton(
                    text=texts.BTN_AI_MODEL, callback_data=SettingsCb(action="ai").pack()
                ),
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


# --- Expenses ---


class ExpCb(CallbackData, prefix="exp"):
    # scale | save | category | pick | setcat | edit | cancel | undo
    action: str
    value: str = ""
    index: int = 0


def _exp(text: str, action: str, value: str = "", index: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=ExpCb(action=action, value=value, index=index).pack()
    )


def expense_scale(thousand: str, million: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_exp(thousand, "scale", "k"), _exp(million, "scale", "m")],
            [_exp(texts.BTN_CANCEL, "cancel")],
        ]
    )


def expense_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_exp(texts.BTN_SAVE, "save"), _exp(texts.BTN_CATEGORY, "category")],
            [_exp(texts.BTN_EDIT, "edit"), _exp(texts.BTN_CANCEL, "cancel")],
        ]
    )


def expense_items(descriptions: list[str]) -> InlineKeyboardMarkup:
    rows = [[_exp(f"{n}. {d}"[:60], "pick", index=n - 1)] for n, d in enumerate(descriptions, 1)]
    rows.append([_exp(texts.BTN_BACK, "back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_grid(categories: list[tuple[int, str]], index: int) -> InlineKeyboardMarkup:
    """Two categories per row; `categories` is [(id, "🛒 Groceries"), ...]."""
    buttons = [_exp(label, "setcat", str(cid), index) for cid, label in categories]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([_exp(texts.BTN_BACK, "back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def expense_saved() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_exp(texts.BTN_UNDO, "undo")]])


# --- Reports ---


class RepCb(CallbackData, prefix="rep"):
    action: str  # show | delete | confirm_delete
    kind: str = "day"  # day | week | month
    offset: int = 0
    eid: int = 0


def report_nav(kind: str, offset: int, expense_ids: list[int]) -> InlineKeyboardMarkup:
    """Delete buttons (day reports), ◀️ / ▶️ through periods, and day / week / month switches."""
    rows: list[list[InlineKeyboardButton]] = []
    deletes = [
        InlineKeyboardButton(
            text=texts.BTN_DELETE_ITEM.format(n=n),
            callback_data=RepCb(action="delete", kind=kind, offset=offset, eid=eid).pack(),
        )
        for n, eid in enumerate(expense_ids, 1)
    ]
    rows += [deletes[i : i + 5] for i in range(0, len(deletes), 5)]
    nav = [
        InlineKeyboardButton(
            text=texts.BTN_PREV,
            callback_data=RepCb(action="show", kind=kind, offset=offset + 1).pack(),
        )
    ]
    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                text=texts.BTN_NEXT,
                callback_data=RepCb(action="show", kind=kind, offset=offset - 1).pack(),
            )
        )
    rows.append(nav)
    switches = [
        (texts.BTN_REPORT_DAY, "day"),
        (texts.BTN_REPORT_WEEK, "week"),
        (texts.BTN_REPORT_MONTH, "month"),
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=label, callback_data=RepCb(action="show", kind=target, offset=0).pack()
            )
            for label, target in switches
            if target != kind
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_delete_confirm(eid: int, kind: str, offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_YES_DELETE,
                    callback_data=RepCb(
                        action="confirm_delete", kind=kind, offset=offset, eid=eid
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_CANCEL,
                    callback_data=RepCb(action="show", kind=kind, offset=offset).pack(),
                ),
            ]
        ]
    )


# --- Categories (Settings) ---


class CatCb(CallbackData, prefix="cat"):
    action: str  # list | delete | confirm_delete | add
    cid: int = 0


def categories_list(categories: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=CatCb(action="delete", cid=cid).pack())
        for cid, label in categories
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BTN_ADD_CATEGORY, callback_data=CatCb(action="add").pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_delete_confirm(cid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_YES_DELETE,
                    callback_data=CatCb(action="confirm_delete", cid=cid).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BTN_CANCEL, callback_data=CatCb(action="list").pack()
                ),
            ]
        ]
    )


# --- Agent results ---


class ActCb(CallbackData, prefix="act"):
    # undo | edit | alert | cat | setcat | scale
    action: str
    aid: int = 0  # agent action id
    value: str = ""


def _act(text: str, action: str, aid: int = 0, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, callback_data=ActCb(action=action, aid=aid, value=value).pack()
    )


def action_buttons(
    aid: int,
    *,
    edit: bool = True,
    category: bool = False,
    alerts: list[tuple[str, str]] | None = None,
    selected: list[str] | None = None,
) -> InlineKeyboardMarkup:
    """↩️ Undo / ✏️ Edit (+ 🏷 Category, + alert options for a new reminder)."""
    rows: list[list[InlineKeyboardButton]] = []
    if alerts:
        chosen = selected or []
        buttons = [
            _act(
                (texts.BTN_SELECTED + label)
                if spec in chosen
                else texts.BTN_ALERT_ADD.format(label=label),
                "alert",
                aid,
                str(i),
            )
            for i, (spec, label) in enumerate(alerts)
            if spec != "at"
        ]
        rows += [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    main = [_act(texts.BTN_UNDO, "undo", aid)]
    if edit:
        main.append(_act(texts.BTN_EDIT, "edit", aid))
    if category:
        main.append(_act(texts.BTN_CATEGORY, "cat", aid))
    rows.append(main)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def saved_expense_items(aid: int, items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [
        [_act(f"{n}. {label}"[:60], "cat", aid, str(eid))]
        for n, (eid, label) in enumerate(items, 1)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def saved_expense_categories(
    aid: int, expense_id: int, categories: list[tuple[int, str]]
) -> InlineKeyboardMarkup:
    buttons = [_act(label, "setcat", aid, f"{expense_id}.{cid}") for cid, label in categories]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    )


def agent_scale(thousand: str, million: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_act(thousand, "scale", value="k"), _act(million, "scale", value="m")],
            [_act(texts.BTN_CANCEL, "scale", value="cancel")],
        ]
    )


# --- AI model ---


class AiCb(CallbackData, prefix="ai"):
    action: str  # auto | pick
    index: int = 0  # position in the menu's option list (kept in the FSM data)


def ai_models_menu(labels: list[str], selected: int | None) -> InlineKeyboardMarkup:
    """✨ Auto plus one button per model; `selected` is the preferred model's index."""
    auto = texts.BTN_AI_AUTO
    rows = [
        [
            InlineKeyboardButton(
                text=(texts.BTN_SELECTED + auto) if selected is None else auto,
                callback_data=AiCb(action="auto").pack(),
            )
        ]
    ]
    buttons = [
        InlineKeyboardButton(
            text=(texts.BTN_SELECTED + label) if i == selected else label,
            callback_data=AiCb(action="pick", index=i).pack(),
        )
        for i, label in enumerate(labels)
    ]
    rows += [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)
