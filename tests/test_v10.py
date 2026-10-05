"""v1.0: error reports, the healthcheck / watchdog, /status, migrations in a child process,
the API proxy and releasing an unused local Whisper model."""

import asyncio
import os
import sqlite3
import time
from types import SimpleNamespace

from pydantic import SecretStr

from app import __version__, texts
from app.bot.errors import ErrorReporter, describe
from app.bot.handlers.status import duration, size
from app.db.session import migrate_in_subprocess
from app.health import Watchdog, check
from app.llm.client import LLMError
from app.llm.providers import ProviderChain, build_clients
from app.scheduler.setup import create_scheduler
from app.stt.chain import SpeechChain
from app.stt.engines import Audio, GroqWhisper, LocalWhisper
from tests.fakes import OWNER_ID, make_env, reply
from tests.test_reminders import FakeBot
from tests.test_stt import StubEngine


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- Error reports ---


async def test_errors_are_reported_once_in_a_while():
    clock = Clock()
    reporter = ErrorReporter(OWNER_ID, clock=clock)
    bot = FakeBot()
    assert await reporter.report(bot, "message «hi»", ValueError("bad"))  # type: ignore[arg-type]
    assert not await reporter.report(bot, "message «hi»", ValueError("bad"))  # type: ignore[arg-type]
    clock.now += 601
    assert await reporter.report(bot, "message «hi»", ValueError("bad"))  # type: ignore[arg-type]
    assert reporter.count == 3 and len(bot.sent) == 2
    assert bot.sent[0][0] == OWNER_ID and "<code>ValueError: bad</code>" in bot.sent[0][1]


async def test_a_crashing_handler_is_reported_not_silent(env):
    def explode(messages):
        raise RuntimeError("something unexpected")

    env.llm.script = [explode]
    await env.send("hello")
    report = env.session.sent[-1]
    assert report.startswith("⚠️ <b>Something went wrong</b> (message «hello»)")
    assert "RuntimeError: something unexpected" in report


async def test_a_crashing_button_gets_an_alert(env, monkeypatch):
    from app.bot.handlers import ai_models

    async def broken(*args, **kwargs):
        raise KeyError("boom")

    monkeypatch.setattr(ai_models, "render", broken)
    await env.send("/model")
    assert "KeyError" in env.session.sent[-1]


async def test_job_errors_are_reported():
    reporter = ErrorReporter(OWNER_ID)
    bot = FakeBot()
    listener = reporter.on_job_error(bot)  # type: ignore[arg-type]
    listener(SimpleNamespace(job_id="daily_digests", exception=OSError("disk full")))
    await asyncio.sleep(0)
    assert "job daily_digests" in bot.sent[0][1] and "disk full" in bot.sent[0][1]


def test_describe_updates():
    assert describe(None) == "update"
    update = SimpleNamespace(message=None, callback_query=SimpleNamespace(data="ai:pick:3"))
    assert describe(update) == "button ai:pick:3"  # type: ignore[arg-type]


# --- Healthcheck and watchdog ---


async def test_heartbeat_and_healthcheck(tmp_path):
    path = tmp_path / "beat"
    assert check(path) == 1  # no heartbeat yet
    watchdog = Watchdog(path)
    task = asyncio.create_task(watchdog.run())
    await asyncio.sleep(0.05)
    task.cancel()
    assert check(path) == 0
    old = time.time() - 600
    os.utime(path, (old, old))
    assert check(path) == 1  # stale: unhealthy


def test_watchdog_restarts_a_stuck_bot(tmp_path):
    exits = []
    watchdog = Watchdog(tmp_path / "beat", stuck_after=300, exit_process=exits.append)
    assert not watchdog.watch_once()
    watchdog.last -= 301
    assert watchdog.watch_once() and exits == [1]


# --- /status ---


def test_status_formatting():
    assert duration(300) == "5 min"
    assert duration(3 * 3600 + 12 * 60) == "3 h 12 min"
    assert duration(2 * 86400 + 4 * 3600) == "2 days 4 h"
    assert size(812 * 1024) == "812 KB"
    assert size(1.25 * 1024**2) == "1.2 MB"
    assert size(18.4 * 1024**3) == "18.4 GB"


