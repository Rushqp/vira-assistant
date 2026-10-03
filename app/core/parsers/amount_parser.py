"""Money amounts and quantities in normalized Persian + English text.

Input must be passed through `normalize()` first: number words are digits and a number followed
by a scale word is already combined («۳ میلیون» → `3000000`). Left for this module:
- decimals / halves with a scale: `2.5 میلیون`, `2 و نیم میلیون`, `100k`, `1.2m`
- currency words: تومن / تومان / ریال / toman / rial
- quantities: «۱۰ لیتر», `2 kg`, «۳ تا»

An amount below 1000 without a scale («۳ تومن», `150`) is *ambiguous*: thousand or million?
The user is asked (see `ExpenseDraft`).
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.core.normalizer import ZWNJ

Currency = Literal["toman", "rial"]

B = rf"(?<![\w{ZWNJ}.,])"
E = rf"(?![\w{ZWNJ}])"
NUM = r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

SCALES = {
    "هزار": 1_000, "میلیون": 1_000_000, "ملیون": 1_000_000, "میلیارد": 1_000_000_000,
    "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
    "k": 1_000, "m": 1_000_000, "mil": 1_000_000, "mln": 1_000_000,
}  # fmt: skip
CURRENCIES: dict[str, Currency] = {
    "تومن": "toman", "تومان": "toman", "toman": "toman", "tomans": "toman",
    "ریال": "rial", "rial": "rial", "rials": "rial", "irr": "rial",
}  # fmt: skip
UNITS = {
    "لیتر": "L", "liter": "L", "liters": "L", "litre": "L", "litres": "L", "l": "L",
    "کیلو": "kg", "کیلوگرم": "kg", "kg": "kg", "kilo": "kg", "kilos": "kg",
    "گرم": "g", "gram": "g", "grams": "g", "g": "g",
    "عدد": "pcs", "تا": "pcs", "دونه": "pcs", "دانه": "pcs", "pcs": "pcs", "piece": "pcs",
    "pieces": "pcs", "بسته": "pack", "pack": "pack", "packs": "pack",
    "بطری": "bottle", "bottle": "bottle", "bottles": "bottle",
    "متر": "meter", "meter": "meter", "meters": "meter", "نفر": "people", "people": "people",
}  # fmt: skip


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


SCALE = _alt(SCALES)
CURRENCY = _alt(CURRENCIES)
UNIT = _alt(UNITS)

_SCALED = re.compile(
    rf"{B}(?P<n>{NUM})(?P<half>\s*و\s*نیم)?\s*(?P<scale>{SCALE}){E}(?:\s*(?P<cur>{CURRENCY}){E})?",
    re.IGNORECASE,
)
_WITH_CURRENCY = re.compile(rf"{B}(?P<n>{NUM})\s*(?P<cur>{CURRENCY}){E}", re.IGNORECASE)
_BARE = re.compile(rf"{B}(?P<n>{NUM})(?![\d\w{ZWNJ}])")
_QUANTITY = re.compile(rf"{B}(?P<n>{NUM})\s*(?P<unit>{UNIT}){E}", re.IGNORECASE)
CURRENCY_WORD = re.compile(rf"{B}(?:{CURRENCY}){E}", re.IGNORECASE)

_MASK = "\x00"


@dataclass
class Amount:
    start: int
    end: int
    value: float  # in the currency given by `currency` (or the default currency if None)
    ambiguous: bool  # below 1000 without scale: thousand or million?
    currency: Currency | None  # explicit currency word, if any
    bare: bool  # a plain number without scale or currency (weakest evidence)


@dataclass
class Quantity:
    start: int
    end: int
    value: float
    unit: str


def parse_number(text: str) -> float:
    """`1,500,000` → 1500000, `2.5` → 2.5."""
    return float(text.replace(",", ""))


def mask(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = _MASK
    return "".join(chars)


def find_quantities(text: str) -> list[Quantity]:
    return [
        Quantity(m.start(), m.end(), parse_number(m["n"]), UNITS[m["unit"].lower()])
        for m in _QUANTITY.finditer(text)
    ]


def find_amounts(text: str) -> list[Amount]:
    """Amounts in priority order: scaled, then with a currency word, then bare numbers."""
    found: list[Amount] = []
    masked = text

    def take(match: re.Match, amount: Amount) -> None:
        nonlocal masked
        found.append(amount)
        masked = mask(masked, [(match.start(), match.end())])

    for m in _SCALED.finditer(masked):
        value = (parse_number(m["n"]) + (0.5 if m["half"] else 0)) * SCALES[m["scale"].lower()]
        cur = CURRENCIES[m["cur"].lower()] if m["cur"] else None
        take(m, Amount(m.start(), m.end(), value, False, cur, False))
    for m in _WITH_CURRENCY.finditer(masked):
        value = parse_number(m["n"])
        cur = CURRENCIES[m["cur"].lower()]
        take(m, Amount(m.start(), m.end(), value, value < 1000, cur, False))
    for m in _BARE.finditer(masked):
        value = parse_number(m["n"])
        if value == 0:
            continue
        take(m, Amount(m.start(), m.end(), value, value < 1000, None, True))
    return sorted(found, key=lambda a: a.start)


def to_currency(value: float, given: Currency | None, target: Currency) -> int:
    """Convert between toman and rial (1 toman = 10 rial); round to a whole unit."""
    if given == "rial" and target == "toman":
        value /= 10
    elif given == "toman" and target == "rial":
        value *= 10
    return round(value)
