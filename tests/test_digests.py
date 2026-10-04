"""The nightly report and the daily-digest clock: content, chosen times, once a day.

"Today" is Sunday 4 Oct 2026 = 12 Mehr 1405 (Tehran).
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.config import Calendar
from app.db.models import Expense
from app.scheduler import jobs
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService, to_utc
from app.services.settings import SettingsService
from tests.test_reminders import DT, FakeBot, draft

TZ = ZoneInfo("Asia/Tehran")
TODAY = datetime(2026, 10, 4, 10, 0, tzinfo=TZ)


@pytest.fixture
def at(monkeypatch):
    """Freeze "now" for the scheduler jobs."""

    def set_now(local: datetime):
        monkeypatch.setattr(jobs, "utcnow", lambda: to_utc(local))
        monkeypatch.setattr(jobs, "now_local", lambda tz: local.astimezone(tz))

    return set_now


async def add_expense(sessionmaker, description, amount, when, category="Groceries"):
    async with sessionmaker() as session:
        found = await ExpenseService(session, TZ, "toman").category_by_name(category)
        session.add(
            Expense(
                amount=amount,
                category_id=found.id,
                description=description,
                spent_at=to_utc(when),
            )
        )
        await session.commit()


async def add_reminder(sessionmaker, text, important=False):
    async with sessionmaker() as session:
        reminder = draft(text, now=TODAY)
        reminder.important = important
        await ReminderService(session, TZ, DT).create(reminder, TODAY)


async def test_nightly_report(config, sessionmaker, at):
    await add_expense(sessionmaker, "ماست", 200_000, datetime(2026, 10, 4, 9, 0, tzinfo=TZ))
    await add_expense(
        sessionmaker, "بنزین", 100_000, datetime(2026, 10, 4, 18, 0, tzinfo=TZ), "Fuel"
    )
    await add_expense(
        sessionmaker, "رستوران", 1_500_000, datetime(2026, 9, 25, 13, 0, tzinfo=TZ), "Restaurant"
    )
    await add_reminder(sessionmaker, "remind me tomorrow at 10:00 to water the plants")
    await add_reminder(sessionmaker, "remind me tomorrow at 14:00 doctor appointment", True)
    bot = FakeBot()
    at(datetime(2026, 10, 4, 22, 0, tzinfo=TZ))
    await jobs.send_nightly_report(bot, sessionmaker, config)  # type: ignore[arg-type]

    [(chat_id, text)] = bot.sent
    assert chat_id == config.owner_id
    assert "🌙 <b>Your day</b> · Sun 12 Mehr 1405" in text
    assert "Spent today: <b>300,000 toman</b> · 2 expenses" in text
    assert "🛒 Groceries" in text and "ماست — 200,000 toman" in text
    # 1,800,000 in the 12 days of Mehr so far
    assert "This month so far: <b>1,800,000 toman</b> · daily average 150,000 toman" in text
    tomorrow = text[text.index("Tomorrow") :]
    assert tomorrow.index("⭐ 14:00") < tomorrow.index("10:00 — water the plants")

    await jobs.send_nightly_report(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1  # once a day


async def test_quiet_day_gets_a_nudge(config, sessionmaker, at):
    bot = FakeBot()
    at(datetime(2026, 10, 4, 22, 0, tzinfo=TZ))
    await jobs.send_nightly_report(bot, sessionmaker, config)  # type: ignore[arg-type]
    text = bot.sent[0][1]
    assert "No expenses recorded today" in text
    assert "Nothing scheduled for tomorrow" in text
    assert "This month so far" not in text


async def test_nightly_report_can_be_turned_off(config, sessionmaker, at):
    async with sessionmaker() as session:
        await SettingsService(session, Calendar.JALALI).set_nightly(False)
    bot = FakeBot()
    at(datetime(2026, 10, 4, 22, 0, tzinfo=TZ))
    await jobs.send_daily_digests(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert bot.sent == []


async def test_digests_follow_the_chosen_times(config, sessionmaker, at):
    async with sessionmaker() as session:
        service = SettingsService(session, Calendar.JALALI)
        await service.set_nightly_time(time(21, 30))
        await service.set_briefing_time(time(7, 0))
    await add_reminder(sessionmaker, "remind me tomorrow at 10:00 to call mom")
    bot = FakeBot()

    at(datetime(2026, 10, 4, 21, 29, tzinfo=TZ))
    await jobs.send_daily_digests(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert bot.sent == []
    at(datetime(2026, 10, 4, 21, 30, tzinfo=TZ))
    await jobs.send_daily_digests(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1 and "Your day" in bot.sent[0][1]
    at(datetime(2026, 10, 4, 23, 50, tzinfo=TZ))
    await jobs.send_daily_digests(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 1

    # The next morning the bot was offline at 07:00 and starts at 10:30: still sent.
    at(datetime(2026, 10, 5, 10, 30, tzinfo=TZ))
    await jobs.send_daily_digests(bot, sessionmaker, config)  # type: ignore[arg-type]
    assert len(bot.sent) == 2 and "Good morning" in bot.sent[1][1]


@pytest.mark.parametrize(
    ("now", "at_time", "due"),
    [
        (datetime(2026, 10, 4, 22, 0), time(22, 0), True),
        (datetime(2026, 10, 4, 21, 59), time(22, 0), False),
        (datetime(2026, 10, 4, 11, 59), time(8, 0), True),
        (datetime(2026, 10, 4, 12, 0), time(8, 0), False),  # more than 4 hours late
        (datetime(2026, 10, 5, 0, 30), time(22, 0), False),  # yesterday's report: too late
    ],
)
def test_is_due(now, at_time, due):
    assert jobs.is_due(now.replace(tzinfo=TZ), at_time) is due
