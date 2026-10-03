"""Reminder drafts, time calculations, storage and the scheduler jobs."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.config import Calendar
from app.core.parsers.datetime_parser import DayTimes, RepeatRule
from app.core.parsers.rules import parse_reminder
from app.db.models import ReminderAlert
from app.scheduler import jobs
from app.services.reminders import (
    ReminderDraft,
    ReminderService,
    alert_time,
    guess_important,
    monthly_date,
    next_occurrence,
    to_utc,
)
from app.services.settings import SettingsService

TZ = ZoneInfo("Asia/Tehran")
DT = DayTimes()
NOW = datetime(2026, 10, 3, 10, 0, tzinfo=TZ)  # Saturday 11 Mehr 1405, 10:00


def draft(text: str, now: datetime = NOW, cal: Calendar = Calendar.JALALI) -> ReminderDraft:
    parse = parse_reminder(text, now.date(), DT)
    return ReminderDraft.from_parse(parse, text, now, cal)


# --- Draft: questions ---


def test_ambiguous_then_alerts_then_ready():
    d = draft("Doctor tomorrow at 2, remind me in the morning")
    assert d.next_step(NOW, DT) == "ambiguous"
    d.time, d.ambiguous = "14:00", False
    assert d.alerts == [f"same_day:{DT.morning:%H:%M}"]
    assert d.next_step(NOW, DT) is None
    assert d.alert_times(NOW, DT) == [(datetime(2026, 10, 4, 9, 0, tzinfo=TZ), "spec")]


def test_ambiguous_notify_hour_is_chosen_before_the_event():
    d = draft("meeting tomorrow at 14:00, remind me at 8")
    assert d.alerts == ["same_day:08:00"]
    d = draft("meeting tomorrow at 22:00, remind me at 8")
    assert d.alerts == ["same_day:20:00"]


def test_missing_notify_is_asked():
    d = draft("دکتر فردا ساعت ۱۴، یادم بنداز")
    assert d.next_step(NOW, DT) == "alerts"


def test_missing_time_and_subject_are_asked():
    assert draft("یادم بنداز").next_step(NOW, DT) == "subject"
    d = draft("call the bank")
    assert d.next_step(NOW, DT) == "when"


def test_before_alert_needs_a_clock_time():
    d = draft("تولد مامان ۱۵ مهر، نیم ساعت قبلش یادم بنداز")
    assert d.next_step(NOW, DT) == "time"


def test_past_time_is_rejected():
    d = draft("call mom today at 08:00, remind me")
    assert d.next_step(NOW, DT) == "past"


def test_alerts_in_the_past_are_asked_again():
    d = draft("meeting today at 11:30am, remind me 2 hours before")
    assert d.next_step(NOW, DT) == "alerts_past"


def test_relative_reminder_is_ready():
    d = draft("۱۰ دقیقه دیگه یادم بنداز قرص بخورم")
    assert d.next_step(NOW, DT) is None
    assert d.alert_times(NOW, DT) == [(NOW + timedelta(minutes=10), "spec")]


def test_draft_round_trip():
    d = draft("remind me every day at 9pm to take my pills")
    assert ReminderDraft.from_dict(d.to_dict()) == d


# --- Draft: event times ---


def test_time_without_date_is_today_or_tomorrow():
    d = draft("remind me at 18:00 to stretch")
    assert d.event_datetime(NOW)[0] == datetime(2026, 10, 3, 18, 0, tzinfo=TZ)
    d = draft("remind me at 09:00 to stretch")
    assert d.event_datetime(NOW)[0] == datetime(2026, 10, 4, 9, 0, tzinfo=TZ)


def test_weekday_today_moves_a_week_if_passed():
    d = draft("gym on Saturday at 08:00, remind me")
    assert d.event_datetime(NOW)[0] == datetime(2026, 10, 10, 8, 0, tzinfo=TZ)
    d = draft("gym on Saturday at 18:00, remind me")
    assert d.event_datetime(NOW)[0] == datetime(2026, 10, 3, 18, 0, tzinfo=TZ)


def test_monthly_jalali_rule():
    d = draft("اجاره هر ماه ۵ام ساعت ۱۰ صبح یادم بنداز")
    assert d.repeat == "monthly:jalali:5"
    # 5 Mehr already passed → 5 Aban 1405 = 27 Oct 2026
    assert d.event_datetime(NOW)[0] == datetime(2026, 10, 27, 10, 0, tzinfo=TZ)


def test_all_day_event():
    d = draft("تولد مامان ۱۵ مهر، شب قبلش یادم بنداز")
    event, all_day = d.event_datetime(NOW)
    assert all_day and event.date() == date(2026, 10, 7)
    assert d.alert_times(NOW, DT) == [(datetime(2026, 10, 6, 22, 0, tzinfo=TZ), "spec")]


# --- Time helpers ---


def test_monthly_date_clamps_to_month_length():
    # 31 Shahrivar exists (31 days), Mehr has 30 days
    assert monthly_date(31, "jalali", date(2026, 9, 1), 1) == date(2026, 10, 22)  # 30 Mehr
    assert monthly_date(31, "gregorian", date(2026, 1, 15), 1) == date(2026, 2, 28)


def test_next_occurrence():
    event = datetime(2026, 10, 3, 9, 0, tzinfo=TZ)
    after = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)
    assert next_occurrence(RepeatRule("daily"), event, after) == datetime(
        2026, 10, 6, 9, 0, tzinfo=TZ
    )
    assert next_occurrence(RepeatRule("weekly", weekday=5), event, after) == datetime(
        2026, 10, 10, 9, 0, tzinfo=TZ
    )
    monthly = RepeatRule("monthly", day=11, calendar="jalali")  # 11 Mehr → 11 Aban
    assert next_occurrence(monthly, event, after) == datetime(2026, 11, 2, 9, 0, tzinfo=TZ)


def test_alert_time_specs():
    event = datetime(2026, 10, 4, 14, 0, tzinfo=TZ)
    assert alert_time("at", event, False, DT) == event
    assert alert_time("before:15", event, False, DT) == event - timedelta(minutes=15)
    assert alert_time("day_before:22:00", event, False, DT) == datetime(2026, 10, 3, 22, tzinfo=TZ)
    assert alert_time("same_day:09:00", event, False, DT) == datetime(2026, 10, 4, 9, tzinfo=TZ)
    assert alert_time("before:15", event, True, DT) is None
    assert alert_time("at", event, True, DT) == datetime(2026, 10, 4, 9, tzinfo=TZ)


def test_guess_important():
    assert guess_important("نوبت دکتر")
    assert guess_important("Pay the electricity bill")
    assert not guess_important("water the plants")


# --- Storage ---


def service(session) -> ReminderService:
    return ReminderService(session, TZ, DT)


async def test_create_stores_alerts_in_utc(sessionmaker):
    d = draft("Doctor tomorrow at 14:00, remind me 15 minutes before")
    d.important = True
    async with sessionmaker() as session:
        reminder = await service(session).create(d, NOW)
        loaded = await service(session).get(reminder.id)
        assert loaded is not None
        assert loaded.text == "Doctor" and loaded.important
        assert loaded.event_at == datetime(2026, 10, 4, 10, 30)  # 14:00 Tehran = 10:30 UTC
        assert [a.notify_at for a in loaded.alerts] == [datetime(2026, 10, 4, 10, 15)]
        assert loaded.alert_specs == "before:15"


async def test_replace_deletes_the_old_reminder(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        old = await svc.create(draft("remind me tomorrow at 9 am to call mom"), NOW)
        new_draft = draft("remind me tomorrow at 10 am to call mom")
        new_draft.replace_id = old.id
        await svc.create(new_draft, NOW)
        assert await svc.get(old.id) is None
        assert len(await svc.upcoming()) == 1


async def test_due_alerts_and_roll_forward_one_off(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        reminder = await svc.create(draft("remind me in 10 minutes to stretch"), NOW)
        later = to_utc(NOW + timedelta(minutes=11))
        due = await svc.due_alerts(later)
        assert [a.reminder_id for a in due] == [reminder.id]
        await svc.mark_sent(due[0])
        await svc.roll_forward(later)
        assert (await svc.get(reminder.id)).status == "done"  # type: ignore[union-attr]
        assert await svc.due_alerts(later) == []


async def test_repeating_reminder_moves_to_next_occurrence(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        reminder = await svc.create(draft("remind me every day at 21:00 to take my pills"), NOW)
        after = to_utc(datetime(2026, 10, 3, 21, 1, tzinfo=TZ))
        for alert in await svc.due_alerts(after):
            await svc.mark_sent(alert)
        await svc.roll_forward(after)
        loaded = await svc.get(reminder.id)
        assert loaded is not None and loaded.status == "active"
        assert loaded.event_at == to_utc(datetime(2026, 10, 4, 21, 0, tzinfo=TZ))
        pending = [a.notify_at for a in loaded.alerts if a.sent_at is None]
        assert pending == [to_utc(datetime(2026, 10, 4, 21, 0, tzinfo=TZ))]


async def test_mark_done_and_snooze(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        far = NOW.replace(year=2030)
        reminder = await svc.create(draft("remind me tomorrow at 9 am to call mom", far), far)
        when = await svc.snooze(reminder.id, 10)
        assert when is not None
        loaded = await svc.get(reminder.id)
        assert loaded is not None and any(a.kind == "extra" for a in loaded.alerts)

        await svc.mark_done(reminder.id)
        loaded = await svc.get(reminder.id)
        assert loaded is not None and loaded.status == "done"
        pending = await session.scalar(
            select(func.count()).select_from(ReminderAlert).where(ReminderAlert.sent_at.is_(None))
        )
        assert pending == 0


async def test_on_day_lists_important_first(sessionmaker):
    async with sessionmaker() as session:
        svc = service(session)
        a = draft("remind me tomorrow at 09:00 to water plants")
        b = draft("remind me tomorrow at 18:00 doctor")
        b.important = True
        await svc.create(a, NOW)
        await svc.create(b, NOW)
        day = await svc.on_day(date(2026, 10, 4))
        assert [r.text for r in day] == ["doctor", "water plants"]


# --- Scheduler jobs ---


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text))


@pytest.fixture
def frozen(monkeypatch):
    """Freeze "now" for the scheduler jobs."""

    def set_now(local: datetime):
        monkeypatch.setattr(jobs, "utcnow", lambda: to_utc(local))
        monkeypatch.setattr(jobs, "now_local", lambda tz: local.astimezone(tz))

    return set_now


async def test_send_due_reminders(config, sessionmaker, frozen):
    async with sessionmaker() as session:
        await service(session).create(draft("remind me in 10 minutes to stretch"), NOW)
    bot = FakeBot()

    frozen(NOW + timedelta(minutes=5))
    await jobs.send_due_reminders(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert bot.sent == []

    frozen(NOW + timedelta(minutes=10, seconds=20))
    await jobs.send_due_reminders(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == config.owner_id
    assert "stretch" in bot.sent[0][1] and "late" not in bot.sent[0][1]

    await jobs.send_due_reminders(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1  # not sent twice


async def test_late_alert_is_marked(config, sessionmaker, frozen):
    async with sessionmaker() as session:
        await service(session).create(draft("remind me in 10 minutes to stretch"), NOW)
    bot = FakeBot()
    frozen(NOW + timedelta(hours=3))
    await jobs.send_due_reminders(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert "sent late" in bot.sent[0][1]


async def test_morning_briefing(config, sessionmaker, frozen):
    async with sessionmaker() as session:
        svc = service(session)
        important = draft("remind me tomorrow at 14:00 doctor appointment")
        important.important = True
        await svc.create(important, NOW)
        await svc.create(draft("remind me tomorrow at 10:00 to water plants"), NOW)
    bot = FakeBot()
    frozen(datetime(2026, 10, 4, 8, 0, tzinfo=TZ))
    await jobs.send_morning_briefing(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1
    text = bot.sent[0][1]
    order = [text.index(part) for part in ("Important", "doctor", "<b>Today</b>", "water")]
    assert order == sorted(order)

    await jobs.send_morning_briefing(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1  # once a day


async def test_briefing_skipped_when_off_or_empty(config, sessionmaker, frozen):
    bot = FakeBot()
    frozen(datetime(2026, 10, 4, 8, 0, tzinfo=TZ))
    await jobs.send_morning_briefing(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert bot.sent == []  # nothing today

    async with sessionmaker() as session:
        await service(session).create(draft("remind me on monday at 10:00 to call"), NOW)
        await SettingsService(session, Calendar.JALALI).toggle_briefing()  # off
    frozen(datetime(2026, 10, 5, 8, 0, tzinfo=TZ))  # Monday: has a reminder, but briefing is off
    await jobs.send_morning_briefing(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert bot.sent == []


def test_utc_helpers():
    local = datetime(2026, 10, 3, 14, 0, tzinfo=TZ)
    assert to_utc(local) == datetime(2026, 10, 3, 10, 30)
    assert to_utc(local).tzinfo is None
    assert local.astimezone(UTC).hour == 10
    assert time(9) == DT.morning
