"""Migrations upgrade existing data correctly."""

import sqlite3

from alembic import command
from alembic.config import Config

from app.db.session import PROJECT_ROOT, run_migrations


def _alembic(url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["skip_logging"] = True
    return cfg


def test_0003_backfills_titles_and_keeps_history(tmp_path):
    db = tmp_path / "old.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    command.upgrade(_alembic(url), "0002")

    con = sqlite3.connect(db)
    con.executescript(
        """
        INSERT INTO chat_sessions (id, started_at, ended_at) VALUES
            (1, '2026-10-01 10:00:00', '2026-10-01 11:00:00'),
            (2, '2026-10-02 10:00:00', NULL);
        INSERT INTO chat_history (session_id, role, content, created_at) VALUES
            (1, 'user', 'First question', '2026-10-01 10:05:00'),
            (1, 'assistant', 'Answer', '2026-10-01 10:06:00');
        """
    )
    con.commit()
    con.close()

    run_migrations(url)

    con = sqlite3.connect(db)
    rows = con.execute("SELECT id, title, updated_at FROM chat_sessions ORDER BY id").fetchall()
    assert rows == [
        (1, "First question", "2026-10-01 10:06:00"),
        (2, None, "2026-10-02 10:00:00"),
    ]
    assert con.execute("SELECT count(*) FROM chat_history").fetchone() == (2,)
    schema = con.execute("SELECT sql FROM sqlite_master WHERE name = 'chat_sessions'").fetchone()[0]
    assert "AUTOINCREMENT" in schema
    con.close()


def test_downgrade_to_base_and_back(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
