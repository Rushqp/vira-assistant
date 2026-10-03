"""Amounts, quantities, expense sentences and report requests (Persian + English)."""

from datetime import date

import pytest

from app.core.normalizer import normalize
from app.core.parsers.amount_parser import find_amounts, find_quantities, to_currency
from app.core.parsers.expense_rules import (
    has_expense_intent,
    parse_expenses,
    parse_report_request,
)

TODAY = date(2026, 10, 4)  # Sunday


# --- Number words in prices ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("دو میلیون و پونصد", "2500000"),  # colloquial: 2.5 million
        ("2 میلیون و 500", "2500000"),
        ("سه هزار و پانصد", "3500"),  # literal under a thousand-scale
        ("یک میلیون و دویست هزار", "1200000"),
        ("5 میلیون و 300 هزار", "5300000"),
        ("2.5 میلیون", "2.5 میلیون"),  # left for the amount parser
        ("میلیون ها نفر", "میلیون ها نفر"),
    ],
)
def test_price_number_words(text, expected):
    assert normalize(text) == expected


# --- Amount parser ---


def amounts(text: str):
    return [(a.value, a.ambiguous, a.currency) for a in find_amounts(normalize(text))]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("۳ میلیون", [(3_000_000, False, None)]),
        ("۱۰۰ هزار تومن", [(100_000, False, "toman")]),
        ("2.5 میلیون تومان", [(2_500_000, False, "toman")]),
        ("دو و نیم میلیون", [(2_500_000, False, None)]),
        ("100k", [(100_000, False, None)]),
        ("1.2m", [(1_200_000, False, None)]),
        ("450,000 تومن", [(450_000, False, "toman")]),
        ("۳ تومن", [(3, True, "toman")]),
        ("۱۵۰", [(150, True, None)]),
        ("50000 ریال", [(50_000, False, "rial")]),
    ],
)
def test_find_amounts(text, expected):
    assert amounts(text) == expected


def test_quantities():
    found = find_quantities(normalize("۱۰ لیتر بنزین و ۲ کیلو برنج و ۳ تا نون"))
    assert [(q.value, q.unit) for q in found] == [(10, "L"), (2, "kg"), (3, "pcs")]


def test_currency_conversion():
    assert to_currency(50_000, "rial", "toman") == 5_000
    assert to_currency(5_000, "toman", "rial") == 50_000
    assert to_currency(5_000, None, "toman") == 5_000


# --- Expense sentences ---


def items(text: str):
    return [
        (i.amount, i.ambiguous, i.description, i.quantity, i.unit)
        for i in parse_expenses(text, TODAY).items
    ]


def test_roadmap_example_fa():
    assert items("۳ میلیون خرید خونه دادم، ۱۰ لیتر بنزین هم ۱۰۰ تومن") == [
        (3_000_000, False, "خرید خونه", None, None),
        (100, True, "بنزین", 10, "L"),
    ]


def test_roadmap_example_en():
    assert items("Paid 3 million toman for groceries, and 10 liters of fuel cost 100 thousand") == [
        (3_000_000, False, "groceries", None, None),
        (100_000, False, "fuel", 10, "L"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("نون و پنیر ۵۰ هزار", [(50_000, False, "نون و پنیر", None, None)]),
        (
            "نون ۵۰ هزار و شیر ۳۰ هزار",
            [(50_000, False, "نون", None, None), (30_000, False, "شیر", None, None)],
        ),
        ("قبض برق 450,000 تومن", [(450_000, False, "قبض برق", None, None)]),
        ("ناهار رستوران ۸۵۰ تومن شد", [(850, True, "ناهار رستوران", None, None)]),
        ("spent 1.2m on a jacket", [(1_200_000, False, "jacket", None, None)]),
        ("۵ تا نون ۴۰ هزار", [(40_000, False, "نون", 5, "pcs")]),
        ("کتاب", [(None, False, "کتاب", None, None)]),
    ],
)
def test_expense_items(text, expected):
    assert items(text) == expected


def test_dates_are_in_the_past():
    assert parse_expenses("دیروز ۲ و نیم میلیون برای دکتر دادم", TODAY).spent_on == date(
        2026, 10, 3
    )
    assert parse_expenses("شنبه ۲۰۰ هزار تاکسی دادم", TODAY).spent_on == date(2026, 10, 3)
    assert parse_expenses("۱ مهر ۵۰ هزار نون", TODAY).spent_on == date(2026, 9, 23)
    assert parse_expenses("۵۰ هزار نون", TODAY).spent_on is None


@pytest.mark.parametrize(
    "text",
    [
        "۳ میلیون خرید خونه دادم",
        "نون ۵۰ هزار",
        "قبض برق 450,000 تومن",
        "paid 20 toman for coffee",
        "lunch 450k",
    ],
)
def test_expense_intent(text):
    assert has_expense_intent(text)


@pytest.mark.parametrize(
    "text",
    [
        "۳ میلیون تومن چند دلاره؟",
        "how much is 100 toman in rial",
        "سلام خوبی",
        "کتاب ۱۵۰",  # small number, no currency / verb: could be anything
        "I walked 5000 steps today and felt great about the whole thing honestly",
    ],
)
def test_not_expense(text):
    assert not has_expense_intent(text)


# --- Report requests ---


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("گزارش", "today"),
        ("گزارش امروز", "today"),
        ("گزارش دیروز", "yesterday"),
        ("گزارش این هفته", "week"),
        ("گزارش هفته قبل", "last_week"),
        ("گزارش این ماه", "month"),
        ("گزارش ماه گذشته", "last_month"),
        ("چقدر خرج کردم این ماه", "month"),
        ("report", "today"),
        ("how much did I spend last week", "last_week"),
        ("monthly report", "month"),
    ],
)
def test_report_requests(text, period):
    assert parse_report_request(text) == period


@pytest.mark.parametrize("text", ["سلام", "what's the weather", "۳ میلیون خرید خونه دادم"])
def test_not_report_requests(text):
    assert parse_report_request(text) is None
