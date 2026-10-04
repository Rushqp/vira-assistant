"""Rendering agent results: one Telegram message (HTML text + buttons) per tool card.

Cards are built from the database, so the user always sees what really happened.
Also renders the notices about AI model switches (`render_notice`, `send_notices`).
"""

import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from loguru import logger

from app import texts
from app.agent.tools import Card
from app.bot import views
from app.bot.keyboards.inline import action_buttons, alert_options, notes_list, todo_list
from app.config import Calendar, Settings
from app.db.models import Expense
from app.llm.providers import Notice
from app.services.expenses import ExpenseService
from app.services.notes import NoteService
from app.services.reminders import ReminderService, from_utc
from app.services.settings import (
    KEY_BRIEFING,
    KEY_BRIEFING_TIME,
    KEY_CALENDAR,
    KEY_NIGHTLY,
    KEY_NIGHTLY_TIME,
    SettingsService,
)
from app.services.todos import TodoService
from app.utils.calendar import format_date, now_local
from app.utils.formatting import format_money, format_quantity

Rendered = tuple[str, InlineKeyboardMarkup | None]


@dataclass
class UiDeps:
    config: Settings
    calendar: Calendar
    expenses: ExpenseService
    reminders: ReminderService
    settings: SettingsService
    notes: NoteService | None = None  # created from the session when not given
    todos: TodoService | None = None

    def __post_init__(self) -> None:
        self.notes = self.notes or NoteService(self.expenses.session)
        self.todos = self.todos or TodoService(self.expenses.session)

    @property
    def currency(self) -> str:
        return texts.CURRENCY_LABELS[self.config.currency.value]


def _expense_line(n: int, expense: Expense, currency: str) -> str:
    return texts.REPORT_ITEM.format(
        n=n,
        emoji=expense.category.emoji,
        description=html.escape(expense.description or texts.EXPENSE_NO_DESCRIPTION),
        quantity=format_quantity(expense.quantity, expense.unit),
        amount=format_money(expense.amount, currency),
    )


async def render_saved_expenses(aid: int, ids: list[int], deps: UiDeps) -> Rendered | None:
    expenses = await deps.expenses.by_ids(ids)
    if not expenses:
        return None
    lines = [texts.AGENT_EXPENSES_SAVED, ""]
    lines += [_expense_line(n, e, deps.currency) for n, e in enumerate(expenses, 1)]
    day = from_utc(expenses[0].spent_at, deps.config.timezone).date()
    lines += ["", texts.EXPENSE_CARD_DATE.format(date=format_date(day, deps.calendar))]
    if len(expenses) > 1:
        total = sum(e.amount for e in expenses)
        lines.append(texts.EXPENSE_CARD_TOTAL.format(amount=format_money(total, deps.currency)))
    return "\n".join(lines), action_buttons(aid, category=True)


async def render_reminder(
    aid: int, reminder_id: int, deps: UiDeps, *, saved: bool, ask_alerts: bool
) -> Rendered | None:
    reminder = await deps.reminders.get(reminder_id)
    if reminder is None:
        return None
    card = views.reminder_card(reminder, deps.config.timezone, deps.calendar)
    template = texts.AGENT_REMINDER_SAVED if saved else texts.AGENT_REMINDER_UPDATED
    text = template.format(card=card)
    options = None
    if ask_alerts:
        event = from_utc(reminder.event_at, deps.config.timezone)
        clock = None if reminder.all_day else f"{event:%H:%M}"
        options = alert_options(reminder.all_day, clock, deps.config.day_times)
        text += texts.AGENT_ASK_ALERTS
    selected = [s for s in reminder.alert_specs.split(",") if s]
    return text, action_buttons(aid, alerts=options, selected=selected)


def _listed(title: str, items: list[str]) -> str:
    return "\n".join([title, "", *(texts.AGENT_LIST_ITEM.format(text=i) for i in items)])


def _when(value: str, deps: UiDeps) -> str:
    if "T" in value:
        moment = datetime.fromisoformat(value)
        return f"{format_date(moment.date(), deps.calendar)}, {moment:%H:%M}"
    return format_date(datetime.fromisoformat(value).date(), deps.calendar)


async def render_card(card: Card, deps: UiDeps) -> Rendered | None:
    aid = card.action_id or 0
    data = card.data
    match card.kind:
        case "expenses_saved":
            return await render_saved_expenses(aid, data["ids"], deps)
        case "expenses_deleted":
            items = [
                f"{html.escape(i['description'] or texts.EXPENSE_NO_DESCRIPTION)} — "
                f"{format_money(i['amount'], deps.currency)}"
                for i in data["items"]
            ]
            return _listed(texts.AGENT_EXPENSES_DELETED, items), action_buttons(aid, edit=False)
        case "expense_updated":
            expense = await deps.expenses.get(data["id"])
            if expense is None:
                return None
            text = "\n".join(
                [texts.AGENT_EXPENSE_UPDATED, "", _expense_line(1, expense, deps.currency)]
            )
            return text, action_buttons(aid, category=True)
        case "reminder_saved":
            return await render_reminder(
                aid, data["id"], deps, saved=True, ask_alerts=data.get("ask_alerts", False)
            )
        case "reminder_updated":
            return await render_reminder(aid, data["id"], deps, saved=False, ask_alerts=False)
        case "reminders_cancelled":
            items = [
                f"{html.escape(i['subject'])} — {_when(i['start'], deps)}" for i in data["items"]
            ]
            return _listed(texts.AGENT_REMINDERS_CANCELLED, items), action_buttons(aid, edit=False)
        case "report":
            from app.bot.handlers.reports import render_report  # avoid an import cycle

            return await render_report(
                data["kind"], data["offset"], deps.config, deps.expenses, deps.settings
            )
        case "settings":
            lines = [texts.AGENT_SETTINGS_CHANGED, ""]
            for key, value in data["changes"].items():
                if key == KEY_CALENDAR:
                    lines.append(
                        texts.AGENT_SETTING_CALENDAR.format(value=texts.CALENDAR_NAMES[value])
                    )
                elif key in _SETTING_LINES:
                    lines.append(_SETTING_LINES[key].format(value=value))
            return "\n".join(lines), action_buttons(aid, edit=False)
        case "todos_added" | "todos_updated" | "todos_deleted" | "todos_list":
            return await _render_todos(card, deps)
        case "note_saved" | "note_updated" | "notes_deleted" | "notes_found":
            return await _render_notes(card, deps)
    return None


async def _render_todos(card: Card, deps: UiDeps) -> Rendered | None:
    assert deps.todos is not None
    aid = card.action_id or 0
    today = now_local(deps.config.timezone).date()
    if card.kind == "todos_deleted":
        items = [html.escape(t) for t in card.data["items"]]
        return _listed(texts.AGENT_TODOS_DELETED, items), action_buttons(aid, edit=False)
    if card.kind == "todos_list":
        day = date.fromisoformat(card.data["day"])
        day_list = await deps.todos.day_list(day, today)
        entries = [(t.id, t.text, t.done) for t in day_list.items]
        return views.todo_list(day_list, deps.calendar), todo_list(day, today, entries)
    todos = await deps.todos.by_ids(card.data["ids"])
    if not todos:
        return None
    lines = [views.todo_line(t, today, deps.calendar) for t in todos]
    if card.kind == "todos_added":
        title = texts.AGENT_TODOS_ADDED.format(day=format_date(todos[0].due_date, deps.calendar))
        return "\n".join([title, "", *lines]), action_buttons(aid)
    for i, todo in enumerate(todos):  # updated: show the day of tasks not for today
        if todo.due_date != today:
            lines[i] += texts.TODO_ORIGIN.format(day=format_date(todo.due_date, deps.calendar))
    return "\n".join([texts.AGENT_TODOS_UPDATED, "", *lines]), action_buttons(aid, edit=False)


