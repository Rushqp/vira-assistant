"""Pressing a main-menu button or sending a command leaves any half-finished form.

Without this, a reminder form waiting for "when?" would swallow the next menu button.
Registered as an *outer* message middleware so it runs before the state filters.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from app import texts

MENU_BUTTONS = {
    texts.BTN_NEW_CHAT,
    texts.BTN_CHATS,
    texts.BTN_NEW_REMINDER,
    texts.BTN_ADD_EXPENSE,
    texts.BTN_TODAY_REPORT,
    texts.BTN_MONTH_REPORT,
    texts.BTN_REMINDERS,
    texts.BTN_TODOS,
    texts.BTN_NOTES,
    texts.BTN_SETTINGS,
}


class MenuResetMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        text = event.text if isinstance(event, Message) else None
        state: FSMContext | None = data.get("state")
        if (
            text
            and state
            and data.get("raw_state")
            and (text in MENU_BUTTONS or text.startswith("/"))
        ):
            await state.clear()
            data["raw_state"] = None  # state filters read this value
        return await handler(event, data)
