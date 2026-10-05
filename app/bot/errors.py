"""Unexpected errors: logged with the traceback, and told to the owner in the chat.

Before v1.0 a crashing handler just left the user without an answer (that is how the
🤖 AI model bug went unnoticed). Now the owner gets a short message with the error, a button
press gets an alert, and scheduled jobs report their failures too. The same error is reported
at most once per `QUIET_FOR` seconds, so a broken loop can't flood the chat.
"""

import asyncio
import contextlib
import html
import time
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Update
from loguru import logger

from app import texts

QUIET_FOR = 600  # seconds between two reports of the same error


def describe(update: Update | None) -> str:
    """Where it happened, e.g. `message «/status»` or `button ai:pick:3`."""
    if update is None:
        return "update"
    if update.message:
        content = update.message.text or update.message.content_type
        return f"message «{content[:40]}»"
    if update.callback_query:
        return f"button {update.callback_query.data or ''}"
    return update.event_type


class ErrorReporter:
    def __init__(self, owner_id: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.owner_id = owner_id
        self.clock = clock
        self.count = 0  # since the bot started (shown by /status)
        self._last: dict[str, float] = {}

    async def report(self, bot: Bot, where: str, error: BaseException) -> bool:
        """Tell the owner. False when the same error was reported moments ago."""
        self.count += 1
        key = f"{where.split(' ')[0]}:{type(error).__name__}:{str(error)[:80]}"
        now = self.clock()
        if key in self._last and now - self._last[key] < QUIET_FOR:
            return False
        self._last[key] = now
        detail = f"{type(error).__name__}: {error}"[:300]
        text = texts.ERROR_REPORT.format(where=html.escape(where), error=html.escape(detail))
        try:
            await bot.send_message(self.owner_id, text)
        except TelegramAPIError as exc:
            logger.warning("Could not report an error to the owner: {}", exc)
        return True

    async def on_update_error(self, event: ErrorEvent, bot: Bot) -> bool:
        """aiogram's error handler: log, alert a button press, report."""
        logger.opt(exception=event.exception).error("Update failed: {}", describe(event.update))
        query = event.update.callback_query if event.update else None
        if query is not None:
            with contextlib.suppress(TelegramAPIError):  # maybe too late to answer that button
                await query.answer(texts.ERROR_ALERT, show_alert=True)
        await self.report(bot, describe(event.update), event.exception)
        return True

    def on_job_error(self, bot: Bot) -> Callable:
        """An APScheduler listener for failed jobs (reminders, briefing, backup …)."""

        def listener(event) -> None:
            logger.opt(exception=event.exception).error("Scheduled job {} failed", event.job_id)
            task = self.report(bot, f"job {event.job_id}", event.exception)
            asyncio.get_running_loop().create_task(task)

        return listener
