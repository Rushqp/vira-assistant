"""Shows a streamed LLM answer by editing a Telegram message as text arrives.

Telegram rate-limits edits, so the message is updated at most once per `interval` seconds.
Answers longer than one message continue in a new message.
"""

import asyncio
import time

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from app.utils.formatting import markdown_to_html, split_point


class MessageStreamer:
    def __init__(self, reply_to: Message, interval: float = 1.0) -> None:
        self.reply_to = reply_to
        self.interval = interval
        self.text = ""  # full raw answer so far
        self._offset = 0  # start of the part shown in the current message
        self._message: Message | None = None
        self._shown = ""  # HTML currently displayed in `_message`
        self._last_edit = 0.0

    @property
    def started(self) -> bool:
        return self._message is not None

    async def push(self, piece: str) -> None:
        self.text += piece
        if time.monotonic() - self._last_edit >= self.interval:
            await self._render()

    async def finish(self, suffix: str = "") -> None:
        """Show the complete answer (plus an optional suffix such as an error notice)."""
        self.text += suffix
        await self._render()

    async def _render(self) -> None:
        current = self.text[self._offset :]
        while len(current) > split_point(current):
            # Close the current message at a clean break and continue in a new one.
            cut = split_point(current)
            await self._show(current[:cut])
            self._offset += cut
            self._message, self._shown = None, ""
            current = self.text[self._offset :]
        if current.strip():
            await self._show(current)

    async def _show(self, raw: str) -> None:
        html = markdown_to_html(raw.strip())
        if html == self._shown:
            return
        try:
            if self._message is None:
                self._message = await self.reply_to.answer(html)
            else:
                await self._message.edit_text(html)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            return await self._show(raw)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise
        self._shown = html
        self._last_edit = time.monotonic()
