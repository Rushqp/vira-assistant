"""Message rendering shared by handlers and scheduled jobs.

Reminder cards, notifications, the morning briefing, expense cards, reports and the nightly
report, to-do lists and notes. All functions return Telegram HTML; user text (subjects,
descriptions, notes) is escaped here.
"""

import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import texts
from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes, RepeatRule
from app.db.models import Category, Expense, Note, Reminder, Todo
from app.services.expenses import ExpenseDraft
from app.services.notes import tag_list
from app.services.reminders import ReminderDraft, from_utc
from app.services.reports import Report, month_name
from app.services.todos import DayList
from app.utils.calendar import JALALI_MONTHS, format_date
from app.utils.formatting import bar, format_money, format_quantity


def format_when(event: datetime, all_day: bool, calendar: Calendar) -> str:
    day = format_date(event.date(), calendar)
    return f"{day}, {texts.REMINDER_ALL_DAY}" if all_day else f"{day}, {event:%H:%M}"


def format_alerts(times: list[datetime], event: datetime, calendar: Calendar) -> str:
    """Alert times; the date is shown only when it differs from the event day."""
    parts = []
    for when in times:
        if when.date() == event.date():
            parts.append(f"{when:%H:%M}")
        else:
            parts.append(f"{format_date(when.date(), calendar)}, {when:%H:%M}")
    return " · ".join(parts) or "—"


def format_repeat(rule: str | None) -> str:
    if not rule:
        return ""
    parsed = RepeatRule.parse(rule)
    if parsed.kind == "daily":
        text = texts.REPEAT_DAILY
    elif parsed.kind == "weekly":
        text = texts.REPEAT_WEEKLY.format(weekday=texts.WEEKDAY_NAMES[parsed.weekday or 0])
    else:
        text = texts.REPEAT_MONTHLY.format(
            day=parsed.day, calendar=texts.CALENDAR_NAMES.get(parsed.calendar or "", "")
        )
    return texts.REMINDER_REPEAT_LINE.format(repeat=text)


def _card(
    subject: str,
    event: datetime,
    all_day: bool,
    alert_times: list[datetime],
    repeat: str | None,
    important: bool,
    calendar: Calendar,
) -> str:
    return texts.REMINDER_CARD.format(
        subject=html.escape(subject),
        when=format_when(event, all_day, calendar),
        alerts=format_alerts(alert_times, event, calendar),
        repeat=format_repeat(repeat),
        important=texts.REMINDER_IMPORTANT_LINE if important else "",
    )


def draft_card(draft: ReminderDraft, now: datetime, day_times: DayTimes, calendar: Calendar) -> str:
    event, all_day = draft.event_datetime(now)
    times = [when for when, _ in draft.alert_times(now, day_times)]
    return _card(
        draft.subject, event, all_day, times, draft.repeat, bool(draft.important), calendar
    )


def reminder_card(reminder: Reminder, tz: ZoneInfo, calendar: Calendar) -> str:
    event = from_utc(reminder.event_at, tz)
    times = [from_utc(a.notify_at, tz) for a in reminder.alerts if a.sent_at is None]
    return _card(
        reminder.text,
        event,
        reminder.all_day,
        sorted(times),
        reminder.repeat_rule,
        reminder.important,
        calendar,
    )


def reminder_list_label(reminder: Reminder, tz: ZoneInfo, calendar: Calendar) -> str:
    """Short one-line label for list buttons (plain text)."""
    event = from_utc(reminder.event_at, tz)
    day = format_date(event.date(), calendar, weekday=False)
    clock = "" if reminder.all_day else f" {event:%H:%M}"
    star = "⭐ " if reminder.important else ""
    repeat = " 🔁" if reminder.repeat_rule else ""
    return f"{star}{reminder.text} · {day}{clock}{repeat}"


def humanize(delta: timedelta) -> str:
    minutes = round(delta.total_seconds() / 60)
    if minutes < 60:
        return texts.DURATION_MIN.format(n=max(minutes, 1))
    if minutes < 24 * 60:
        h, m = divmod(minutes, 60)
        return (
            texts.DURATION_HOURS.format(h=h)
            if m == 0
            else texts.DURATION_HOURS_MIN.format(h=h, m=m)
        )
    days = round(minutes / (24 * 60))
    return texts.DURATION_DAY if days == 1 else texts.DURATION_DAYS.format(n=days)


