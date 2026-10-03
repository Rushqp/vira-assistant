"""Message rendering shared by handlers and scheduled jobs.

Reminder cards, notifications and the morning briefing. All functions return Telegram HTML;
user text (reminder subjects) is escaped here.
"""

import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import texts
from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes, RepeatRule
from app.db.models import Reminder
from app.services.reminders import ReminderDraft, from_utc
from app.utils.calendar import format_date


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
