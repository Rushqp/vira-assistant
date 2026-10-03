"""Gregorian / Jalali date formatting.

All datetimes are stored in UTC and converted to the user's timezone for display.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import jdatetime

from app.config import Calendar

JALALI_MONTHS = (
    "Farvardin",
    "Ordibehesht",
    "Khordad",
    "Tir",
    "Mordad",
    "Shahrivar",
    "Mehr",
    "Aban",
    "Azar",
    "Dey",
    "Bahman",
    "Esfand",
)
GREGORIAN_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert a datetime to `tz`. Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def now_local(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def format_date(d: date, calendar: Calendar) -> str:
    """e.g. `Sat 11 Mehr 1405` (Jalali) or `Sat 3 Oct 2026` (Gregorian)."""
    weekday = WEEKDAYS[d.weekday()]
    if calendar == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=d)
        return f"{weekday} {j.day} {JALALI_MONTHS[j.month - 1]} {j.year}"
    return f"{weekday} {d.day} {GREGORIAN_MONTHS[d.month - 1]} {d.year}"


def format_datetime(dt: datetime, calendar: Calendar, tz: ZoneInfo) -> str:
    """e.g. `Sat 11 Mehr 1405, 19:36` in the user's timezone."""
    local = to_local(dt, tz)
    return f"{format_date(local.date(), calendar)}, {local:%H:%M}"
