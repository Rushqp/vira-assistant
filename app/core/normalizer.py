"""Text normalization for Persian + English input.

v0.2 covers digits and language detection; number words, ZWNJ handling and ي/ك
unification are added with the parsers in v0.3.
"""

import re
from typing import Literal

Language = Literal["fa", "en"]

_TO_ASCII = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬",  # Persian digits, Arabic-Indic digits, Arabic decimal/thousands sep
    "01234567890123456789.,",
)
_TO_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# Arabic-script letters (Persian included), excluding the digit ranges above.
_PERSIAN_LETTER = re.compile(r"[ء-يپچژکگی]")


def to_ascii_digits(text: str) -> str:
    """`۱۲٫۵` → `12.5`."""
    return text.translate(_TO_ASCII)


def to_persian_digits(text: str) -> str:
    """`12` → `۱۲`."""
    return text.translate(_TO_PERSIAN)


def detect_language(text: str) -> Language:
    """`fa` if the text contains any Persian/Arabic letter, otherwise `en`."""
    return "fa" if _PERSIAN_LETTER.search(text) else "en"
