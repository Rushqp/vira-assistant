"""Scheduled jobs. Each opens its own database session.

- `send_due_reminders` (every 20 s): reminder alerts.
- `send_daily_digests` (every 30 s): the morning briefing and the nightly report, at the times
  chosen in ⚙️ Settings (defaults from .env). A message missed while the bot was offline is
  still sent within `DIGEST_GRACE` of its time, on the same day.
"""

from datetime import datetime, time, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import texts
from app.bot import views
from app.bot.keyboards.inline import reminder_notification
from app.config import Settings
from app.db.models import utcnow
from app.services.expenses import ExpenseService
from app.services.reminders import ReminderService
from app.services.reports import ReportService
from app.services.settings import SettingsService
from app.utils.calendar import now_local

# An alert sent more than this after its time is marked "sent late".
LATE_AFTER = timedelta(minutes=2)
# A daily message missed while offline is still sent this long after its time (same day).
DIGEST_GRACE = timedelta(hours=4)


async def send_due_reminders(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    now_utc = utcnow()
    async with sessionmaker() as session:
        service = ReminderService(session, config.timezone, config.day_times)
        calendar = await SettingsService(session, config.default_calendar).get_calendar()
        for alert in await service.due_alerts(now_utc):
            reminder = alert.reminder
            late = now_utc - alert.notify_at > LATE_AFTER
            text = views.notification(
                reminder, now_local(config.timezone), config.timezone, calendar, late
            )
            try:
                await bot.send_message(
                    config.owner_id, text, reply_markup=reminder_notification(reminder.id)
                )
            except TelegramAPIError as exc:
                logger.warning("Could not send reminder {}: {} (will retry)", reminder.id, exc)
                continue
            await service.mark_sent(alert)
        await service.roll_forward(now_utc)


async def send_morning_briefing(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    """Today's reminders, important ones first. Sent at most once a day, skipped if empty."""
    now = now_local(config.timezone)
    async with sessionmaker() as session:
        settings = SettingsService(session, config.default_calendar)
        if not await settings.briefing_enabled() or await settings.briefing_sent_on() == now.date():
            return
        reminders = await ReminderService(session, config.timezone, config.day_times).on_day(
            now.date()
        )
        await settings.mark_briefing_sent(now.date())
        if not reminders:
            return
        calendar = await settings.get_calendar()
        try:
            await bot.send_message(
                config.owner_id, views.briefing(reminders, now, config.timezone, calendar)
            )
        except TelegramAPIError as exc:
            logger.warning("Could not send the morning briefing: {}", exc)


async def send_nightly_report(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    """Today's expenses, this month so far and tomorrow's reminders. At most once a day."""
    now = now_local(config.timezone)
    today = now.date()
    async with sessionmaker() as session:
        settings = SettingsService(session, config.default_calendar)
        if not await settings.nightly_enabled() or await settings.nightly_sent_on() == today:
            return
        calendar = await settings.get_calendar()
        expenses = ExpenseService(session, config.timezone, config.currency.value)
        reports = ReportService(expenses)
        day = await reports.build("day", today, calendar)
        month = await reports.build("month", today, calendar)
        tomorrow = await ReminderService(session, config.timezone, config.day_times).on_day(
            today + timedelta(days=1)
        )
        await settings.mark_nightly_sent(today)
        text = views.nightly_report(
            day,
            month,
            tomorrow,
            config.timezone,
            calendar,
            texts.CURRENCY_LABELS[config.currency.value],
        )
        try:
            await bot.send_message(config.owner_id, text)
        except TelegramAPIError as exc:
            logger.warning("Could not send the nightly report: {}", exc)


def is_due(now: datetime, at: time) -> bool:
    """`at` has passed today, by less than DIGEST_GRACE."""
    scheduled = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return scheduled <= now < scheduled + DIGEST_GRACE


async def send_daily_digests(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    """Send the morning briefing and the nightly report when their time has come."""
    now = now_local(config.timezone)
    async with sessionmaker() as session:
        settings = SettingsService(session, config.default_calendar)
        briefing_at = await settings.briefing_time(config.morning_briefing_time)
        nightly_at = await settings.nightly_time(config.daily_report_time)
    if is_due(now, briefing_at):
        await send_morning_briefing(bot, sessionmaker, config)
    if is_due(now, nightly_at):
        await send_nightly_report(bot, sessionmaker, config)
