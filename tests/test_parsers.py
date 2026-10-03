"""Normalizer, date/time atoms and reminder rules (Persian + English).

"Today" is fixed to Saturday 3 Oct 2026 = 11 Mehr 1405.
"""

from datetime import date, time, timedelta

import pytest

from app.core.normalizer import ZWNJ, normalize, words_to_numbers
from app.core.parsers.datetime_parser import (
    DayTimes,
    RepeatRule,
    find_atoms,
    resolve,
    resolve_hour,
)
from app.core.parsers.rules import has_reminder_trigger, parse_reminder

TODAY = date(2026, 10, 3)  # Saturday
DT = DayTimes()


def moment(text: str):
    n = normalize(text, lowercase=False)
    return resolve(find_atoms(n, TODAY), TODAY, DT)


# --- Normalizer ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("صد و پنجاه", "150"),
        ("سه میلیون و پانصد هزار", "3500000"),
        ("twenty five", "25"),
        ("two hundred fifty", "250"),
        ("ساعت دو و نیم", "ساعت 2 و نیم"),
        ("ساعت نه", "ساعت 9"),
        ("نه، نمی‌خوام", "نه، نمی‌خوام"),  # "no", not 9
        ("یه ربع دیگه", "1 ربع دیگه"),
        ("the one I like", "the one I like"),
        ("3 میلیون", "3000000"),
    ],
)
def test_words_to_numbers(text, expected):
    assert words_to_numbers(text) == expected


def test_normalize_characters_and_compounds():
    assert normalize("كيك ۱۲") == "کیک 12"
    assert normalize("سه شنبه") == f"سه{ZWNJ}شنبه"
    assert normalize("پنجشنبه") == f"پنج{ZWNJ}شنبه"
    assert normalize("پس فردا بعد از ظهر") == f"پس{ZWNJ}فردا بعدازظهر"
    assert normalize("Hello  World", lowercase=False) == "Hello World"
    assert normalize("Hello") == "hello"


# --- Atoms & resolution ---


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("امروز", TODAY),
        ("فردا", TODAY + timedelta(days=1)),
        ("پس فردا", TODAY + timedelta(days=2)),
        ("tomorrow", TODAY + timedelta(days=1)),
        ("the day after tomorrow", TODAY + timedelta(days=2)),
        ("دوشنبه", date(2026, 10, 5)),
        ("next monday", date(2026, 10, 5)),
        ("سه شنبه آینده", date(2026, 10, 6)),
        ("۱۵ مهر", date(2026, 10, 7)),
        ("پنجم آبان", date(2026, 10, 27)),
        ("بیست و یکم آذر", date(2026, 12, 12)),
        ("1 farvardin", date(2027, 3, 21)),
        ("mehr 15", date(2026, 10, 7)),
        ("۱۰ مهر", date(2027, 10, 2)),  # already passed this year → next year
        ("oct 7", date(2026, 10, 7)),
        ("7 October 2027", date(2027, 10, 7)),
        ("۲۵ دسامبر", date(2026, 12, 25)),
        ("2026-11-02", date(2026, 11, 2)),
        ("1405/08/01", date(2026, 10, 23)),
    ],
)
def test_dates(text, day):
    assert moment(text).date == day


def test_weekday_today_is_flexible():
    m = moment("شنبه ساعت ۱۰ صبح")  # today is Saturday
    assert m.date == TODAY and m.flexible_week


@pytest.mark.parametrize(
    ("text", "clock", "ambiguous"),
    [
        ("ساعت ۲", time(2), True),
        ("at 2", time(2), True),
        ("ساعت ۲ بعدازظهر", time(14), False),
        ("۸ شب", time(20), False),
        ("۲ شب", time(2), False),  # after midnight
        ("۱۲ شب", time(0), False),
        ("ساعت ۷ صبح", time(7), False),
        ("۵ و نیم عصر", time(17, 30), False),
        ("ساعت ۴ و ربع", time(4, 15), True),
        ("ربع به ۳", time(2, 45), True),
        ("ساعت ۱۰ و ۲۰ دقیقه", time(10, 20), True),
        ("2pm", time(14), False),
        ("at 9:30 am", time(9, 30), False),
        ("12am", time(0), False),
        ("14:30", time(14, 30), False),
        ("08:15", time(8, 15), False),  # zero-padded = 24h
        ("8:15", time(8, 15), True),
        ("half past 7", time(7, 30), True),
        ("quarter to 9", time(8, 45), True),
        ("7 in the evening", time(19), False),
        ("noon", time(12), False),
        ("midnight", time(0), False),
        ("صبح", DT.morning, False),
        ("عصر", DT.evening, False),
        ("امشب", DT.night, False),
        ("tonight", DT.night, False),
        ("in the afternoon", DT.afternoon, False),
    ],
)
def test_times(text, clock, ambiguous):
    m = moment(text)
    assert (m.time, m.ambiguous) == (clock, ambiguous)


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("۱۰ دقیقه دیگه", 10),
        ("نیم ساعت دیگه", 30),
        ("یه ربع دیگه", 15),
        ("۲ ساعت و نیم دیگه", 150),
        ("in 10 minutes", 10),
        ("in half an hour", 30),
        ("in an hour", 60),
        ("3 days from now", 3 * 1440),
    ],
)
def test_relative_from_now(text, minutes):
    assert moment(text).delta == timedelta(minutes=minutes)


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("۱ ساعت قبلش", 60), ("نیم ساعت قبل", 30), ("15 minutes before", 15), ("یک روز قبل", 1440)],
)
def test_before(text, minutes):
    assert moment(text).minutes_before == minutes


