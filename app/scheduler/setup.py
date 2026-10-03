"""Creates the scheduler and registers the jobs."""

from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.scheduler.jobs import send_due_reminders, send_morning_briefing

CHECK_EVERY_SECONDS = 20


def create_scheduler(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], config: Settings
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.timezone)
    args = [bot, sessionmaker, config]
    scheduler.add_job(
        send_due_reminders,
        "interval",
        seconds=CHECK_EVERY_SECONDS,
        args=args,
        id="due_reminders",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(config.timezone),
    )
    briefing = config.morning_briefing_time
    scheduler.add_job(
        send_morning_briefing,
        CronTrigger(hour=briefing.hour, minute=briefing.minute, timezone=config.timezone),
        args=args,
        id="morning_briefing",
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler
