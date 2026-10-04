"""Reminder sentences → event time, notification time and a clean subject.

How time expressions are assigned (the sentence is split into clauses at , ، ; . ! ?):
- No trigger phrase (e.g. typed into the 🆕 reminder form): everything describes the event and
  the notification time is asked.
- The trigger clause ("remind me …", «… یادم بنداز») has no time, another clause has one:
  that time is the event; the notification time is asked.
  «فردا ساعت ۲ دکتر دارم، یادم بنداز»
- A single time expression in the trigger clause and nothing elsewhere: notify at that time.
  «remind me to call mom tomorrow at 8» · «۱۰ دقیقه دیگه یادم بنداز»
- Otherwise the expression attached to the trigger is the notification time, the rest is the event.
  «Doctor tomorrow at 2, remind me in the morning» · «فردا ساعت ۲ دکتر دارم صبح یادم بنداز»
"""

import re
from dataclasses import dataclass
from datetime import date, time

from app.core.normalizer import detect_language, normalize
from app.core.parsers.datetime_parser import Atom, B, DayTimes, E, Moment, find_atoms, resolve

_SET_FA = r"(?:بذار(?:ی|ید)?|بزار(?:ی|ید)?|(?:ثبت|تنظیم|ست|درست)\s*کن(?:ی|ید)?|کن(?:ی|ید)?)"
_ARTICLE_FA = r"(?:(?:یه|یک|1)\s*)?"
# Always mean "create a reminder".
TRIGGER = re.compile(
    r"\b(?:please\s+)?remind\s+me\b"
    r"|\b(?:set|add|create|make)\s+(?:a\s+|an\s+|me\s+a\s+)?(?:reminder|alarm)\b"
    r"|\bdon'?t\s+let\s+me\s+forget\b"
    rf"|{B}(?:بهم\s*|به\s*من\s*)?یاد(?:م|ت|\s*من)?\s*(?:بنداز(?:ی|ید)?|بیار(?:ی|ید)?|باشه){E}"
    rf"|{B}(?:بهم\s*)?{_ARTICLE_FA}(?:یادآوری|یادآور|آلارم|هشدار)\s*(?:برام\s*|واسم\s*)?{_SET_FA}{E}",
    re.IGNORECASE,
)
# Mean "create a reminder" only when the sentence also contains a date or time:
# «ساعت ۵ خبرم کن» is a reminder, «بهم بگو پایتخت فرانسه کجاست» or «یادآوری چیه؟» is not.
WEAK_TRIGGER = re.compile(
    r"\b(?:notify|alert|ping|tell|call|wake)\s+me(?:\s+up)?\b|\bremind\b|\breminders?\b|\balarm\b"
    rf"|{B}{_ARTICLE_FA}(?:یادآوری|یادآور|آلارم){E}"
    rf"|{B}(?:خبرم\s*کن(?:ی|ید)?|بهم\s*خبر\s*بده|بهم\s*بگو|صدام\s*کن|بیدارم\s*کن|یادت\s*نره){E}",
    re.IGNORECASE,
)
# Alarms / wake-up calls need no subject: a default one is used.
_ALARM = re.compile(r"\balarm\b|\bwake\b|آلارم|هشدار|بیدارم", re.IGNORECASE)
_WAKE = re.compile(r"\bwake\b|بیدارم", re.IGNORECASE)
DEFAULT_SUBJECTS = {
    ("fa", True): "بیدار شدن",
    ("fa", False): "آلارم",
    ("en", True): "Wake up",
    ("en", False): "Alarm",
}
_CLAUSE_BREAK = re.compile(r"[,،;؛.!?؟\n]")
# Words allowed between atoms of one cluster ("tomorrow at 2", «فردا ساعت ۲»).
_FILLER = re.compile(r"^(?:\s|\x00|\b(?:at|on|in|the|of|by|around|حدود|ساعت|روز)\b)*$", re.I)
# Words left over around the subject after removing time expressions and the trigger.
_EDGE_WORDS_EN = r"(?:to|that|about|for|at|on|in|by|please|me|i|and|also)"
_EDGE_WORDS_FA = r"(?:که|بهم|به\s*من|لطفا|لطفاً|برای|و|هم|رو)"


@dataclass
class ReminderParse:
    subject: str
    event: Moment
    notify: Moment | None  # None: not specified → ask the user
    notify_at_event: bool  # remind exactly at the event time
    has_trigger: bool


def find_trigger(text: str, today: date | None = None) -> re.Match | None:
    """The phrase that makes `text` (normalized) a reminder request, if any."""
    if match := TRIGGER.search(text):
        return match
    weak = WEAK_TRIGGER.search(text)
    if weak and find_atoms(text, today or date.today()):
        return weak
    return None


def has_reminder_trigger(text: str) -> bool:
    return find_trigger(normalize(text, lowercase=False)) is not None


