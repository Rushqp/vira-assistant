"""After each update, tell the user when the answering AI model changed.

`ProviderChain` records a notice when a model stops answering (free quota used up, key
rejected, unreachable …) and the next one takes over, when the preferred model is back, or
when none is left. They are sent once the handler is done, so they follow the answer they
explain. (Before the rule-based fallback, `assistant.run_agent` sends them itself.)
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

from app.bot.agent_ui import send_notices
from app.config import Settings


class ModelNoticeMiddleware(BaseMiddleware):
    def __init__(self, llm: object, config: Settings) -> None:
        self.llm = llm
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        finally:
            bot: Bot | None = data.get("bot")
            if bot is not None:
                await send_notices(bot, self.config.owner_id, self.llm, self.config.timezone)
