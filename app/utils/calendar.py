"""Gregorian / Jalali date formatting in English (UI) or Persian (replies to Persian messages).

All datetimes are stored in UTC and converted to the user's timezone for display.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import jdatetime

from app.config import Calendar
from app.core.normalizer import Language, to_persian_digits

# Index 0 = Monday, matching `date.weekday()`.
WEEKDAYS = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "fa": ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"),
}
JALALI_MONTHS = {
    "en": (
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
    ),
    "fa": (
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ),
}
GREGORIAN_MONTHS = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "fa": (
        "ژانویه",
        "فوریه",
        "مارس",
        "آوریل",
        "مه",
        "ژوئن",
        "ژوئیه",
        "اوت",
        "سپتامبر",
        "اکتبر",
        "نوامبر",
        "دسامبر",
    ),
}


def to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert a datetime to `tz`. Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def now_local(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def format_date(d: date, calendar: Calendar, lang: Language = "en", *, weekday: bool = True) -> str:
    """e.g. `Sat 11 Mehr 1405` / `Sat 3 Oct 2026`, or `شنبه ۱۱ مهر ۱۴۰۵` with `lang="fa"`."""
    if calendar == Calendar.JALALI:
        j = jdatetime.date.fromgregorian(date=d)
        text = f"{j.day} {JALALI_MONTHS[lang][j.month - 1]} {j.year}"
    else:
        text = f"{d.day} {GREGORIAN_MONTHS[lang][d.month - 1]} {d.year}"
    if weekday:
        text = f"{WEEKDAYS[lang][d.weekday()]} {text}"
    return to_persian_digits(text) if lang == "fa" else text


def format_datetime(dt: datetime, calendar: Calendar, tz: ZoneInfo) -> str:
    """e.g. `Sat 11 Mehr 1405, 19:36` in the user's timezone."""
    local = to_local(dt, tz)
    return f"{format_date(local.date(), calendar)}, {local:%H:%M}"
