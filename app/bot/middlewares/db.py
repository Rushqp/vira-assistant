"""Opens a database session per update and exposes services to handlers."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.llm.client import LLMClient
from app.services.chat import ChatService
from app.services.settings import SettingsService


class DbSessionMiddleware(BaseMiddleware):
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], config: Settings, llm: LLMClient
    ) -> None:
        self.sessionmaker = sessionmaker
        self.config = config
        self.llm = llm

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            data["settings_service"] = SettingsService(session, self.config.default_calendar)
            data["chat_service"] = ChatService(
                session,
                self.llm,
                memory=self.config.chat_memory,
                timezone=self.config.timezone,
                keep=self.config.chat_keep,
            )
            return await handler(event, data)
