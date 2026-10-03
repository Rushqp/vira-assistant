"""Shared argument parsing for tools: amounts, dates and report periods.

The model gives both the user's words and its interpretation; these helpers turn them into
exact values with the deterministic parsers (Persian amounts, Jalali/Gregorian dates).
"""

import re
from datetime import date, datetime, timedelta
from typing import Literal

import jdatetime

from app.config import Calendar
from app.core.normalizer import normalize
from app.core.parsers.amount_parser import Amount, find_amounts, find_quantities, mask
from app.core.parsers.datetime_parser import find_atoms
from app.services.reports import Kind, period_range

Period = Literal[
    "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "recent"
]
PERIODS: dict[str, tuple[Kind, int]] = {
    "today": ("day", 0),
    "yesterday": ("day", 1),
    "this_week": ("week", 0),
    "last_week": ("week", 1),
    "this_month": ("month", 0),
    "last_month": ("month", 1),
}
RECENT_DAYS = 60

_ISO_DATE = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_YESTERDAY = re.compile(r"\byesterday\b|(?<![\w])دیروز(?![\w])", re.IGNORECASE)
_DAY_BEFORE_YESTERDAY = re.compile(r"day before yesterday|(?<![\w])پریروز(?![\w])", re.IGNORECASE)


def parse_amount_text(text: str) -> Amount | None:
    """The amount in the user's words («۱۵۰ هزار تومن», "3m", «۳ تومن»), or None."""
    normalized = normalize(str(text), lowercase=False)
    masked = mask(normalized, [(q.start, q.end) for q in find_quantities(normalized)])
    amounts = find_amounts(masked)
    if not amounts:
        return None
    explicit = [a for a in amounts if not a.bare]
    return (explicit or amounts)[0]


def iso_to_date(year: int, month: int, day: int) -> date | None:
    """Gregorian, or Jalali when the year looks Jalali (1300–1699)."""
    try:
        if year < 1700:
            return jdatetime.date(year, month, day).togregorian()
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_arg(text: str | None, today: date, prefer_past: bool = False) -> date | None:
    """ "2026-10-05", "1405-07-13", «دیروز», «شنبه», «۱۵ مهر» → date (None if not understood)."""
    if not text or not str(text).strip():
        return None
    raw = str(text)
    if match := _ISO_DATE.match(normalize(raw)):
        return iso_to_date(int(match[1]), int(match[2]), int(match[3]))
    if _DAY_BEFORE_YESTERDAY.search(raw):
        return today - timedelta(days=2)
    if _YESTERDAY.search(raw):
        return today - timedelta(days=1)
    for atom in find_atoms(normalize(raw, lowercase=False), today):
        if atom.kind == "weekday" and atom.weekday is not None:
            if prefer_past:
                return today - timedelta(days=(today.weekday() - atom.weekday) % 7)
            return today + timedelta(days=(atom.weekday - today.weekday()) % 7)
        if atom.kind == "date" and atom.date is not None:
            found = atom.date
            if prefer_past and found > today:
                found = found.replace(year=found.year - 1)
            return found
    return None


def parse_local_datetime(text: str) -> tuple[date | None, datetime | None]:
    """ "2026-10-05T14:00" → (date, datetime); "2026-10-05" → (date, None); Jalali years ok."""
    value = normalize(str(text), lowercase=False).strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[Tt\s]+(\d{1,2}):(\d{2}))?", value)
    if not match:
        return None, None
    day = iso_to_date(int(match[1]), int(match[2]), int(match[3]))
    if day is None:
        return None, None
    if match[4] is None:
        return day, None
    hour, minute = int(match[4]), int(match[5])
    if hour > 23 or minute > 59:
        return day, None
    return day, datetime(day.year, day.month, day.day, hour, minute)


def period_dates(period: str, today: date, calendar: Calendar) -> tuple[date, date]:
    """[start, end) for a period name."""
    if period in PERIODS:
        kind, offset = PERIODS[period]
        return period_range(kind, today, calendar, offset)
    return today - timedelta(days=RECENT_DAYS), today + timedelta(days=1)


def jalali(day: date) -> str:
    j = jdatetime.date.fromgregorian(date=day)
    return f"{j.year}-{j.month:02d}-{j.day:02d}"