async def test_status_command(env):
    await env.send("/status")
    text = env.session.sent[-1]
    assert text.startswith(f"📊 <b>Vira {__version__}</b> · running for 0 min")
    assert texts.STATUS_AI_NONE in text and "never (send /backup)" in text
    assert "0 expenses · 0 reminders · 0 open to-dos · 0 notes" in text
    assert "Errors since the start: 0" in text
    await env.send("/backup")
    await env.send("/status")
    assert "Last backup: " in env.session.sent[-1] and "never" not in env.session.sent[-1]


async def test_status_with_models(config, sessionmaker):
    paused = StubEngine("groq")
    chain = ProviderChain([StubAi("gemini", error=LLMError("auth")), StubAi("groq")])
    await chain.respond([], tools=[{}])  # gemini fails (paused), groq answers
    chain.drain_notices()
    env = make_env(config, sessionmaker, chain, stt=SpeechChain([paused]))
    await env.send("/status")
    text = env.session.sent[-1]
    assert "🤖 AI: <b>GROQ</b> · 1 paused" in text and "🎙 Voice: GROQ" in text


class StubAi:
    def __init__(self, name, error=None):
        self.name, self.model, self.error = name, f"{name}-model", error
        self.supports_tools = True

    @property
    def id(self):
        return f"{self.name}:{self.model}"

    @property
    def label(self):
        return self.name.upper()

    async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
        if self.error:
            raise self.error
        return reply("ok")

    async def close(self):
        pass


# --- Migrations in a child process ---


def test_migrations_run_in_a_child_process(tmp_path):
    db = tmp_path / "child.db"
    migrate_in_subprocess(f"sqlite+aiosqlite:///{db.as_posix()}")
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"notes", "todos", "expenses", "alembic_version"} <= tables


# --- API proxy ---


def test_api_proxy_is_used_for_apis_but_not_ollama(config):
    proxied = config.model_copy(
        update={"gemini_api_key": SecretStr("g"), "api_proxy": "socks5://127.0.0.1:1080"}
    )
    gemini, local = build_clients(proxied)
    assert gemini._client._client._mounts  # a proxy transport is mounted
    assert not getattr(local._client._client, "_mounts", {})
    groq = GroqWhisper("key", proxy="http://127.0.0.1:8080")
    assert groq._client._client._mounts


def test_telegram_proxy_accepts_socks5h():
    from app.config import Settings

    def proxy(value: str) -> str | None:
        return Settings(
            _env_file=None, bot_token="1:x", owner_id=1, telegram_proxy=value
        ).telegram_proxy

    assert proxy("socks5h://u:p@host:1080") == "socks5://u:p@host:1080"  # aiohttp-socks spelling
    assert proxy("http://host:8080") == "http://host:8080"
    assert proxy("  ") is None


def test_whisper_download_uses_the_proxy_but_ollama_never(monkeypatch):
    import sys
    import types

    from app.stt.engines import load_faster_whisper

    loaded = []
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = lambda model, **kwargs: loaded.append((model, kwargs)) or "whisper"
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    assert load_faster_whisper("small", "/models", proxy="socks5://p:1080") == "whisper"
    assert loaded == [
        ("small", {"device": "cpu", "compute_type": "int8", "download_root": "/models"})
    ]
    assert os.environ["HTTPS_PROXY"] == "socks5://p:1080"  # Hugging Face downloads (HTTPS)
    assert "HTTP_PROXY" not in os.environ  # plain-HTTP Ollama clients made later stay direct


# --- Releasing an unused local Whisper ---


async def test_local_whisper_leaves_ram_when_unused(config):
    clock = Clock()
    whisper = SimpleNamespace(
        transcribe=lambda audio, **kw: (
            [SimpleNamespace(text=" سلام ")],
            SimpleNamespace(language="fa"),
        )
    )
    engine = LocalWhisper("small", "models", loader=lambda *a: whisper, clock=clock)
    chain = SpeechChain([engine])
    await chain.transcribe(Audio(b"x"))
    assert engine.loaded
    await chain.release_idle()
    assert engine.loaded  # used just now
    clock.now += 601
    await chain.release_idle()
    assert not engine.loaded
    assert (await chain.transcribe(Audio(b"x"))).text == "سلام"  # loads again when needed


def test_scheduler_jobs(config, sessionmaker):
    scheduler = create_scheduler(None, sessionmaker, config, SpeechChain([]))  # type: ignore[arg-type]
    assert {job.id for job in scheduler.get_jobs()} == {
        "due_reminders",
        "daily_digests",
        "release_idle_models",
    }
