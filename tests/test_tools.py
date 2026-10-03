from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import Calendar
from app.services.tools import (
    CalcError,
    answer_builtin,
    calculate,
    format_number,
    is_date_question,
    looks_like_math,
)

NOW = datetime(2026, 10, 3, 19, 36, tzinfo=ZoneInfo("Asia/Tehran"))


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("2+2", 4),
        ("12 * 350000", 4_200_000),
        ("۱۲ × ۳", 36),
        ("(3 + 4) * 2 =", 14),
        ("10 / 4", 2.5),
        ("2^10", 1024),
        ("-5 + 3", -2),
        ("1,500,000 + 250,000", 1_750_000),
        ("۷٫۵ * ۲", 15),
        ("100 ÷ 8", 12.5),
        ("17 % 5", 2),
    ],
)
def test_calculate(expr, expected):
    assert looks_like_math(expr)
    assert calculate(expr) == expected


@pytest.mark.parametrize("expr", ["1/0", "2**1000", "9**9**9", "2 +", "10 ** 30"])
def test_calculate_rejects_bad_input(expr):
    with pytest.raises(CalcError):
        calculate(expr)


@pytest.mark.parametrize(
    "text", ["2026", "hello", "what is 2+2 in binary", "__import__('os')", "-5", "۱۴۰۵", ""]
)
def test_not_math(text):
    assert not looks_like_math(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4_200_000, "4,200,000"),
        (0.1 + 0.2, "0.3"),
        (2.5, "2.5"),
        (-3.0, "-3"),
        (1 / 3, "0.3333333333"),
    ],
)
def test_format_number(value, expected):
    assert format_number(value) == expected


@pytest.mark.parametrize(
    "text",
    [
        "what's the date?",
        "What is the date today?",
        "what day is it",
        "today's date",
        "Date?",
        "امروز چندمه؟",
        "امروز چه روزیه",
        "امروز چندشنبه است؟",
        "تاریخ امروز",
    ],
)
def test_date_questions(text):
    assert is_date_question(text)


@pytest.mark.parametrize(
    "text", ["what's the date of nowruz?", "tell me about dates", "امروز هوا چطوره؟", "update"]
)
def test_not_date_questions(text):
    assert not is_date_question(text)


def test_date_answer_english_jalali_first():
    answer = answer_builtin("what's the date?", NOW, Calendar.JALALI)
    assert answer is not None
    assert "Sat 11 Mehr 1405" in answer
    assert "3 Oct 2026" in answer
    assert "19:36" in answer


def test_date_answer_persian_gregorian_first():
    answer = answer_builtin("امروز چندمه؟", NOW, Calendar.GREGORIAN)
    assert answer is not None
    assert answer.index("۳ اکتبر ۲۰۲۶") < answer.index("۱۱ مهر ۱۴۰۵")
    assert "شنبه" in answer
    assert "۱۹:۳۶" in answer


def test_calculator_answer():
    assert answer_builtin("12*350000", NOW, Calendar.JALALI) == (
        "🧮 <code>12*350000</code> = <b>4,200,000</b>"
    )
    assert "division by zero" in (answer_builtin("5/0", NOW, Calendar.JALALI) or "")


def test_other_text_goes_to_llm():
    assert answer_builtin("How do I cook rice?", NOW, Calendar.JALALI) is None
    assert answer_builtin("سلام، خوبی؟", NOW, Calendar.JALALI) is None
