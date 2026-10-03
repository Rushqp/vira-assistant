"""Logs each incoming update and how long it took to handle."""

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started = time.perf_counter()
        kind = event.event_type if isinstance(event, Update) else type(event).__name__
        try:
            return await handler(event, data)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            logger.debug("Handled {} in {:.1f} ms", kind, elapsed)
