"""Text normalization for Persian + English input.

`normalize()` is applied before any rule-based parsing:
- Persian / Arabic-Indic digits → ASCII (`۱۲` → `12`)
- Arabic `ي` / `ك` → Persian `ی` / `ک`, Arabic diacritics removed
- ZWNJ variants unified, whitespace collapsed, Latin letters lower-cased (optional)
- number words → digits (`صد و پنجاه` → `150`, `twenty five` → `25`)
"""

import re
from typing import Literal

Language = Literal["fa", "en"]

ZWNJ = "‌"

_TO_ASCII = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬",  # Persian digits, Arabic-Indic digits, Arabic decimal/thousands sep
    "01234567890123456789.,",
)
_TO_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_CHARS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "‍": ZWNJ})
_DIACRITICS = re.compile(r"[ً-ٰٟ]")

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


# --- Number words ---

_UNITS = {
    # Persian (with common colloquial spellings)
    "صفر": 0, "یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "شیش": 6,
    "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سیزده": 13,
    "چهارده": 14, "پانزده": 15, "پونزده": 15, "شانزده": 16, "شونزده": 16, "هفده": 17,
    "هیفده": 17, "هجده": 18, "هیجده": 18, "نوزده": 19,
    "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70, "هشتاد": 80,
    "نود": 90, "صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
    "پانصد": 500, "پونصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900,
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_HUNDRED = {"hundred"}
_SCALES = {
    "هزار": 1_000, "میلیون": 1_000_000, "ملیون": 1_000_000, "میلیارد": 1_000_000_000,
    "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
}  # fmt: skip
_JOINERS = {"و", "and"}

# Single words that are also ordinary words ("نه" = "no", "سی" = "thirty"/"CD", "one" = "the one").
# They are converted only next to a context word (ساعت, دقیقه, هزار, ...) or another number.
_AMBIGUOUS = {"نه", "سی", "one", "یه"}
_CONTEXT = {
    "ساعت", "دقیقه", "ثانیه", "روز", "هفته", "ماه", "سال", "تومن", "تومان", "ریال", "لیتر",
    "کیلو", "عدد", "تا", "صبح", "ظهر", "شب", "عصر", "بعدازظهر", "ربع", "دیگه", "دیگر", "بعد",
    "قبل", "o'clock", "oclock", "minute", "minutes", "hour", "hours", "day", "days", "week",
    "weeks", "month", "months", "am", "pm", "toman", "tomans", "rial", "rials",
}  # fmt: skip

_TOKEN = re.compile(r"\S+")


def _is_number_word(token: str) -> bool:
    token = token.lower()
    return token in _UNITS or token in _SCALES or token in _HUNDRED or token.isdigit()


def _value(tokens: list[str]) -> int:
    total = current = 0
    for tok in (t.lower() for t in tokens):
        if tok in _JOINERS:
            continue
        if tok.isdigit():
            current += int(tok)
        elif tok in _UNITS:
            current += _UNITS[tok]
        elif tok in _HUNDRED:
            current = (current or 1) * 100
        else:  # scale
            total += (current or 1) * _SCALES[tok]
            current = 0
    return total + current


def words_to_numbers(text: str) -> str:
    """Replace runs of number words with digits: `سه میلیون و پانصد هزار` → `3500000`.

    Digits inside a run are combined too (`3 میلیون` → `3000000`). Expects ASCII digits
    (see `normalize`).
    """
    tokens = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(text)]
    out: list[str] = []
    last_end = 0
    i = 0
    while i < len(tokens):
        start, _, tok = tokens[i]
        if not (_is_number_word(tok) and not tok.isdigit()) and not (
            tok.isdigit() and i + 1 < len(tokens) and tokens[i + 1][2].lower() in _SCALES
        ):
            i += 1
            continue
        # Grow the run: number words, optionally joined by "و" / "and".
        j = i
        run = [tok]
        while j + 1 < len(tokens):
            nxt = tokens[j + 1][2]
            if _is_number_word(nxt) and not nxt.isdigit():
                run.append(nxt)
                j += 1
            elif nxt.lower() in _JOINERS and j + 2 < len(tokens):
                after = tokens[j + 2][2]
                if _is_number_word(after) and not after.isdigit():
                    run += [nxt, after]
                    j += 2
                else:
                    break
            else:
                break
        if len(run) == 1 and tok.lower() in _AMBIGUOUS:
            prev_tok = tokens[i - 1][2].lower() if i > 0 else ""
            next_tok = tokens[j + 1][2].lower() if j + 1 < len(tokens) else ""
            if prev_tok not in _CONTEXT and next_tok not in _CONTEXT:
                i += 1
                continue
        out.append(text[last_end:start])
        out.append(str(_value(run)))
        last_end = tokens[j][1]
        i = j + 1
    out.append(text[last_end:])
    return "".join(out)


# Multi-word expressions written with or without space / ZWNJ, unified to one token
# (also keeps "سه شنبه" from becoming "3 شنبه").
_COMPOUNDS = [
    (re.compile(rf"(یک|دو|سه|چهار|پنج)[\s{ZWNJ}]*شنبه"), rf"\1{ZWNJ}شنبه"),
    (re.compile(rf"پس[\s{ZWNJ}]*فردا"), f"پس{ZWNJ}فردا"),
    (re.compile(rf"بعد[\s{ZWNJ}]*از[\s{ZWNJ}]*ظهر"), "بعدازظهر"),
    (re.compile(rf"نیمه[\s{ZWNJ}]*شب"), f"نیمه{ZWNJ}شب"),
    (re.compile(rf"فردا[\s{ZWNJ}]*شب"), f"فردا{ZWNJ}شب"),
    # «یاد آوری», «یاد اوری», «یاداوری» → «یادآوری» (common spellings without the madda)
    (re.compile(rf"یاد[\s{ZWNJ}]*[اآ]وری"), "یادآوری"),
    (re.compile(rf"یاد[\s{ZWNJ}]*[اآ]ور(?![\w{ZWNJ}])"), "یادآور"),
    (re.compile(rf"(?<![\w{ZWNJ}])[اآ]لارم"), "آلارم"),
]


def normalize(text: str, *, lowercase: bool = True) -> str:
    text = to_ascii_digits(text).translate(_CHARS)
    text = _DIACRITICS.sub("", text)
    text = re.sub(rf"\s*{ZWNJ}\s*", ZWNJ, text)
    text = re.sub(r"\s+", " ", text).strip()
    if lowercase:
        text = text.lower()
    for pattern, replacement in _COMPOUNDS:
        text = pattern.sub(replacement, text)
    return words_to_numbers(text)