def notification(
    reminder: Reminder, now: datetime, tz: ZoneInfo, calendar: Calendar, late: bool
) -> str:
    event = from_utc(reminder.event_at, tz)
    if reminder.all_day:
        relative = ""
    elif event - now > timedelta(minutes=1):
        relative = texts.NOTIFY_IN.format(delta=humanize(event - now))
    else:
        relative = texts.NOTIFY_NOW
    text = texts.NOTIFY.format(
        subject=html.escape(reminder.text),
        when=format_when(event, reminder.all_day, calendar),
        relative=relative,
    )
    return text + (texts.NOTIFY_LATE if late else "")


def briefing(
    reminders: list[Reminder],
    now: datetime,
    tz: ZoneInfo,
    calendar: Calendar,
    todos: list[Todo] | None = None,
) -> str:
    """Today's reminders, important ones first, and today's open to-dos."""

    def item(r: Reminder) -> str:
        clock = texts.REMINDER_ALL_DAY if r.all_day else f"{from_utc(r.event_at, tz):%H:%M}"
        return texts.BRIEFING_ITEM.format(time=clock, subject=html.escape(r.text))

    lines = [texts.BRIEFING_TITLE.format(today=format_date(now.date(), calendar)), ""]
    important = [r for r in reminders if r.important]
    others = [r for r in reminders if not r.important]
    if important:
        lines += [texts.BRIEFING_IMPORTANT, *map(item, important), ""]
    if others:
        lines += [texts.BRIEFING_TODAY, *map(item, others), ""]
    if todos:
        lines += [texts.BRIEFING_TODOS]
        lines += [
            texts.BRIEFING_TODO.format(
                text=html.escape(t.text), origin=todo_origin(t, now.date(), calendar)
            )
            for t in todos
        ]
    return "\n".join(lines).strip()


# --- Expenses ---


def expense_card(
    draft: ExpenseDraft,
    categories: dict[int, Category],
    currency: str,
    calendar: Calendar,
    today: date,
) -> str:
    title = (
        texts.EXPENSE_CARD_TITLE
        if len(draft.items) == 1
        else texts.EXPENSE_CARD_TITLE_MANY.format(count=len(draft.items))
    )
    lines = [title, ""]
    for n, item in enumerate(draft.items, 1):
        category = categories.get(item.category_id or 0)
        lines.append(
            texts.EXPENSE_CARD_ITEM.format(
                n=n,
                emoji=category.emoji if category else "❔",
                description=html.escape(item.description or texts.EXPENSE_NO_DESCRIPTION),
                quantity=format_quantity(item.quantity, item.unit),
                amount=format_money(item.amount or 0, currency),
            )
        )
    lines.append("")
    spent_on = date.fromisoformat(draft.spent_on) if draft.spent_on else today
    lines.append(texts.EXPENSE_CARD_DATE.format(date=format_date(spent_on, calendar)))
    if len(draft.items) > 1:
        lines.append(texts.EXPENSE_CARD_TOTAL.format(amount=format_money(draft.total, currency)))
    return "\n".join(lines)


# --- Reports ---

REPORT_MAX_ITEMS = 20


def _report_title(report: Report, calendar: Calendar) -> str:
    if report.kind == "day":
        return texts.REPORT_DAY_TITLE.format(date=format_date(report.start, calendar))
    if report.kind == "week":
        last = report.end - timedelta(days=1)
        return texts.REPORT_WEEK_TITLE.format(
            start=format_date(report.start, calendar, weekday=False),
            end=format_date(last, calendar, weekday=False),
        )
    month, year = month_name(report.start, calendar)
    names = JALALI_MONTHS["en"] if calendar == Calendar.JALALI else texts.GREGORIAN_MONTH_NAMES
    return texts.REPORT_MONTH_TITLE.format(month=names[month - 1], year=year)


def _comparison(report: Report, currency: str) -> str:
    previous = report.previous_total
    if previous == 0:
        return texts.REPORT_VS_ZERO if report.total else ""
    change = (report.total - previous) / previous * 100
    return texts.REPORT_VS_PREVIOUS.format(
        arrow="▲" if change >= 0 else "▼",
        percent=f"{abs(change):.0f}",
        previous=f"{texts.REPORT_PREVIOUS[report.kind]}: {format_money(previous, currency)}",
    )


