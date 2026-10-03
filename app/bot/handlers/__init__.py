"""Telegram handlers, one module per feature. `build_router` wires them together."""

from aiogram import Router

from app.bot.handlers import (
    assistant,
    categories,
    chat,
    chats,
    expenses,
    fallback,
    menu,
    reminders,
    reports,
    settings,
    start,
)


def build_router() -> Router:
    router = Router(name="root")
    # Order matters: buttons, commands and the forms' states first; then `assistant`, which
    # sends every other text message to the agent (or the rule-based fallback); then
    # `fallback` for everything that isn't text.
    router.include_routers(
        start.router,
        settings.router,
        categories.router,
        menu.router,
        chats.router,
        reminders.router,
        reports.router,
        expenses.router,
        chat.router,
        assistant.router,
        fallback.router,
    )
    return router
