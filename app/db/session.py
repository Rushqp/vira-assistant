"""Database engine, session factory and migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory of a file-based SQLite database."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def run_migrations(database_url: str) -> None:
    """Upgrade the database to the latest Alembic revision (synchronous)."""
    ensure_sqlite_dir(database_url)
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["skip_logging"] = True  # keep the app's logging setup intact
    command.upgrade(cfg, "head")


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def known_revisions() -> list[str]:
    """Every migration revision of this app ("0001" …), e.g. to check a backup's schema."""
    from alembic.script import ScriptDirectory

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return sorted(script.revision for script in ScriptDirectory.from_config(cfg).walk_revisions())
