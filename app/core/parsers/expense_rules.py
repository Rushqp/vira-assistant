"""Expense sentences → items (amount, quantity, description) and report requests.

«۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن»
→ [3,000,000 "خرید خونه"], [100 (thousand or million?) "بنزین", 10 L]

Splitting: the text is cut at , ، ; and new lines. A piece without an amount is joined to the
next one («نون و پنیر، ۵۰ هزار»); a piece with several amounts is cut at «و» / "and" between
them («نون ۵۰ هزار و شیر ۳۰ هزار»).
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise
from typing import Literal

from app.core.normalizer import ZWNJ, normalize
from app.core.parsers.amount_parser import (
    CURRENCY_WORD,
    Amount,
    Quantity,
    find_amounts,
    find_quantities,
    mask,
)
from app.core.parsers.datetime_parser import B, E, find_atoms

# Words that say money was spent.
SPEND = re.compile(
    r"\b(?:paid|pay|spent|spend|bought|buy|cost|costs|purchased|expense)\b"
    rf"|{B}(?:دادم|دادیم|خریدم|خریدیم|خرید|گرفتم|پرداخت(?:\s*کردم)?|پرداختم|هزینه|خرج|"
    rf"شد|زدم|ریختم|حساب\s*کردم|کارت\s*کشیدم){E}",
    re.IGNORECASE,
)
# Questions mention money too («۳ میلیون چند دلاره؟») but are not expenses.
QUESTION = re.compile(
    rf"[?؟]|\bhow\s+much\b|\bprice\s+of\b|{B}(?:چند|چنده|چقدر|چقد|قیمت){E}", re.IGNORECASE
)
_PIECE_BREAK = re.compile(r"[,،;؛\n]")
_JOIN = re.compile(r"\s(?:و|and|also|plus)\s", re.IGNORECASE)
_FILLER = re.compile(
    r"\b(?:i|we|paid|pay|spent|spend|bought|buy|cost|costs|purchased|for|on|of|the|a|an|and|"
    r"also|plus|was|were|it|total)\b"
    rf"|{B}(?:دادم|دادیم|خریدم|خریدیم|گرفتم|پرداخت\s*کردم|پرداخت|پرداختم|هزینه|خرج|کردم|شد|"
    rf"زدم|ریختم|حساب\s*کردم|کارت\s*کشیدم|بابت|برای|واسه|هم|پول|که|رو|را|من|امروز|دیروز){E}",
    re.IGNORECASE,
)


@dataclass
class ExpenseItem:
    amount: float | None  # None: not found (ask the user)
    ambiguous: bool  # below 1000 without scale → thousand or million?
    currency: str | None  # explicit "toman" / "rial", if written
    description: str
    quantity: float | None = None
    unit: str | None = None


@dataclass
class ExpenseParse:
    items: list[ExpenseItem] = field(default_factory=list)
    spent_on: date | None = None  # None = today


def _spent_on(text: str, today: date) -> tuple[date | None, list[tuple[int, int]]]:
    """Date mentioned in the text (moved to the past: «شنبه» = last Saturday) + its spans.

    Only day words count: times are ignored so «۲ و نیم میلیون» stays an amount.
    """
    atoms = [a for a in find_atoms(text, today) if a.kind in ("date", "weekday")]
    spans = [(a.start, a.end) for a in atoms]
    day: date | None = None
    for atom in atoms:
        if atom.kind == "weekday" and atom.weekday is not None:
            day = today - timedelta(days=(today.weekday() - atom.weekday) % 7)
        elif atom.kind == "date" and atom.date is not None:
            day = atom.date
            if day > today:  # «۱۵ مهر» next year → this year's
                try:
                    day = day.replace(year=day.year - 1)
                except ValueError:
                    day = day - timedelta(days=365)
    if text and re.search(rf"{B}دیروز{E}|\byesterday\b", text, re.IGNORECASE):
        day = today - timedelta(days=1)
    if day is not None and day > today:
        day = today
    return day, spans


SHORT_MESSAGE_WORDS = 12


def has_expense_intent(raw: str) -> bool:
    """Not a question, has an amount, and either a spending / currency word, or it is a short
    message with an amount of at least 1000 («نون ۵۰ هزار»)."""
    text = normalize(raw, lowercase=False)
    if QUESTION.search(text):
        return False
    _, spans = _spent_on(text, date.today())
    masked = mask(text, spans)
    quantity_spans = [(q.start, q.end) for q in find_quantities(masked)]
    amounts = find_amounts(mask(masked, quantity_spans))
    if not amounts:
        return False
    if SPEND.search(text) or CURRENCY_WORD.search(text):
        return True
    has_words = re.search(r"[^\W\d_]{2,}", text) is not None
    short = len(text.split()) <= SHORT_MESSAGE_WORDS
    return short and has_words and all(a.value >= 1000 for a in amounts)


def _pieces(text: str, amounts: list[Amount]) -> list[tuple[int, int]]:
    """Cut the text into (start, end) pieces with one amount each where possible."""
    bounds = [0] + [m.end() for m in _PIECE_BREAK.finditer(text)] + [len(text) + 1]
    raw = [(bounds[i], bounds[i + 1] - 1) for i in range(len(bounds) - 1)]
    raw = [(s, min(e, len(text))) for s, e in raw]

    def count(span):
        return sum(1 for a in amounts if span[0] <= a.start < span[1])

    # Join pieces without an amount to the next one (or the previous, at the end).
    merged: list[tuple[int, int]] = []
    pending: int | None = None
    for span in raw:
        start = pending if pending is not None else span[0]
        if count((start, span[1])) == 0:
            pending = start
            continue
        merged.append((start, span[1]))
        pending = None
    if pending is not None:
        if merged:
            merged[-1] = (merged[-1][0], len(text))
        else:
            merged.append((pending, len(text)))

    # Split pieces with several amounts at «و» / "and" between them (or right after an amount).
    result: list[tuple[int, int]] = []
    for start, end in merged:
        inside = [a for a in amounts if start <= a.start < end]
        cut_from = start
        for left, right in pairwise(inside):
            join = _JOIN.search(text, left.end, right.start)
            cut = join.start() if join else left.end
            result.append((cut_from, cut))
            cut_from = cut
        result.append((cut_from, end))
    return result


def _describe(text: str) -> str:
    text = _FILLER.sub(" ", text)
    text = re.sub(rf"[\x00,،;؛.!:\-–]+|{ZWNJ}(?=\s)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # «و» joins words inside a description («نون و پنیر») but not at its edges.
    return re.sub(r"^(?:و|and)\s+|\s+(?:و|and)$", "", text, flags=re.IGNORECASE)


def parse_expenses(raw: str, today: date) -> ExpenseParse:
    text = normalize(raw, lowercase=False)
    spent_on, date_spans = _spent_on(text, today)
    masked = mask(text, date_spans)
    quantities = find_quantities(masked)
    masked = mask(masked, [(q.start, q.end) for q in quantities])
    amounts = find_amounts(masked)
    # Prefer explicit amounts: drop bare numbers in pieces that already have one.
    items: list[ExpenseItem] = []
    for start, end in _pieces(masked, amounts):
        inside = [a for a in amounts if start <= a.start < end]
        explicit = [a for a in inside if not a.bare]
        amount = (explicit or inside or [None])[0]
        qty: Quantity | None = next((q for q in quantities if start <= q.start < end), None)
        piece = mask(masked, [(amount.start, amount.end)]) if amount else masked
        description = CURRENCY_WORD.sub(" ", piece[start:end])
        description = _describe(description)
        if amount is None and not description:
            continue
        items.append(
            ExpenseItem(
                amount=amount.value if amount else None,
                ambiguous=amount.ambiguous if amount else False,
                currency=amount.currency if amount else None,
                description=description,
                quantity=qty.value if qty else None,
                unit=qty.unit if qty else None,
            )
        )
    return ExpenseParse(items=items, spent_on=spent_on)


# --- Report requests ---

Period = Literal["today", "yesterday", "week", "last_week", "month", "last_month"]

_REPORT_WORD = re.compile(
    rf"\breport\b|\bsummary\b|\bhow\s+much\s+(?:did|have)\s+i\s+spen[dt]\b|\bmy\s+expenses\b"
    rf"|{B}(?:گزارش|خلاصه\s*خرج|چقدر\s*خرج\s*کردم|چقد\s*خرج\s*کردم|هزینه\s*هام|خرج\s*هام|"
    rf"خرجام|هزینه\s*های\s*من){E}",
    re.IGNORECASE,
)
_BEFORE_FA = r"\s*(?:قبل|پیش|گذشته)"
_PERIODS: list[tuple[re.Pattern, Period]] = [
    (re.compile(rf"\b(?:last|previous)\s+month\b|{B}ماه{_BEFORE_FA}{E}", re.I), "last_month"),
    (re.compile(rf"\b(?:last|previous)\s+week\b|{B}هفته{_BEFORE_FA}{E}", re.I), "last_week"),
    (re.compile(rf"\byesterday\b|{B}دیروز{E}", re.I), "yesterday"),
    (re.compile(rf"\bweek\b|{B}هفته{E}", re.I), "week"),
    (re.compile(rf"\bmonth\b|\bmonthly\b|{B}ماه{E}|{B}ماهانه{E}", re.I), "month"),
    (re.compile(rf"\btoday\b|{B}امروز{E}", re.I), "today"),
]  # fmt: skip


def parse_period(raw: str) -> Period | None:
    """The period named in a message («ماه قبل», "this week"), if any."""
    text = normalize(raw, lowercase=False)
    return next((period for pattern, period in _PERIODS if pattern.search(text)), None)


def parse_report_request(raw: str) -> Period | None:
    """«گزارش این ماه» → "month", "how much did I spend last week" → "last_week"."""
    if not _REPORT_WORD.search(normalize(raw, lowercase=False)):
        return None
    return parse_period(raw) or "today"


# --- Excel requests (when no model is available) ---

_EXPORT_WORD = re.compile(rf"\b(?:excel|xlsx|spreadsheet|export)\b|{B}اکسل", re.IGNORECASE)


def has_export_intent(raw: str) -> bool:
    """«اکسل هزینه‌های این ماه», "export to Excel"."""
    return bool(_EXPORT_WORD.search(normalize(raw, lowercase=False)))
