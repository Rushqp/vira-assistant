"""Per-message context: the current time and nearby dates in both calendars.

It is sent with every user message instead of the system prompt, so the system prompt stays
identical between messages (prompt caching). The model never does calendar arithmetic: it looks
dates up here, and tools re-check dates with the deterministic parser.
"""

from datetime import date, datetime, timedelta

import jdatetime

from app.config import Calendar
from app.utils.calendar import JALALI_MONTHS, WEEKDAYS

WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
LABELS = {-1: "yesterday / دیروز", 0: "today / امروز", 1: "tomorrow / فردا", 2: "پس‌فردا"}


def date_line(day: date, label: str = "") -> str:
    """`2026-10-05 Monday = 1405-07-13 (13 مهر 1405) دوشنبه — tomorrow`."""
    j = jdatetime.date.fromgregorian(date=day)
    weekday = day.weekday()
    text = (
        f"{day.isoformat()} {WEEKDAYS_EN[weekday]} = {j.year}-{j.month:02d}-{j.day:02d} "
        f"({j.day} {JALALI_MONTHS['fa'][j.month - 1]} {j.year}) {WEEKDAYS['fa'][weekday]}"
    )
    return f"{text} — {label}" if label else text


def build_context(now: datetime, calendar: Calendar, currency: str) -> str:
    lines = [
        "[context]",
        f"now: {now:%Y-%m-%d %H:%M} ({now.tzinfo}) {WEEKDAYS_EN[now.weekday()]}",
        f"user's calendar: {calendar.value} · currency: {currency}",
        "dates (Gregorian = Jalali):",
    ]
    for offset in range(-2, 9):
        lines.append("  " + date_line(now.date() + timedelta(days=offset), LABELS.get(offset, "")))
    lines.append("[/context]")
    return "\n".join(lines)
