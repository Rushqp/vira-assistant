from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import Calendar
from app.utils.calendar import format_date, format_datetime, to_local

TEHRAN = ZoneInfo("Asia/Tehran")


def test_format_date_jalali():
    assert format_date(date(2026, 10, 3), Calendar.JALALI) == "Sat 11 Mehr 1405"


def test_format_date_gregorian():
    assert format_date(date(2026, 10, 3), Calendar.GREGORIAN) == "Sat 3 Oct 2026"


def test_nowruz_is_first_of_farvardin():
    assert format_date(date(2026, 3, 21), Calendar.JALALI) == "Sat 1 Farvardin 1405"


def test_format_datetime_converts_utc_to_local():
    dt = datetime(2026, 10, 3, 16, 6, tzinfo=UTC)  # 19:36 in Tehran (UTC+3:30)
    assert format_datetime(dt, Calendar.JALALI, TEHRAN) == "Sat 11 Mehr 1405, 19:36"
    assert format_datetime(dt, Calendar.GREGORIAN, TEHRAN) == "Sat 3 Oct 2026, 19:36"


def test_date_rolls_over_at_local_midnight():
    dt = datetime(2026, 10, 3, 21, 0, tzinfo=UTC)  # 00:30 next day in Tehran
    assert format_datetime(dt, Calendar.GREGORIAN, TEHRAN) == "Sun 4 Oct 2026, 00:30"


def test_naive_datetime_is_treated_as_utc():
    assert to_local(datetime(2026, 1, 1, 0, 0), TEHRAN).hour == 3
