"""Telegram handlers, one module per feature. `build_router` wires them together."""

from aiogram import Router

from app.bot.handlers import (
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
    # Order matters: specific buttons/commands first; then the free-text features, each with
    # its own form states and detector: `reminders` ("remind me" / «یادم بنداز»), `reports`
    # («گزارش این ماه»), `expenses` (an amount + «دادم» / تومن); then `chat` (all remaining
    # free text), then `fallback` (everything else).
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
        fallback.router,
    )
    return router
