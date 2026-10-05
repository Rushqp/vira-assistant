"""Telegram handlers, one module per feature. `build_router` wires them together."""

from aiogram import Router

from app.bot.handlers import (
    ai_models,
    assistant,
    backup,
    categories,
    chat,
    chats,
    expenses,
    fallback,
    notes,
    reminders,
    reports,
    settings,
    start,
    status,
    todos,
)


def build_router() -> Router:
    router = Router(name="root")
    # Order matters: buttons, commands and the forms' states first; then `assistant`, which
    # sends every other text message to the agent (or the rule-based fallback); then
    # `fallback` for everything that isn't text.
    router.include_routers(
        start.router,
        status.router,
        settings.router,
        ai_models.router,
        categories.router,
        backup.router,
        todos.router,
        notes.router,
        chats.router,
        reminders.router,
        reports.router,
        expenses.router,
        chat.router,
        assistant.router,
        fallback.router,
    )
    return router
