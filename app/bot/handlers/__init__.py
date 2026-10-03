"""Telegram handlers, one module per feature. `build_router` wires them together."""

from aiogram import Router

from app.bot.handlers import menu, settings, start


def build_router() -> Router:
    router = Router(name="root")
    # Order matters: `menu` contains the catch-all fallback and must come last.
    router.include_routers(start.router, settings.router, menu.router)
    return router