def report(report: Report, currency: str, calendar: Calendar) -> str:
    """Total, comparison, per-category bars, largest expense and (for days) the item list."""
    lines = [_report_title(report, calendar), ""]
    if not report.expenses:
        lines.append(texts.REPORT_EMPTY)
        if report.previous_total:
            lines.append(texts.REPORT_TOTAL.format(amount=format_money(0, currency)))
        return "\n".join(lines)

    lines.append(
        texts.REPORT_TOTAL.format(amount=format_money(report.total, currency))
        + _comparison(report, currency)
    )
    if report.kind != "day":
        average = report.total // report.days_elapsed
        lines.append(texts.REPORT_AVERAGE.format(amount=format_money(average, currency)))
    lines.append("")
    lines += _category_lines(report, currency)
    largest = report.largest
    if largest and len(report.expenses) > 1:
        lines += [
            "",
            texts.REPORT_LARGEST.format(
                description=html.escape(largest.description or texts.EXPENSE_NO_DESCRIPTION),
                amount=format_money(largest.amount, currency),
            ),
        ]
    if report.kind == "day":
        lines += ["", texts.REPORT_ITEMS, *_item_lines(report.expenses, currency)]
    return "\n".join(lines)


def _category_lines(report: Report, currency: str) -> list[str]:
    return [
        texts.REPORT_CATEGORY.format(
            emoji=entry.category.emoji,
            name=html.escape(entry.category.name),
            bar=bar(entry.share),
            percent=f"{entry.share * 100:.0f}",
            amount=format_money(entry.total, currency),
        )
        for entry in report.by_category
    ]


def _item_lines(expenses: list[Expense], currency: str) -> list[str]:
    lines = [
        texts.REPORT_ITEM.format(
            n=n,
            emoji=expense.category.emoji,
            description=html.escape(expense.description or texts.EXPENSE_NO_DESCRIPTION),
            quantity=format_quantity(expense.quantity, expense.unit),
            amount=format_money(expense.amount, currency),
        )
        for n, expense in enumerate(expenses[:REPORT_MAX_ITEMS], 1)
    ]
    if len(expenses) > REPORT_MAX_ITEMS:
        lines.append(texts.REPORT_MORE.format(count=len(expenses) - REPORT_MAX_ITEMS))
    return lines


def expense_count(count: int) -> str:
    """`1 expense` / `3 expenses`."""
    if count == 1:
        return texts.EXPENSE_COUNT["one"]
    return texts.EXPENSE_COUNT["many"].format(count=count)


# --- Nightly report ---


def nightly_report(
    day: Report,
    month: Report,
    tomorrow: list[Reminder],
    tz: ZoneInfo,
    calendar: Calendar,
    currency: str,
    todos: DayList | None = None,
) -> str:
    """Today's expenses, this month so far, today's to-dos and tomorrow's reminders."""
    lines = [texts.NIGHTLY_TITLE.format(today=format_date(day.start, calendar)), ""]
    if day.expenses:
        lines.append(
            texts.NIGHTLY_SPENT.format(
                amount=format_money(day.total, currency), count=expense_count(len(day.expenses))
            )
        )
        lines += [*_category_lines(day, currency), "", *_item_lines(day.expenses, currency)]
    else:
        lines.append(texts.NIGHTLY_NOTHING)
    if month.expenses:
        average = month.total // month.days_elapsed
        lines += [
            "",
            texts.NIGHTLY_MONTH.format(
                amount=format_money(month.total, currency),
                average=format_money(average, currency),
            ),
        ]
    if todos and todos.items:
        done, total = len(todos.done), len(todos.items)
        if done == total:
            lines += ["", texts.NIGHTLY_TODOS_DONE.format(total=total)]
        else:
            names = ", ".join(html.escape(t.text) for t in todos.open[:5])
            if len(todos.open) > 5:
                names += "…"
            lines += ["", texts.NIGHTLY_TODOS_OPEN.format(done=done, total=total, items=names)]
    lines.append("")
    if not tomorrow:
        lines.append(texts.NIGHTLY_TOMORROW_EMPTY)
        return "\n".join(lines)
    lines.append(texts.NIGHTLY_TOMORROW)
    for reminder in tomorrow:
        if reminder.all_day:
            clock = texts.REMINDER_ALL_DAY
        else:
            clock = f"{from_utc(reminder.event_at, tz):%H:%M}"
        lines.append(
            texts.NIGHTLY_ITEM.format(
                star="⭐ " if reminder.important else "",
                time=clock,
                subject=html.escape(reminder.text),
            )
        )
    return "\n".join(lines)


