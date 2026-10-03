import pytest

from app.config import Settings
from app.db.session import create_engine, create_sessionmaker, run_migrations

OWNER_ID = 1001


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
