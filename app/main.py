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
from app.agent.core import Agent
from app.agent.tools import build_registry
from app.bot.handlers import build_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.logging import LoggingMiddleware
from app.bot.middlewares.menu_reset import MenuResetMiddleware
from app.bot.middlewares.owner_only import OwnerOnlyMiddleware
from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker, run_migrations
from app.llm.providers import ProviderChain
from app.scheduler.jobs import catch_up_briefing
from app.scheduler.setup import create_scheduler


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


def build_dispatcher(config: Settings, sessionmaker, llm: ProviderChain) -> Dispatcher:
    agent = Agent(llm, build_registry())
    dp = Dispatcher(config=config, llm=llm, agent=agent)
    dp.update.outer_middleware(OwnerOnlyMiddleware(config.owner_id))
    dp.update.outer_middleware(LoggingMiddleware())
    dp.message.outer_middleware(MenuResetMiddleware())
    dp.update.middleware(DbSessionMiddleware(sessionmaker, config, llm))
    dp.include_router(build_router())
    return dp


async def run_bot(config: Settings) -> None:
    engine = create_engine(config.database_url)
    sessionmaker = create_sessionmaker(engine)
    llm = ProviderChain.from_settings(config)

    session = AiohttpSession(proxy=config.telegram_proxy) if config.telegram_proxy else None
    bot = Bot(
        token=config.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(config, sessionmaker, llm)
    scheduler = create_scheduler(bot, sessionmaker, config)

    try:
        await bot.set_my_commands(
            [BotCommand(command=cmd, description=desc) for cmd, desc in texts.COMMANDS.items()]
        )
        me = await bot.get_me()
        logger.info(
            "Vira v{} started as @{} (profile={}, models: {})",
            __version__,
            me.username,
            config.profile,
            llm.model,
        )
        await llm.check()  # informational only: the model may still be downloading
        scheduler.start()
        await catch_up_briefing(bot, sessionmaker, config)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        await llm.close()
        await engine.dispose()


def main() -> None:
    try:
        config = get_settings()
    except ValidationError as exc:
        problems = [
            str(err["loc"][0]).upper() if err["loc"] else err["msg"] for err in exc.errors()
        ]
        sys.exit(f"Invalid or missing settings in .env: {', '.join(problems)}")

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
