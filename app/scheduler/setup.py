"""Creates the scheduler and registers the jobs."""

from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.scheduler.jobs import send_daily_digests, send_due_reminders

CHECK_EVERY_SECONDS = 20
DIGESTS_EVERY_SECONDS = 30


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
    # The times can change in ⚙️ Settings, so this checks them instead of a fixed cron time
    # (the first run, right at startup, also catches up a message missed while offline).
    scheduler.add_job(
        send_daily_digests,
        "interval",
        seconds=DIGESTS_EVERY_SECONDS,
        args=args,
        id="daily_digests",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(config.timezone),
    )
    return scheduler