async def _render_notes(card: Card, deps: UiDeps) -> Rendered | None:
    assert deps.notes is not None
    aid = card.action_id or 0
    tz = deps.config.timezone
    if card.kind == "notes_deleted":
        items = [html.escape(t) for t in card.data["items"]]
        return _listed(texts.AGENT_NOTES_DELETED, items), action_buttons(aid, edit=False)
    if card.kind == "notes_found":
        from app.bot.handlers.notes import note_label  # avoid an import cycle

        notes = await deps.notes.by_ids(card.data["ids"])
        order = {nid: i for i, nid in enumerate(card.data["ids"])}  # best match first
        notes.sort(key=lambda n: order[n.id])
        text = views.notes_list(notes, len(notes), tz, deps.calendar, card.data["query"] or None)
        return text, notes_list([(n.id, note_label(n)) for n in notes], 0, 1)
    note = await deps.notes.get(card.data["id"])
    if note is None:
        return None
    heading = texts.AGENT_NOTE_SAVED if card.kind == "note_saved" else texts.AGENT_NOTE_UPDATED
    return views.note_card(note, tz, deps.calendar, heading), action_buttons(aid)


_SETTING_LINES = {
    KEY_BRIEFING: texts.AGENT_SETTING_BRIEFING,
    KEY_BRIEFING_TIME: texts.AGENT_SETTING_BRIEFING_TIME,
    KEY_NIGHTLY: texts.AGENT_SETTING_NIGHTLY,
    KEY_NIGHTLY_TIME: texts.AGENT_SETTING_NIGHTLY_TIME,
}


# --- Files ---


def file_caption(caption: dict, deps: UiDeps) -> str:
    title = html.escape(caption.get("title", ""))
    match caption.get("kind"):
        case "expenses":
            return texts.EXPORT_CAPTION_EXPENSES.format(
                title=title,
                count=views.expense_count(caption.get("count", 0)),
                total=format_money(caption.get("total", 0), deps.currency),
            )
        case "reminders":
            return texts.EXPORT_CAPTION_REMINDERS.format(title=title, count=caption.get("count", 0))
    return texts.EXPORT_CAPTION_TABLE.format(title=title)


async def send_file(target: Message, card: Card, deps: UiDeps) -> None:
    """A "file" card: the document with a short caption."""
    if not card.attachment:
        return
    document = BufferedInputFile(card.attachment, filename=card.data["filename"])
    await target.answer_document(document, caption=file_caption(card.data["caption"], deps))


# --- Model switch notices ---


def render_notice(notice: Notice, tz: ZoneInfo) -> str:
    def reason(kind: str) -> str:
        return texts.AI_REASONS.get(kind, kind)

    voice = notice.task == "voice"
    if notice.kind == "switched":
        text = (texts.VOICE_SWITCHED if voice else texts.AI_SWITCHED).format(
            previous=html.escape(notice.previous),
            reason=reason(notice.reason),
            model=html.escape(notice.model),
        )
        if notice.retry_in:
            at = datetime.now(tz) + timedelta(seconds=notice.retry_in)
            text += texts.AI_SWITCHED_RETRY.format(time=f"{at:%H:%M}")
        return text
    if notice.kind == "restored":
        restored = texts.VOICE_RESTORED if voice else texts.AI_RESTORED
        return restored.format(model=html.escape(notice.model))
    reasons = ", ".join(
        f"{html.escape(label)}: {reason(kind)}" for label, kind in notice.reasons.items()
    )
    return (texts.VOICE_DOWN if voice else texts.AI_DOWN).format(reasons=reasons or "—")


async def send_notices(bot: Bot, chat_id: int, llm: object, tz: ZoneInfo) -> None:
    """Send the model notices collected since the last call (no-op for a plain client)."""
    drain = getattr(llm, "drain_notices", None)
    if drain is None:
        return
    for notice in drain():
        try:
            await bot.send_message(chat_id, render_notice(notice, tz))
        except TelegramAPIError as exc:
            logger.warning("Could not send a model notice: {}", exc)
