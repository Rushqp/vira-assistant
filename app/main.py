"""Entry point: `python -m app.main`."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand
from loguru import logger
from pydantic import ValidationError

from app import __version__, texts
from app.bot.handlers import build_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.logging import LoggingMiddleware
from app.bot.middlewares.owner_only import OwnerOnlyMiddleware
from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker, run_migrations


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (aiogram, aiohttp, alembic) into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level.upper(), backtrace=False, diagnose=False)
    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)


def build_dispatcher(config: Settings, sessionmaker) -> Dispatcher:
    dp = Dispatcher(config=config)
    dp.update.outer_middleware(OwnerOnlyMiddleware(config.owner_id))
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware(sessionmaker, config))
    dp.include_router(build_router())
    return dp


async def run_bot(config: Settings) -> None:
    engine = create_engine(config.database_url)
    sessionmaker = create_sessionmaker(engine)

    session = AiohttpSession(proxy=config.telegram_proxy) if config.telegram_proxy else None
    bot = Bot(
        token=config.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(config, sessionmaker)

    try:
        await bot.set_my_commands(
            [BotCommand(command=cmd, description=desc) for cmd, desc in texts.COMMANDS.items()]
        )
        me = await bot.get_me()
        logger.info(
            "Vira v{} started as @{} (profile={})", __version__, me.username, config.profile
        )
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    try:
        config = get_settings()
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]).upper() for err in exc.errors())
        sys.exit(f"Invalid or missing settings in .env: {fields}")

    setup_logging(config.log_level)
    logger.info("Applying database migrations…")
    run_migrations(config.database_url)
    try:
        asyncio.run(run_bot(config))
    except TelegramUnauthorizedError:
        logger.error("Telegram rejected BOT_TOKEN. Check the token from @BotFather in .env")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