def _clusters(text: str, atoms: list[Atom]) -> list[list[Atom]]:
    clusters: list[list[Atom]] = []
    for atom in atoms:
        if clusters:
            gap = text[clusters[-1][-1].end : atom.start]
            if _FILLER.match(gap) and not _CLAUSE_BREAK.search(gap):
                clusters[-1].append(atom)
                continue
        clusters.append([atom])
    return clusters


def _clause_of(text: str, pos: int) -> tuple[int, int]:
    starts = [m.end() for m in _CLAUSE_BREAK.finditer(text, 0, pos)]
    start = starts[-1] if starts else 0
    end_match = _CLAUSE_BREAK.search(text, pos)
    return start, end_match.start() if end_match else len(text)


def _pick_notify_cluster(
    text: str, clusters: list[list[Atom]], trigger: re.Match, lang: str
) -> list[Atom] | None:
    """The cluster attached to the trigger phrase, if any."""
    before = [c for c in clusters if c[-1].end <= trigger.start()]
    after = [c for c in clusters if c[0].start >= trigger.end()]
    touching_before = (
        before[-1] if before and _FILLER.match(text[before[-1][-1].end : trigger.start()]) else None
    )
    first_after = after[0] if after else None
    if lang == "fa":
        return touching_before or first_after
    return first_after or touching_before


def _clean_subject(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    subject = "".join(chars)
    subject = re.sub(r"\s+", " ", subject)
    edge = rf"(?:{_EDGE_WORDS_EN}|{_EDGE_WORDS_FA})"
    for _ in range(3):  # strip leftovers like "to", "that", «که» at both ends
        subject = re.sub(rf"^[\s,،;:.\-–]*{edge}(?=\s|$)", "", subject, flags=re.I)
        subject = re.sub(rf"(?<=\s){edge}[\s,،;:.!?؟\-–]*$", "", subject, flags=re.I)
        subject = subject.strip(" ,،;:.!?؟-–")
    return subject.strip()


def parse_reminder(raw: str, today: date, day_times: DayTimes) -> ReminderParse:
    text = normalize(raw, lowercase=False)
    atoms = find_atoms(text, today)
    trigger = find_trigger(text, today)
    clusters = _clusters(text, atoms)

    # Repeats always describe the event, wherever they appear.
    repeat_atoms = [a for a in atoms if a.kind == "repeat"]
    clusters = [[a for a in c if a.kind != "repeat"] for c in clusters]
    clusters = [c for c in clusters if c]

    notify_atoms: list[Atom] | None = None
    notify_at_event = False
    event_clusters = clusters
    if trigger:
        start, end = _clause_of(text, trigger.start())
        in_clause = [c for c in clusters if start <= c[0].start < end]
        elsewhere = [c for c in clusters if not start <= c[0].start < end]
        if in_clause and not elsewhere and len(in_clause) == 1:
            only = in_clause[0]
            if all(a.kind in ("before", "day_before") for a in only):
                notify_atoms, event_clusters = only, []
            else:
                notify_at_event = True
        elif in_clause:
            picked = _pick_notify_cluster(text, in_clause, trigger, detect_language(text))
            if picked is not None:
                notify_atoms = picked
                event_clusters = [c for c in clusters if c is not picked]

    event_atoms = [a for c in event_clusters for a in c] + repeat_atoms
    event = resolve(sorted(event_atoms, key=lambda a: a.start), today, day_times)
    notify = resolve(notify_atoms, today, day_times) if notify_atoms is not None else None

    spans = [(a.start, a.end) for a in atoms]
    if trigger:
        spans.append(trigger.span())
    subject = _clean_subject(text, spans)
    if not subject and trigger and _ALARM.search(trigger.group()):
        wake = bool(_WAKE.search(trigger.group()))
        subject = DEFAULT_SUBJECTS[(detect_language(text), wake)]
    return ReminderParse(
        subject=subject,
        event=event,
        notify=notify,
        notify_at_event=notify_at_event,
        has_trigger=trigger is not None,
    )


# --- A clock time on its own ("21:30", «۹ شب», "9pm") ---

_BARE_TIME = re.compile(r"^\s*([0-9۰-۹]{1,2})(?:[:٫.]([0-9۰-۹]{2}))?\s*$")


def parse_clock(
    raw: str, today: date, day_times: DayTimes, *, evening: bool = False
) -> time | None:
    """A clock time typed alone. An hour that could be AM or PM («ساعت ۱۰», "10") is read as
    PM when `evening` (e.g. the nightly report's time), otherwise as AM."""
    text = f"ساعت {raw.strip()}" if _BARE_TIME.match(raw) else raw
    moment = parse_reminder(text, today, day_times).event
    if moment.time is None:
        return None
    clock = moment.time
    if moment.ambiguous and clock.hour == 0:  # a bare "12" is noon
        return clock.replace(hour=12)
    if moment.ambiguous and evening and clock.hour < 12:
        return clock.replace(hour=clock.hour + 12)
    return clock
