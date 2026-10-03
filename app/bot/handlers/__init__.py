"""Telegram handlers, one module per feature. `build_router` wires them together."""

from aiogram import Router

from app.bot.handlers import chat, chats, fallback, menu, reminders, settings, start


def build_router() -> Router:
    router = Router(name="root")
    # Order matters: specific buttons/commands first, then `reminders` (its form states and
    # free text with "remind me" / «یادم بنداز»), then `chat` (all remaining free text),
    # then `fallback` (everything else).
    router.include_routers(
        start.router,
        settings.router,
        menu.router,
        chats.router,
        reminders.router,
        chat.router,
        fallback.router,
    )
    return router
