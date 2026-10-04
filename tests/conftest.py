import pytest

from app.bot.handlers import (
    ai_models,
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
from app.config import Settings
from app.db.session import create_engine, create_sessionmaker, run_migrations
from tests.fakes import OWNER_ID, make_env


@pytest.fixture
def config(tmp_path, monkeypatch) -> Settings:
    monkeypatch.chdir(tmp_path)  # make sure a developer's local .env is not picked up
    return Settings(
        bot_token="123456:TEST",
        owner_id=OWNER_ID,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )


@pytest.fixture
async def sessionmaker(config):
    run_migrations(config.database_url)
    engine = create_engine(config.database_url)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture(autouse=True)
def detach_routers():
    """Handler routers are module-level singletons: detach them so each test can build a fresh
    dispatcher."""
    yield
    for module in (
        ai_models,
        start,
        settings,
        categories,
        menu,
        chats,
        reminders,
        reports,
        expenses,
        chat,
        assistant,
        fallback,
    ):
        module.router._parent_router = None


@pytest.fixture
async def env(config, sessionmaker):
    """Send messages / press buttons through the real dispatcher (fake Telegram + LLM)."""
    return make_env(config, sessionmaker)
