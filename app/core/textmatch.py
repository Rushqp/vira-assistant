"""Fuzzy matching of short Persian / English texts, for references like «تایم دکتر رو کنسل کن».

Used by the agent tools to find "the doctor reminder" or "the yogurt expense" among stored items.
A reference is only acted on when one item clearly matches best; otherwise the candidates are
returned so the user can choose.
"""

import re
from collections.abc import Callable, Iterable

from app.core.normalizer import ZWNJ, normalize

STOPWORDS = {
    # Persian
    "رو", "را", "و", "که", "به", "از", "با", "برای", "واسه", "تو", "توی", "این", "اون", "آن",
    "یه", "یک", "1", "من", "مال", "هم", "کن", "کنی", "بکن", "دارم", "داشتم", "بود", "شد", "اینو",
    "اونو", "تایم", "وقت", "قرار", "یادآور", "یادآوری", "هزینه", "خرج", "پاک", "حذف", "کنسل",
    # English
    "the", "a", "an", "to", "of", "for", "my", "me", "that", "this", "one", "please", "delete",
    "remove", "cancel", "reminder", "expense", "it",
}  # fmt: skip

_SPLIT = re.compile(rf"[^\w{ZWNJ}]+")


def tokens(text: str) -> set[str]:
    words = (w.replace(ZWNJ, "") for w in _SPLIT.split(normalize(text)))
    return {w for w in words if len(w) >= 2 and w not in STOPWORDS}


def score(query: str, text: str) -> float:
    """0 (no match) … 1+ (every query word found; +0.5 for the whole phrase)."""
    wanted, have = tokens(query), tokens(text)
    if not wanted:
        return 0.0
    hits = 0.0
    for word in wanted:
        if word in have:
            hits += 1
        elif len(word) >= 3 and any(h.startswith(word) or word.startswith(h) for h in have):
            hits += 0.7  # «دکترم» / «دکتر», "meetings" / "meeting"
    result = hits / len(wanted)
    if result and normalize(query).strip() in normalize(text):
        result += 0.5
    return result


def rank[T](items: Iterable[T], query: str, key: Callable[[T], str]) -> list[tuple[float, T]]:
    """Items with a positive score, best first."""
    scored = [(score(query, key(item)), item) for item in items]
    return sorted((pair for pair in scored if pair[0] > 0), key=lambda p: p[0], reverse=True)


def best_match[T](
    items: Iterable[T], query: str, key: Callable[[T], str]
) -> tuple[T | None, list[T]]:
    """(the single clear best match, or None) and all matches best first."""
    ranked = rank(items, query, key)
    matches = [item for _, item in ranked]
    if not ranked:
        return None, []
    if len(ranked) == 1 or ranked[0][0] > ranked[1][0] + 0.25:
        return ranked[0][1], matches
    return None, matches