# --- To-dos ---


def todo_origin(todo: Todo, day: date, calendar: Calendar) -> str:
    """` (Sat 12 Mehr)` for a task carried over from an earlier day."""
    if todo.due_date >= day:
        return ""
    return texts.TODO_ORIGIN.format(day=format_date(todo.due_date, calendar))


def todo_line(todo: Todo, day: date, calendar: Calendar) -> str:
    template = texts.TODO_DONE if todo.done else texts.TODO_OPEN
    return template.format(text=html.escape(todo.text), origin=todo_origin(todo, day, calendar))


def todo_list(day_list: DayList, calendar: Calendar) -> str:
    """A day's tasks: unfinished ones from earlier days first, then the day's own."""
    day = day_list.day
    lines = [texts.TODOS_TITLE.format(day=format_date(day, calendar))]
    if not day_list.items:
        return "\n".join([*lines, "", texts.TODOS_EMPTY])
    if day_list.carried:
        lines += ["", texts.TODOS_CARRIED, *(todo_line(t, day, calendar) for t in day_list.carried)]
        if day_list.planned:
            lines += ["", texts.TODOS_PLANNED]
    else:
        lines.append("")
    lines += [todo_line(t, day, calendar) for t in day_list.planned]
    done, total = len(day_list.done), len(day_list.items)
    lines += ["", texts.TODOS_PROGRESS.format(done=done, total=total)]
    return "\n".join(lines)


# --- Notes ---

NOTE_BODY_MAX = 3000  # characters of a note shown in one message


def _tags(note: Note) -> str:
    return " ".join(f"#{t}" for t in tag_list(note))


def notes_list(
    notes: list[Note],
    total: int,
    tz: ZoneInfo,
    calendar: Calendar,
    query: str | None = None,
    first: int = 1,
) -> str:
    title = (
        texts.NOTES_FOUND.format(query=html.escape(query))
        if query
        else texts.NOTES_TITLE.format(count=total)
    )
    if not notes:
        return f"{title}\n\n{texts.NOTES_EMPTY}"
    lines = [title, ""]
    for n, note in enumerate(notes, first):
        tags = _tags(note)
        lines.append(
            texts.NOTES_ITEM.format(
                n=n,
                pin=texts.NOTE_PIN if note.pinned else "",
                title=html.escape(note.title),
                tags=f" {html.escape(tags)}" if tags else "",
                date=format_date(from_utc(note.created_at, tz).date(), calendar, weekday=False),
            )
        )
    if not query:
        lines += ["", texts.NOTES_SEARCH_HINT]
    return "\n".join(lines)


def note_card(note: Note, tz: ZoneInfo, calendar: Calendar, heading: str = "") -> str:
    """A note in full (long texts are cut to one message), with its summary and tags."""
    tags = _tags(note)
    meta = texts.NOTE_META.format(
        tags=f"{html.escape(tags)}\n" if tags else "",
        date=format_date(from_utc(note.created_at, tz).date(), calendar),
    )
    if note.source == "voice":
        meta += texts.NOTE_VOICE
    body = note.text[:NOTE_BODY_MAX]
    more = (
        texts.NOTE_MORE.format(count=len(note.text) - NOTE_BODY_MAX)
        if note.text[NOTE_BODY_MAX:]
        else ""
    )
    summary = texts.NOTE_SUMMARY.format(summary=html.escape(note.summary)) if note.summary else ""
    card = texts.NOTE_CARD.format(
        title=html.escape(note.title),
        pin=" 📌" if note.pinned else "",
        meta=meta,
        body=summary + html.escape(body) + more,
    )
    return f"{heading}\n\n{card}" if heading else card
