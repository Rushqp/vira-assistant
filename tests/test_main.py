"""The entry point: settings errors, migrations, startup and shutdown (with fakes)."""

import logging
import subprocess

import pytest
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.methods import GetMe

from app import main as entry
from app.config import Settings


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(entry, "setup_logging", lambda level: None)


def test_missing_settings_exit_with_their_names(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.setattr(entry, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert "BOT_TOKEN" in str(stop.value) and "OWNER_ID" in str(stop.value)


def test_failed_migrations_stop_the_bot(monkeypatch, config, quiet):
    def fail(url):
        raise subprocess.CalledProcessError(1, "migrate")

    monkeypatch.setattr(entry, "get_settings", lambda: config)
    monkeypatch.setattr(entry, "migrate_in_subprocess", fail)
    with pytest.raises(SystemExit) as stop:
        entry.main()
    assert "migrations failed" in str(stop.value)


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [(TelegramUnauthorizedError(GetMe(), "Unauthorized"), 1), (KeyboardInterrupt(), None)],
)
def test_startup_errors(monkeypatch, config, quiet, error, exit_code):
    async def run(config):
        raise error

    monkeypatch.setattr(entry, "get_settings", lambda: config)
    monkeypatch.setattr(entry, "migrate_in_subprocess", lambda url: None)
    monkeypatch.setattr(entry, "run_bot", run)
    if exit_code is None:
        entry.main()  # Ctrl+C: a clean stop
    else:
        with pytest.raises(SystemExit) as stop:
            entry.main()
        assert stop.value.code == exit_code


class FakeWatchdog:
    def start_thread(self):
        pass

    async def run(self):
        pass


class FakeSession:
    closed = False

    async def close(self):
        FakeSession.closed = True


class FakeBot:
    def __init__(self, *args, **kwargs):
        self.session = FakeSession()

    async def set_my_commands(self, commands):
        self.commands = commands

    async def get_me(self):
        raise TelegramUnauthorizedError(GetMe(), "Unauthorized")


async def test_run_bot_starts_and_cleans_up(monkeypatch, config, sessionmaker):
    monkeypatch.setattr(entry, "Bot", FakeBot)
    monkeypatch.setattr(entry, "Watchdog", FakeWatchdog)
    with pytest.raises(TelegramUnauthorizedError):
        await entry.run_bot(config)
    assert FakeSession.closed  # the finally block ran


def test_stdlib_logging_goes_to_loguru():
    from loguru import logger

    lines: list[str] = []
    entry.setup_logging("INFO")
    sink = logger.add(lambda message: lines.append(str(message)), level="INFO")
    logging.getLogger("aiogram.test").warning("hello from aiogram")
    logger.remove(sink)
    assert any("hello from aiogram" in line for line in lines)