def test_day_before():
    assert moment("شب قبلش").day_before == DT.night
    assert moment("the morning before").day_before == DT.morning
    assert moment("شب قبلش ساعت ۹").day_before == time(21)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("هر روز", RepeatRule("daily")),
        ("every day", RepeatRule("daily")),
        ("daily", RepeatRule("daily")),
        ("هر شنبه", RepeatRule("weekly", weekday=5)),
        ("every Saturday", RepeatRule("weekly", weekday=5)),
        ("every week", RepeatRule("weekly")),
        ("هر ماه ۵ام", RepeatRule("monthly", day=5)),
        ("every month on the 5th", RepeatRule("monthly", day=5)),
        ("monthly", RepeatRule("monthly")),
    ],
)
def test_repeats(text, rule):
    assert moment(text).repeat == rule


def test_every_morning_is_daily_at_morning():
    m = moment("هر صبح")
    assert m.repeat == RepeatRule("daily") and m.time == DT.morning


@pytest.mark.parametrize("text", ["I sat on the sun", "may I come", "hello there", "۱۲۳۴۵"])
def test_no_false_positives(text):
    assert moment(text).empty


def test_repeat_rule_round_trip():
    for rule in (
        RepeatRule("daily"),
        RepeatRule("weekly", weekday=3),
        RepeatRule("monthly", day=15, calendar="jalali"),
    ):
        assert RepeatRule.parse(rule.serialize()) == rule


@pytest.mark.parametrize(
    ("hour", "meridiem", "part", "expected"),
    [
        (2, "pm", None, time(14)),
        (12, "pm", None, time(12)),
        (12, "am", None, time(0)),
        (1, None, "noon", time(13)),
        (11, None, "noon", time(11)),
        (9, None, "night", time(21)),
        (3, None, "afternoon", time(15)),
    ],
)
def test_resolve_hour(hour, meridiem, part, expected):
    assert resolve_hour(hour, 0, meridiem, part) == (expected, False)


# --- Reminder rules ---


def test_trigger_detection():
    for text in ["یادم بنداز", "بهم یادآوری کن", "Remind me", "set a reminder", "یادت باشه"]:
        assert has_reminder_trigger(text), text
    for text in ["how are you", "یاد گرفتم", "سلام"]:
        assert not has_reminder_trigger(text), text


def test_event_and_notify_in_separate_clauses_fa():
    r = parse_reminder("فردا ساعت ۲ دکتر دارم، صبح یادم بنداز", TODAY, DT)
    assert r.subject == "دکتر دارم"
    assert (r.event.date, r.event.time, r.event.ambiguous) == (date(2026, 10, 4), time(2), True)
    assert r.notify is not None and r.notify.time == DT.morning
    assert not r.notify_at_event


def test_event_and_notify_in_separate_clauses_en():
    r = parse_reminder("Doctor tomorrow at 2, remind me in the morning", TODAY, DT)
    assert r.subject == "Doctor"
    assert r.event.date == date(2026, 10, 4)
    assert r.notify is not None and r.notify.time == DT.morning


def test_notify_attached_to_trigger_without_comma():
    r = parse_reminder("فردا ساعت ۲ دکتر دارم صبح یادم بنداز", TODAY, DT)
    assert r.event.time == time(2)
    assert r.notify is not None and r.notify.time == DT.morning


def test_trigger_without_time_means_ask():
    r = parse_reminder("دکتر فردا ساعت ۲، یادم بنداز", TODAY, DT)
    assert r.notify is None and not r.notify_at_event
    assert r.event.date == date(2026, 10, 4)


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        ("remind me to call mom tomorrow at 8", "call mom"),
        ("فردا ساعت ۸ نون بخرم یادم بنداز", "نون بخرم"),
        ("یادم بنداز فردا ساعت ۸ به مامان زنگ بزنم", "به مامان زنگ بزنم"),
    ],
)
def test_single_time_means_notify_at_that_time(text, subject):
    r = parse_reminder(text, TODAY, DT)
    assert r.notify_at_event
    assert r.subject == subject
    assert (r.event.date, r.event.time) == (date(2026, 10, 4), time(8))


def test_relative_reminder():
    r = parse_reminder("۱۰ دقیقه دیگه یادم بنداز قرص بخورم", TODAY, DT)
    assert r.notify_at_event and r.event.delta == timedelta(minutes=10)
    assert r.subject == "قرص بخورم"


def test_notify_before_and_day_before():
    r = parse_reminder(
        "Meeting with Ali on Saturday at 2PM, remind me 30 minutes before", TODAY, DT
    )
    assert r.subject == "Meeting with Ali"
    assert r.event.time == time(14)
    assert r.notify is not None and r.notify.minutes_before == 30

    r = parse_reminder("تولد مامان ۱۵ مهر، شب قبلش یادم بنداز", TODAY, DT)
    assert r.subject == "تولد مامان"
    assert r.event.date == date(2026, 10, 7) and r.event.time is None
    assert r.notify is not None and r.notify.day_before == DT.night


def test_repeating_reminder():
    r = parse_reminder("remind me every day at 9pm to take my pills", TODAY, DT)
    assert r.subject == "take my pills"
    assert r.event.repeat == RepeatRule("daily") and r.event.time == time(21)
    assert r.notify_at_event


def test_without_trigger_everything_is_the_event():
    r = parse_reminder("call the bank tomorrow at 16:00", TODAY, DT)
    assert not r.has_trigger and r.notify is None and not r.notify_at_event
    assert r.subject == "call the bank"
    assert r.event.time == time(16)
