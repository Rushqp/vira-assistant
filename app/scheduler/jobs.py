"""Scheduled jobs. Each opens its own database session."""

from datetime import time, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot import views
from app.bot.keyboards.inline import reminder_notification
from app.config import Settings
from app.db.models import utcnow
from app.services.reminders import ReminderService
from app.services.settings import SettingsService
from app.utils.calendar import now_local

# An alert sent more than this after its time is marked "sent late".
LATE_AFTER = timedelta(minutes=2)
# A missed morning briefing is still sent after a restart until this time.
BRIEFING_CATCH_UP_UNTIL = time(12, 0)


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


async def catch_up_briefing(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    """After a restart in the morning, send the briefing that was missed."""
    current = now_local(config.timezone).time()
    if config.morning_briefing_time <= current < BRIEFING_CATCH_UP_UNTIL:
        await send_morning_briefing(bot, sessionmaker, config)
