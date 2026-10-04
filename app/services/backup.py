"""Backups of the whole database, and restoring one.

- `make_backup`: a consistent copy of the live SQLite database (the SQLite backup API, safe
  while the bot runs), zipped with a small manifest.
- `inspect_backup`: checks an uploaded file (zip or raw .db): integrity, tables, and that its
  schema version is one this app knows.
- `restore_backup`: copies a backup over the live database in place (again with the backup API,
  so open connections stay valid); migrations then bring an older backup up to date.
"""

import json
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy.engine import make_url

DB_NAME = "vira.db"
MANIFEST = "backup.json"
SQLITE_HEADER = b"SQLite format 3\x00"
REQUIRED_TABLES = {"alembic_version", "settings", "expenses", "reminders"}
COUNTED = ("expenses", "reminders", "todos", "notes")


class BackupError(Exception):
    def __init__(self, reason: str, newer: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.newer = newer  # made by a newer version of the app


@dataclass
class BackupInfo:
    revision: str
    counts: dict[str, int] = field(default_factory=dict)
    created: datetime | None = None


def database_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise BackupError("only a file-based SQLite database can be backed up")
    return Path(url.database)


def _copy(source: Path, target: Path) -> None:
    src = sqlite3.connect(source, timeout=30)
    dst = sqlite3.connect(target, timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _inspect_file(path: Path) -> BackupInfo:
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BackupError("not a database") from exc
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("the database is damaged")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if missing := REQUIRED_TABLES - tables:
            raise BackupError(f"missing tables: {', '.join(sorted(missing))}")
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        if row is None:
            raise BackupError("no schema version")
        counts = {
            name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in COUNTED
            if name in tables
        }
        return BackupInfo(revision=row[0], counts={n: counts.get(n, 0) for n in COUNTED})
    except sqlite3.DatabaseError as exc:
        raise BackupError("not a database") from exc
    finally:
        con.close()


def make_backup(db_path: Path, created: datetime, version: str) -> tuple[bytes, BackupInfo]:
    """The zipped copy of the database, and what it contains."""
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / DB_NAME
        _copy(db_path, copy)
        info = _inspect_file(copy)
        info.created = created
        manifest = {
            "app": "vira-assistant",
            "version": version,
            "created": created.isoformat(),
            "revision": info.revision,
            "counts": info.counts,
        }
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(copy, DB_NAME)
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        return buffer.getvalue(), info


def _unpack(data: bytes) -> tuple[bytes, datetime | None]:
    """The SQLite bytes of a backup (zip or raw .db) and its creation time, if known."""
    if data.startswith(SQLITE_HEADER):
        return data, None
    if not data.startswith(b"PK"):
        raise BackupError("not a zip or SQLite file")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
            db_name = (
                DB_NAME
                if DB_NAME in names
                else next((n for n in names if n.endswith((".db", ".sqlite"))), None)
            )
            if db_name is None:
                raise BackupError("no database in the zip")
            content = archive.read(db_name)
            created = None
            if MANIFEST in names:
                manifest = json.loads(archive.read(MANIFEST))
                created = datetime.fromisoformat(manifest["created"])
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise BackupError("the zip is damaged") from exc
    if not content.startswith(SQLITE_HEADER):
        raise BackupError("not a database")
    return content, created


def _check_revision(info: BackupInfo, known: list[str]) -> None:
    if info.revision in known:
        return
    newer = bool(known) and info.revision > max(known)  # revisions are "0001", "0002", …
    raise BackupError(f"unknown schema version {info.revision}", newer=newer)


def inspect_backup(data: bytes, known_revisions: list[str]) -> BackupInfo:
    content, created = _unpack(data)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / DB_NAME
        path.write_bytes(content)
        info = _inspect_file(path)
    _check_revision(info, known_revisions)
    info.created = created
    return info


def restore_backup(data: bytes, db_path: Path, known_revisions: list[str]) -> BackupInfo:
    """Replace the live database with the backup. Run the migrations afterwards."""
    content, created = _unpack(data)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / DB_NAME
        path.write_bytes(content)
        info = _inspect_file(path)
        _check_revision(info, known_revisions)
        _copy(path, db_path)
    info.created = created
    return info
