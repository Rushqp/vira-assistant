"""Finds date / time expressions ("atoms") in normalized Persian + English text.

Input must be passed through `app.core.normalizer.normalize` first (ASCII digits, unified ZWNJ
compounds, number words as digits). Matching is case-insensitive, so the original case is kept.

Each atom remembers its span so callers can tell which expressions belong together and remove
them from the text. `resolve()` merges a group of atoms into one `Moment`.

Supported (fa + en), for example:
- relative days:    امروز / فردا / پس‌فردا / امشب · today / tomorrow / day after tomorrow / tonight
- weekdays:         شنبه، سه‌شنبه آینده · saturday, next tuesday
- Jalali dates:     ۱۵ مهر، پنجم آبان ۱۴۰۵ · 15 mehr, mehr 15
- Gregorian dates:  ۷ اکتبر · oct 7, 7 october 2026 · 2026-10-07 · 1405/07/15
- times:            ساعت ۲، ۲ و نیم، ربع به ۳، ۸ شب · at 2, 2:30, 2pm, half past 2, noon
- parts of day:     صبح، ظهر، بعدازظهر، عصر، شب · morning, afternoon, evening, night
- from now:         ۱۰ دقیقه دیگه، نیم ساعت دیگه · in 10 minutes, in half an hour
- before an event:  ۱ ساعت قبلش، شب قبلش · 1 hour before, the night before
- repeats:          هر روز، هر شنبه، هر ماه ۵ام · every day, every saturday, monthly
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, time, timedelta
from typing import Literal

import jdatetime

from app.core.normalizer import ZWNJ

Part = Literal["morning", "noon", "afternoon", "evening", "night", "midnight"]

Z = ZWNJ
B = rf"(?<![\w{Z}])"  # word start (Persian letters are \w; ZWNJ joins words)
E = rf"(?![\w{Z}])"  # word end


@dataclass(frozen=True)
class DayTimes:
    """Default clock times for parts of the day (configurable in `.env`)."""

    morning: time = time(9)
    noon: time = time(12)
    afternoon: time = time(16)
    evening: time = time(19)
    night: time = time(22)

    def of(self, part: Part) -> time:
        return time(0) if part == "midnight" else getattr(self, part)


@dataclass(frozen=True)
class RepeatRule:
    kind: Literal["daily", "weekly", "monthly"]
    weekday: int | None = None  # weekly: 0 = Monday
    day: int | None = None  # monthly: day of month
    calendar: str | None = None  # monthly: "jalali" | "gregorian"

    def serialize(self) -> str:
        if self.kind == "weekly":
            return f"weekly:{self.weekday}"
        if self.kind == "monthly":
            return f"monthly:{self.calendar}:{self.day}"
        return "daily"

    @classmethod
    def parse(cls, value: str) -> RepeatRule:
        kind, *rest = value.split(":")
        if kind == "weekly":
            return cls("weekly", weekday=int(rest[0]))
        if kind == "monthly":
            return cls("monthly", calendar=rest[0], day=int(rest[1]))
        return cls("daily")


@dataclass
class Atom:
    start: int
    end: int
    kind: Literal["date", "weekday", "time", "part", "relative", "before", "day_before", "repeat"]
    date: date | None = None
    weekday: int | None = None
    next_week: bool = False
    hour: int | None = None
    minute: int = 0
    meridiem: Literal["am", "pm", "24h"] | None = None
    part: Part | None = None
    delta: timedelta | None = None
    minutes_before: int | None = None
    repeat: RepeatRule | None = None


@dataclass
class Moment:
    """A group of atoms merged into one point in time (fields are None when not mentioned)."""

    date: date | None = None
    flexible_week: bool = False  # weekday that is today: move a week ahead if the time passed
    time: time | None = None
    ambiguous: bool = False  # hour 1–12 without am/pm: `time` holds the AM reading
    delta: timedelta | None = None  # "in 10 minutes"
    minutes_before: int | None = None  # "1 hour before"
    day_before: time | None = None  # "the night before" → time on the previous day
    repeat: RepeatRule | None = None

    @property
    def empty(self) -> bool:
        return (
            self.date is None
            and self.time is None
            and self.delta is None
            and self.minutes_before is None
            and self.day_before is None
            and self.repeat is None
        )


# --- Vocabulary ---

WEEKDAYS_FA = {
    "شنبه": 5,
    f"یک{Z}شنبه": 6,
    f"دو{Z}شنبه": 0,
    f"سه{Z}شنبه": 1,
    f"چهار{Z}شنبه": 2,
    f"پنج{Z}شنبه": 3,
    "جمعه": 4,
}
# Full names only: abbreviations like "sat", "sun", "wed" are ordinary English words.
WEEKDAYS_EN = {
    "monday": 0, "tuesday": 1, "tues": 1, "wednesday": 2, "thursday": 3, "thurs": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}  # fmt: skip
JALALI_MONTHS_FA = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "امرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}  # fmt: skip
JALALI_MONTHS_EN = {
    "farvardin": 1, "ordibehesht": 2, "khordad": 3, "tir": 4, "mordad": 5, "amordad": 5,
    "shahrivar": 6, "mehr": 7, "aban": 8, "azar": 9, "dey": 10, "dei": 10, "bahman": 11,
    "esfand": 12,
}  # fmt: skip
GREGORIAN_MONTHS_EN = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4,
    "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}  # fmt: skip
GREGORIAN_MONTHS_FA = {
    "ژانویه": 1, "فوریه": 2, "مارس": 3, "آوریل": 4, "مه": 5, "می": 5, "ژوئن": 6, "ژوئیه": 7,
    "جولای": 7, "اوت": 8, "آگوست": 8, "سپتامبر": 9, "اکتبر": 10, "نوامبر": 11, "دسامبر": 12,
}  # fmt: skip
ORDINALS_FA = {
    "یکم": 1, "اول": 1, "دوم": 2, "سوم": 3, "چهارم": 4, "پنجم": 5, "ششم": 6, "هفتم": 7,
    "هشتم": 8, "نهم": 9, "دهم": 10, "یازدهم": 11, "دوازدهم": 12, "سیزدهم": 13,
    "چهاردهم": 14, "پانزدهم": 15, "شانزدهم": 16, "هفدهم": 17, "هجدهم": 18, "نوزدهم": 19,
    "بیستم": 20, f"سی{Z}ام": 30, "سیم": 30,
}  # fmt: skip
PARTS_FA: dict[str, Part] = {
    "صبح": "morning",
    "ظهر": "noon",
    "بعدازظهر": "afternoon",
    "عصر": "evening",
    "شب": "night",
    f"نیمه{Z}شب": "midnight",
}
PARTS_EN: dict[str, Part] = {
    "morning": "morning",
    "noon": "noon",
    "midday": "noon",
    "afternoon": "afternoon",
    "evening": "evening",
    "night": "night",
    "midnight": "midnight",
}
UNIT_MINUTES = {
    "دقیقه": 1, "ساعت": 60, "روز": 1440, "هفته": 10080,
    "minute": 1, "minutes": 1, "min": 1, "mins": 1, "hour": 60, "hours": 60, "hr": 60, "hrs": 60,
    "day": 1440, "days": 1440, "week": 10080, "weeks": 10080,
}  # fmt: skip


def _alt(words) -> str:
    """Regex alternation, longest first so `سه‌شنبه` wins over `شنبه`."""
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


WD_FA = _alt(WEEKDAYS_FA)
WD_EN = _alt(WEEKDAYS_EN)
PART_FA = _alt(PARTS_FA)
PART_EN = _alt(PARTS_EN)
ORD_FA = _alt(ORDINALS_FA)
DAY_FA = rf"(?:\d{{1,2}}(?:\s*و\s*(?:{ORD_FA}))?|{ORD_FA})"

AMOUNT_FA = (
    r"(?P<amt>\d+\s*(?:دقیقه|ساعت|روز|هفته)(?:\s*و\s*نیم)?"
    r"|نیم\s*ساعت|(?:1\s*)?ربع(?:\s*ساعت)?)"
)
AMOUNT_EN = (
    r"(?P<amt>(?:\d+|an?)\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?)(?:\s+and\s+a\s+half)?"
    r"|half\s+an?\s+hour|(?:a\s+)?quarter\s+of\s+an\s+hour)"
)


def amount_minutes(text: str) -> int:
    """`2 ساعت و نیم` → 150, `half an hour` → 30, `1 ربع` → 15."""
    if "نیم ساعت" in text or ("half" in text and "and a half" not in text):
        return 30
    if "ربع" in text or "quarter" in text:
        return 15
    number = re.search(r"\d+", text)
    count = int(number.group()) if number else 1
    unit = next(u for u in sorted(UNIT_MINUTES, key=len, reverse=True) if u in text)
    minutes = count * UNIT_MINUTES[unit]
    if "و نیم" in text or "and a half" in text:
        minutes += UNIT_MINUTES[unit] // 2
    return minutes


def _day_value(text: str) -> int:
    """`15`, `پنجم` or `20 و یکم` → day of month."""
    total = 0
    for piece in re.split(r"\s*و\s*", text.strip()):
        total += int(piece) if piece.isdigit() else ORDINALS_FA.get(piece, 0)
    return total


# --- Date helpers ---


def next_jalali(month: int, day: int, today: date, year: int | None = None) -> date | None:
    try:
        if year:
            return jdatetime.date(year, month, day).togregorian()
        jy = jdatetime.date.fromgregorian(date=today).year
        candidate = jdatetime.date(jy, month, day).togregorian()
        return candidate if candidate >= today else jdatetime.date(jy + 1, month, day).togregorian()
    except ValueError:
        return None


def next_gregorian(month: int, day: int, today: date, year: int | None = None) -> date | None:
    try:
        if year:
            return date(year, month, day)
        candidate = date(today.year, month, day)
        return candidate if candidate >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def next_weekday(weekday: int, today: date, next_week: bool = False) -> date:
    ahead = (weekday - today.weekday()) % 7
    if ahead == 0 and next_week:
        ahead = 7
    return today + timedelta(days=ahead)


# --- Atom finders (applied in priority order; matched text is masked) ---

_MASK = "\x00"


def _part(word: str) -> Part:
    return PARTS_FA.get(word) or PARTS_EN[word.lower()]


def _build_patterns(today: date):
    """List of (compiled regex, builder(match) -> Atom | None)."""

    def repeat(kind, **kw):
        return lambda m: Atom(m.start(), m.end(), "repeat", repeat=RepeatRule(kind, **kw))

    def repeat_part(kind):
        return lambda m: Atom(
            m.start(), m.end(), "repeat", repeat=RepeatRule(kind), part=_part(m["part"])
        )

    def repeat_weekday(table):
        return lambda m: Atom(
            m.start(),
            m.end(),
            "repeat",
            repeat=RepeatRule("weekly", weekday=table[m["wd"].lower()]),
        )

    def repeat_monthly(m):
        day = int(m["day"]) if m.groupdict().get("day") else None
        return Atom(m.start(), m.end(), "repeat", repeat=RepeatRule("monthly", day=day))

    def before(m):
        return Atom(m.start(), m.end(), "before", minutes_before=amount_minutes(m["amt"]))

    def day_before(m):
        word = m["part"]
        if word in ("روز", "day"):
            return Atom(m.start(), m.end(), "before", minutes_before=1440)
        return Atom(m.start(), m.end(), "day_before", part=_part(word))

    def relative(m):
        return Atom(
            m.start(), m.end(), "relative", delta=timedelta(minutes=amount_minutes(m["amt"]))
        )

    def numeric_date(m):
        y, mo, d = int(m["y"]), int(m["m"]), int(m["d"])
        finder = next_jalali if y < 1700 else next_gregorian
        found = finder(mo, d, today, y)
        return Atom(m.start(), m.end(), "date", date=found) if found else None

    def month_date(table, finder, day_parser=int):
        def build(m):
            year = int(m["year"]) if m.groupdict().get("year") else None
            found = finder(table[m["month"].lower()], day_parser(m["day"]), today, year)
            return Atom(m.start(), m.end(), "date", date=found) if found else None

        return build

    def relative_day(days, part=None):
        return lambda m: Atom(
            m.start(), m.end(), "date", date=today + timedelta(days=days), part=part
        )

    def weekday(table):
        return lambda m: Atom(
            m.start(),
            m.end(),
            "weekday",
            weekday=table[m["wd"].lower()],
            next_week=bool(m.groupdict().get("next")),
        )

    def clock(quarter_to=False, fixed_minute=None):
        def build(m):
            g = m.groupdict()
            hour = int(g["h"])
            minute = int(g["m"]) if g.get("m") else 0
            meridiem = None
            if g.get("ap"):
                meridiem = "am" if g["ap"].startswith("a") else "pm"
            elif hour >= 13 or hour == 0 or (g.get("m") and g["h"].startswith("0")):
                meridiem = "24h"  # 14:00, 0:30 and zero-padded 08:00 are unambiguous
            if g.get("half"):
                minute = 30
            elif g.get("quarter"):
                minute = 15
            elif g.get("mm"):
                minute = int(g["mm"])
            if fixed_minute is not None:
                minute = fixed_minute
            if quarter_to:
                hour, minute = (hour - 1) % 12 or 12, 45
            part = _part(g["part"]) if g.get("part") else None
            if hour > 23 or minute > 59:
                return None
            return Atom(
                m.start(), m.end(), "time", hour=hour, minute=minute, meridiem=meridiem, part=part
            )

        return build

    def fixed_time(m):
        part = _part(m["word"])
        hour = 12 if part == "noon" else 0
        return Atom(m.start(), m.end(), "time", hour=hour, meridiem="24h", part=part)

    def part_atom(m):
        return Atom(m.start(), m.end(), "part", part=_part(m["part"]))

    jfa, jen = _alt(JALALI_MONTHS_FA), _alt(JALALI_MONTHS_EN)
    gfa, gen = _alt(GREGORIAN_MONTHS_FA), _alt(GREGORIAN_MONTHS_EN)
    suffix_en = r"(?:st|nd|rd|th)?"
    patterns = [
        # Repeats
        (rf"{B}هر\s*روز\s*(?P<part>{PART_FA}){E}", repeat_part("daily")),
        (rf"{B}(?:هر\s*روز|روزانه){E}", repeat("daily")),
        (rf"{B}هر\s*(?P<part>صبح|ظهر|عصر|شب){E}", repeat_part("daily")),
        (rf"{B}هر\s*(?P<wd>{WD_FA}){E}", repeat_weekday(WEEKDAYS_FA)),
        (rf"{B}(?:هر\s*هفته|هفتگی){E}", repeat("weekly")),
        (rf"{B}هر\s*ماه\s*(?P<day>\d{{1,2}})\s*(?:ام|م){E}", repeat_monthly),
        (rf"{B}(?P<day>\d{{1,2}})\s*(?:ام|م)?\s*هر\s*ماه{E}", repeat_monthly),
        (rf"{B}(?:هر\s*ماه|ماهانه){E}", repeat_monthly),
        (rf"{B}every\s+(?P<part>morning|afternoon|evening|night){E}", repeat_part("daily")),
        (rf"{B}(?:every\s*day|everyday|daily|each\s+day){E}", repeat("daily")),
        (rf"{B}every\s+(?P<wd>{WD_EN})s?{E}", repeat_weekday(WEEKDAYS_EN)),
        (rf"{B}(?:every\s+week|weekly){E}", repeat("weekly")),
        (
            rf"{B}every\s+month\s+on\s+the\s+(?P<day>\d{{1,2}}){suffix_en}{E}"
            rf"|{B}on\s+the\s+(?P<day2>\d{{1,2}}){suffix_en}\s+of\s+every\s+month{E}",
            lambda m: repeat_monthly_en(m),
        ),
        (rf"{B}(?:every\s+month|monthly){E}", repeat_monthly),
        # Relative to the event
        (rf"{B}{AMOUNT_FA}\s*(?:قبل|پیش|زودتر)ش?{E}", before),
        (rf"{B}{AMOUNT_EN}\s+(?:before|earlier|ahead)(?:\s+of\s+(?:it|time))?{E}", before),
        (rf"{B}(?P<part>{PART_FA}|روز)\s*قبلش?{E}", day_before),
        (rf"{B}the\s+(?P<part>morning|afternoon|evening|night|day)\s+before{E}", day_before),
        # Relative to now
        (rf"{B}{AMOUNT_FA}\s*(?:دیگه|دیگر|بعد)(?!\s*از){E}", relative),
        (rf"{B}in\s+{AMOUNT_EN}{E}", relative),
        (rf"{B}{AMOUNT_EN}\s+from\s+now{E}", relative),
        # Absolute dates
        (rf"{B}(?P<y>\d{{4}})[/\-.](?P<m>\d{{1,2}})[/\-.](?P<d>\d{{1,2}}){E}", numeric_date),
        (
            rf"{B}(?P<day>{DAY_FA})\s*(?:ام|م)?\s*(?P<month>{jfa})(?:\s*ماه)?"
            rf"(?:\s*(?:سال\s*)?(?P<year>1[34]\d\d))?{E}",
            month_date(JALALI_MONTHS_FA, next_jalali, _day_value),
        ),
        (
            rf"{B}(?P<day>\d{{1,2}})\s*(?:ام|م)?\s*(?P<month>{gfa})(?:\s*(?P<year>20\d\d))?{E}",
            month_date(GREGORIAN_MONTHS_FA, next_gregorian),
        ),
        (
            rf"{B}(?P<day>\d{{1,2}}){suffix_en}\s*(?:of\s+)?(?P<month>{jen})(?:\s+(?P<year>1[34]\d\d))?{E}",
            month_date(JALALI_MONTHS_EN, next_jalali),
        ),
        (
            rf"{B}(?P<month>{jen})\s+(?P<day>\d{{1,2}}){suffix_en}(?:,?\s+(?P<year>1[34]\d\d))?{E}",
            month_date(JALALI_MONTHS_EN, next_jalali),
        ),
        (
            rf"{B}(?P<day>\d{{1,2}}){suffix_en}\s*(?:of\s+)?(?P<month>{gen})(?:,?\s+(?P<year>20\d\d))?{E}",
            month_date(GREGORIAN_MONTHS_EN, next_gregorian),
        ),
        (
            rf"{B}(?P<month>{gen})\s+(?P<day>\d{{1,2}}){suffix_en}(?:,?\s+(?P<year>20\d\d))?{E}",
            month_date(GREGORIAN_MONTHS_EN, next_gregorian),
        ),
        # Relative days
        (rf"{B}پس{Z}فردا{E}|{B}(?:the\s+)?day\s+after\s+tomorrow{E}", relative_day(2)),
        (rf"{B}فردا{Z}شب{E}", relative_day(1, "night")),
        (rf"{B}(?:فردا|tomorrow){E}", relative_day(1)),
        (rf"{B}(?:امشب|tonight){E}", relative_day(0, "night")),
        (rf"{B}(?:امروز|today){E}", relative_day(0)),
        # Weekdays
        (
            rf"{B}(?:این\s*)?(?P<wd>{WD_FA})(?:\s*(?P<next>آینده|بعد|دیگه|ی\s*بعد|ی\s*آینده))?{E}",
            weekday(WEEKDAYS_FA),
        ),
        (rf"{B}(?:(?P<next>next)\s+|this\s+|on\s+)?(?P<wd>{WD_EN}){E}", weekday(WEEKDAYS_EN)),
        # Times
        (rf"{B}(?:ساعت\s*)?(?:1\s*)?ربع\s*به\s*(?P<h>\d{{1,2}}){E}", clock(quarter_to=True)),
        (
            rf"{B}ساعت\s*(?P<h>\d{{1,2}})(?::(?P<m>\d{{2}}))?"
            rf"(?:\s*و\s*(?:(?P<half>نیم)|(?P<quarter>ربع)|(?P<mm>\d{{1,2}})\s*دقیقه))?"
            rf"(?:\s*(?P<part>{PART_FA}))?{E}",
            clock(),
        ),
        (
            rf"{B}(?P<h>\d{{1,2}})\s*و\s*(?:(?P<half>نیم)|(?P<quarter>ربع))"
            rf"(?:\s*(?P<part>{PART_FA}))?{E}",
            clock(),
        ),
        (
            rf"{B}(?:at\s+)?(?P<h>\d{{1,2}})(?::(?P<m>\d{{2}}))?\s*(?P<ap>am|pm|a\.m\.|p\.m\.)(?!\w)",
            clock(),
        ),
        (rf"{B}(?:at\s+)?half\s+past\s+(?P<h>\d{{1,2}}){E}", clock(fixed_minute=30)),
        (rf"{B}(?:at\s+)?(?:a\s+)?quarter\s+past\s+(?P<h>\d{{1,2}}){E}", clock(fixed_minute=15)),
        (rf"{B}(?:at\s+)?(?:a\s+)?quarter\s+to\s+(?P<h>\d{{1,2}}){E}", clock(quarter_to=True)),
        (
            rf"{B}(?:at\s+)?(?P<h>\d{{1,2}})(?::(?P<m>\d{{2}}))?\s+in\s+the\s+"
            rf"(?P<part>morning|afternoon|evening){E}"
            rf"|{B}(?:at\s+)?(?P<h2>\d{{1,2}})(?::(?P<m2>\d{{2}}))?\s+at\s+(?P<part2>night){E}",
            lambda m: clock_en_part(m),
        ),
        (
            rf"(?<![\d/:])(?:at\s+)?(?P<h>\d{{1,2}}):(?P<m>\d{{2}})(?![\d/:])"
            rf"(?:\s*(?P<part>{PART_FA}))?",
            clock(),
        ),
        (rf"{B}at\s+(?P<h>\d{{1,2}})(?:\s*o'?clock)?{E}", clock()),
        (rf"{B}(?P<h>\d{{1,2}})\s*o'?clock{E}", clock()),
        (rf"{B}(?P<h>\d{{1,2}})\s*(?P<part>{PART_FA})ش?{E}", clock()),
        (rf"{B}(?:at\s+)?(?P<word>noon|midday|midnight){E}", fixed_time),
        # Parts of day
        (rf"{B}(?P<part>{PART_FA})ش?{E}", part_atom),
        (
            rf"{B}(?:in\s+the\s+|at\s+|this\s+)?(?P<part>morning|afternoon|evening|night){E}",
            part_atom,
        ),
    ]

    def repeat_monthly_en(m):
        day = int(m["day"] or m["day2"])
        return Atom(m.start(), m.end(), "repeat", repeat=RepeatRule("monthly", day=day))

    def clock_en_part(m):
        h, mm, part = (m["h"], m["m"], m["part"]) if m["h"] else (m["h2"], m["m2"], m["part2"])
        hour, minute = int(h), int(mm) if mm else 0
        if hour > 23 or minute > 59:
            return None
        return Atom(m.start(), m.end(), "time", hour=hour, minute=minute, part=_part(part))

    return [(re.compile(p, re.IGNORECASE), build) for p, build in patterns]


def find_atoms(text: str, today: date) -> list[Atom]:
    """All date/time atoms in `text` (normalized), ordered by position."""
    atoms: list[Atom] = []
    masked = text
    for pattern, build in _build_patterns(today):
        for match in pattern.finditer(masked):
            atom = build(match)
            if atom is None:
                continue
            atoms.append(atom)
            masked = masked[: atom.start] + _MASK * (atom.end - atom.start) + masked[atom.end :]
    return sorted(atoms, key=lambda a: a.start)


# --- Resolution ---


def resolve_hour(
    hour: int, minute: int, meridiem: str | None, part: Part | None
) -> tuple[time, bool]:
    """Apply am/pm or a part of day to an hour. Returns (time, ambiguous)."""
    if meridiem == "am":
        return time(0 if hour == 12 else hour, minute), False
    if meridiem == "pm":
        return time(hour if hour == 12 else (hour + 12) % 24, minute), False
    if meridiem == "24h":
        return time(hour, minute), False
    if part == "morning":
        return time(hour % 12, minute), False
    if part == "noon":
        return time(hour if hour >= 11 else (hour + 12) % 24, minute), False
    if part in ("afternoon", "evening"):
        return time(hour if hour >= 12 else hour + 12, minute), False
    if part == "night":
        if hour == 12:
            return time(0, minute), False
        return time(hour + 12 if 6 <= hour <= 11 else hour, minute), False
    if part == "midnight":
        return time(0, minute), False
    return time(hour % 12, minute), True


def resolve(atoms: list[Atom], today: date, day_times: DayTimes) -> Moment:
    """Merge a group of atoms (e.g. `فردا` + `ساعت ۲` + `بعدازظهر`) into one Moment."""
    moment = Moment()
    part: Part | None = None
    clock: Atom | None = None
    day_before_part: Part | None = None
    for atom in atoms:
        if atom.kind == "date":
            moment.date = atom.date
            part = atom.part or part
        elif atom.kind == "weekday":
            moment.date = next_weekday(atom.weekday, today, atom.next_week)  # type: ignore[arg-type]
            moment.flexible_week = moment.date == today
        elif atom.kind == "time":
            clock = atom
            part = atom.part or part
        elif atom.kind == "part":
            part = atom.part
        elif atom.kind == "relative":
            moment.delta = atom.delta
        elif atom.kind == "before":
            moment.minutes_before = atom.minutes_before
        elif atom.kind == "day_before":
            day_before_part = atom.part
        elif atom.kind == "repeat":
            moment.repeat = atom.repeat
            part = atom.part or part
            if atom.repeat and atom.repeat.kind == "weekly" and atom.repeat.weekday is not None:
                moment.date = next_weekday(atom.repeat.weekday, today)
                moment.flexible_week = moment.date == today

    if day_before_part:
        if clock:
            moment.day_before, _ = resolve_hour(
                clock.hour,
                clock.minute,
                clock.meridiem,
                day_before_part,  # type: ignore[arg-type]
            )
        else:
            moment.day_before = day_times.of(day_before_part)
        return moment

    if clock:
        moment.time, moment.ambiguous = resolve_hour(
            clock.hour,
            clock.minute,
            clock.meridiem,
            part,  # type: ignore[arg-type]
        )
    elif part:
        moment.time = day_times.of(part)
    return moment


def with_time(moment: Moment, value: time) -> Moment:
    return replace(moment, time=value, ambiguous=False)
