"""/status: version and uptime, AI models and voice engines, memory, storage, how much data
there is, the last backup and the errors since the start — one message for a quick health check.
"""

import html
import re
import shutil
import time
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__, texts
from app.config import Settings
from app.db.models import Expense, Note, Reminder, Todo
from app.llm.providers import ProviderChain
from app.services.backup import BackupError, database_path
from app.services.settings import SettingsService
from app.stt.chain import SpeechChain
from app.stt.engines import LocalWhisper
from app.utils.calendar import format_date

router = Router(name="status")


def duration(seconds: float) -> str:
    """`5 min`, `3 h 12 min`, `2 days 4 h`."""
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} day{'s' if days > 1 else ''} {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def size(number: float) -> str:
    """`812 KB`, `1.2 MB`, `18.4 GB`."""
    for unit in ("B", "KB", "MB", "GB"):
        if number < 1024 or unit == "GB":
            return f"{number:.0f} {unit}" if unit in ("B", "KB") else f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} GB"  # pragma: no cover


def memory_used() -> int | None:
    """This process's resident memory in bytes (Linux), None elsewhere."""
    try:
        status = Path("/proc/self/status").read_text()
    except OSError:
        return None
    match = re.search(r"VmRSS:\s+(\d+)\s+kB", status)
    return int(match[1]) * 1024 if match else None


async def counts(session: AsyncSession) -> dict[str, int]:
    async def count(query) -> int:
        return int(await session.scalar(query) or 0)

    return {
        "expenses": await count(select(func.count(Expense.id))),
        "reminders": await count(
            select(func.count(Reminder.id)).where(Reminder.status == "active")
        ),
        "todos": await count(select(func.count(Todo.id)).where(Todo.done_at.is_(None))),
        "notes": await count(select(func.count(Note.id))),
    }


def _ai_line(llm: object) -> str:
    if not isinstance(llm, ProviderChain) or not llm.clients:
        return texts.STATUS_AI_NONE
    answering = llm.answering() or llm.answering(need_tools=False) or llm.clients[0]
    paused = sum(1 for status in llm.status() if not status.ready)
    extra = texts.STATUS_AI_PAUSED.format(count=paused) if paused else ""
    return texts.STATUS_AI.format(model=html.escape(answering.label), paused=extra)


def _storage_line(config: Settings) -> str:
    try:
        path = database_path(config.database_url)
    except BackupError:
        return texts.STATUS_STORAGE.format(db=texts.STATUS_UNKNOWN, free=texts.STATUS_UNKNOWN)
    files = [path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")]
    used = sum(f.stat().st_size for f in files if f.exists())
    folder = path.parent if path.parent.exists() else Path(".")
    free = shutil.disk_usage(folder).free
    return texts.STATUS_STORAGE.format(db=size(used), free=size(free))


async def render_status(
    config: Settings,
    llm: object,
    stt: object,
    session: AsyncSession,
    settings_service: SettingsService,
    started_at: float,
    error_count: int,
) -> str:
    lines = [
        texts.STATUS_TITLE.format(
            version=__version__, uptime=duration(time.monotonic() - started_at)
        ),
        "",
        _ai_line(llm),
    ]
    whisper_loaded = False
    if not config.stt_enabled:
        lines.append(texts.STATUS_VOICE.format(engines=texts.STT_OFF))
    elif isinstance(stt, SpeechChain) and stt.engines:
        lines.append(texts.STATUS_VOICE.format(engines=html.escape(stt.model)))
        whisper_loaded = any(isinstance(e, LocalWhisper) and e.loaded for e in stt.engines)
    else:
        lines.append(texts.STATUS_VOICE.format(engines=texts.STT_NO_ENGINE))
    memory = memory_used()
    lines.append(
        texts.STATUS_MEMORY.format(
            memory=size(memory) if memory is not None else texts.STATUS_UNKNOWN,
            whisper=texts.STATUS_WHISPER if whisper_loaded else "",
        )
    )
    lines.append(_storage_line(config))
    lines.append(texts.STATUS_DATA.format(**await counts(session)))
    sent = await settings_service.backup_sent_at()
    if sent is None:
        when = texts.STATUS_BACKUP_NEVER
    else:
        local = sent.astimezone(config.timezone)
        calendar = await settings_service.get_calendar()
        when = f"{format_date(local.date(), calendar)}, {local:%H:%M}"
    lines.append(texts.STATUS_BACKUP.format(when=when))
    lines.append(texts.STATUS_ERRORS.format(count=error_count))
    return "\n".join(lines)


@router.message(Command("status"))
async def show_status(
    message: Message,
    config: Settings,
    llm: object,
    session: AsyncSession,
    settings_service: SettingsService,
    stt: object = None,
    started_at: float | None = None,
    errors: object = None,
) -> None:
    text = await render_status(
        config,
        llm,
        stt,
        session,
        settings_service,
        started_at if started_at is not None else time.monotonic(),
        getattr(errors, "count", 0),
    )
    await message.answer(text)
