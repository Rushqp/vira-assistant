"""Message rendering shared by handlers and scheduled jobs.

Reminder cards, notifications, the morning briefing, expense cards and reports. All functions
return Telegram HTML; user text (subjects, descriptions) is escaped here.
"""

import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import texts
from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes, RepeatRule
from app.db.models import Category, Reminder
from app.services.expenses import ExpenseDraft
from app.services.reminders import ReminderDraft, from_utc
from app.services.reports import Report, month_name
from app.utils.calendar import JALALI_MONTHS, format_date
from app.utils.formatting import bar, format_money, format_quantity

FULL_GREGORIAN_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip


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


def briefing(reminders: list[Reminder], now: datetime, tz: ZoneInfo, calendar: Calendar) -> str:
    """Today's reminders, important ones first."""

    def item(r: Reminder) -> str:
        clock = texts.REMINDER_ALL_DAY if r.all_day else f"{from_utc(r.event_at, tz):%H:%M}"
        return texts.BRIEFING_ITEM.format(time=clock, subject=html.escape(r.text))

    lines = [texts.BRIEFING_TITLE.format(today=format_date(now.date(), calendar)), ""]
    important = [r for r in reminders if r.important]
    others = [r for r in reminders if not r.important]
    if important:
        lines += [texts.BRIEFING_IMPORTANT, *map(item, important), ""]
    if others:
        lines += [texts.BRIEFING_TODAY, *map(item, others)]
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
    names = JALALI_MONTHS["en"] if calendar == Calendar.JALALI else FULL_GREGORIAN_MONTHS
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
    for entry in report.by_category:
        lines.append(
            texts.REPORT_CATEGORY.format(
                emoji=entry.category.emoji,
                name=html.escape(entry.category.name),
                bar=bar(entry.share),
                percent=f"{entry.share * 100:.0f}",
                amount=format_money(entry.total, currency),
            )
        )
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
        lines += ["", texts.REPORT_ITEMS]
        for n, expense in enumerate(report.expenses[:REPORT_MAX_ITEMS], 1):
            lines.append(
                texts.REPORT_ITEM.format(
                    n=n,
                    emoji=expense.category.emoji,
                    description=html.escape(expense.description or texts.EXPENSE_NO_DESCRIPTION),
                    quantity=format_quantity(expense.quantity, expense.unit),
                    amount=format_money(expense.amount, currency),
                )
            )
        if len(report.expenses) > REPORT_MAX_ITEMS:
            lines.append(texts.REPORT_MORE.format(count=len(report.expenses) - REPORT_MAX_ITEMS))
    return "\n".join(lines)
