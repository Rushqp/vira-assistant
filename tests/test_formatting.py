from datetime import date

import pytest

from app.config import Calendar
from app.core.normalizer import detect_language, to_ascii_digits, to_persian_digits
from app.utils.calendar import format_date
from app.utils.formatting import markdown_to_html, split_point

# --- markdown_to_html ---


@pytest.mark.parametrize(
    ("md", "expected"),
    [
        ("**bold** text", "<b>bold</b> text"),
        ("use `x < y`", "use <code>x &lt; y</code>"),
        ("```python\nif a < b:\n    pass\n```", "<pre>if a &lt; b:\n    pass</pre>"),
        ("## Title\nbody", "<b>Title</b>\nbody"),
        ("1 < 2 & 3 > 2", "1 &lt; 2 &amp; 3 &gt; 2"),
        ("**سلام** دنیا", "<b>سلام</b> دنیا"),
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
    ],
)
def test_markdown_to_html(md, expected):
    assert markdown_to_html(md) == expected


@pytest.mark.parametrize("partial", ["**unfinished bold", "```code not closed", "`half"])
def test_partial_markdown_stays_literal(partial):
    html = markdown_to_html(partial)
    assert "<b>" not in html and "<pre>" not in html and "<code>" not in html


def test_code_is_not_formatted_inside():
    assert markdown_to_html("`**not bold**`") == "<code>**not bold**</code>"


# --- split_point ---


def test_short_text_is_not_split():
    assert split_point("hello", limit=10) == 5


def test_split_prefers_paragraph_then_line_then_space():
    text = "a" * 60 + "\n\n" + "b" * 60
    assert split_point(text, limit=100) == 62
    text = "a" * 60 + "\n" + "b" * 60
    assert split_point(text, limit=100) == 61
    text = "a" * 60 + " " + "b" * 60
    assert split_point(text, limit=100) == 61


def test_split_hard_cut_without_separators():
    assert split_point("x" * 250, limit=100) == 100


# --- normalizer ---


def test_digits():
    assert to_ascii_digits("۱۲۳٤٥ و ۷٫۵") == "12345 و 7.5"
    assert to_persian_digits("2026/10/03") == "۲۰۲۶/۱۰/۰۳"


@pytest.mark.parametrize(
    ("text", "lang"),
    [("Hello", "en"), ("سلام", "fa"), ("hi سلام", "fa"), ("۱۲۳", "en"), ("گچپژ", "fa")],
)
def test_detect_language(text, lang):
    assert detect_language(text) == lang


# --- Persian calendar names ---


def test_format_date_persian():
    d = date(2026, 10, 3)
    assert format_date(d, Calendar.JALALI, "fa") == "شنبه ۱۱ مهر ۱۴۰۵"
    assert format_date(d, Calendar.GREGORIAN, "fa", weekday=False) == "۳ اکتبر ۲۰۲۶"
