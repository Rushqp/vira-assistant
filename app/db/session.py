"""Database engine, session factory and migrations.

Alembic is imported only inside the migration helpers: the bot runs migrations in a child
process (`migrate_in_subprocess`), so it never stays in the bot's memory.
"""

import subprocess
import sys
from pathlib import Path

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


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return cfg


def run_migrations(database_url: str) -> None:
    """Upgrade the database to the latest Alembic revision (synchronous)."""
    from alembic import command

    ensure_sqlite_dir(database_url)
    cfg = _alembic_config()
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["skip_logging"] = True  # keep the app's logging setup intact
    command.upgrade(cfg, "head")


def migrate_in_subprocess(database_url: str) -> None:
    """`run_migrations` in a child process (keeps Alembic out of the bot's memory)."""
    subprocess.run(
        [sys.executable, "-m", "app.db.migrate", database_url],
        check=True,
        cwd=PROJECT_ROOT,
    )


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

    scripts = ScriptDirectory.from_config(_alembic_config())
    return sorted(script.revision for script in scripts.walk_revisions())
