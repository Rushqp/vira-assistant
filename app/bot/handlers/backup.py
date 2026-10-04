"""💾 Backup: /backup or ⚙️ Settings → 💾 Backup sends all data as one file, a copy comes every
Friday night, and sending a backup file back restores it (after a confirmation, with a copy of
the current data sent first).
"""

import asyncio
import re
import sqlite3
from datetime import datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Document, InlineKeyboardMarkup, Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__, texts
from app.bot.keyboards.inline import BackupCb, backup_menu, restore_confirm
from app.bot.states import BackupForm
from app.config import Calendar, Settings
from app.db.session import known_revisions, run_migrations
from app.services.backup import (
    COUNTED,
    BackupError,
    database_path,
    inspect_backup,
    make_backup,
    restore_backup,
)
from app.services.export import date_text
from app.services.settings import SettingsService
from app.utils.calendar import format_date, now_local

router = Router(name="backup")

BACKUP_WEEKDAY = 4  # Friday
BACKUP_TIME = time(23, 30)
MAX_UPLOAD = 20 * 1024 * 1024  # bots can't download bigger files
_BACKUP_NAME = re.compile(r"\.(zip|db|sqlite3?)$", re.IGNORECASE)
_BACKUP_TYPES = {"application/zip", "application/x-sqlite3", "application/vnd.sqlite3"}


def counts_text(counts: dict[str, int]) -> str:
    return texts.BACKUP_COUNTS.format(**{name: counts.get(name, 0) for name in COUNTED})


def last_slot(now: datetime) -> datetime:
    """The most recent weekly backup time (Friday 23:30) at or before `now`."""
    back = (now.weekday() - BACKUP_WEEKDAY) % 7
    slot = (now - timedelta(days=back)).replace(
        hour=BACKUP_TIME.hour, minute=BACKUP_TIME.minute, second=0, microsecond=0
    )
    return slot if slot <= now else slot - timedelta(days=7)


async def send_backup(
    bot: Bot, config: Settings, calendar: Calendar, caption: str | None = None
) -> None:
    now = now_local(config.timezone)
    path = database_path(config.database_url)
    content, info = await asyncio.to_thread(make_backup, path, now, __version__)
    stamp = date_text(now.date(), calendar).replace("/", "-")
    text = caption or texts.BACKUP_CAPTION.format(
        date=f"{format_date(now.date(), calendar)}, {now:%H:%M}", counts=counts_text(info.counts)
    )
    document = BufferedInputFile(content, filename=f"vira-backup-{stamp}.zip")
    await bot.send_document(config.owner_id, document, caption=text)


async def render_backup(settings_service: SettingsService) -> tuple[str, InlineKeyboardMarkup]:
    weekly = await settings_service.backup_enabled()
    state = (
        texts.BACKUP_WEEKLY_ON.format(time=f"{BACKUP_TIME:%H:%M}")
        if weekly
        else texts.BACKUP_WEEKLY_OFF
    )
    return "\n".join([texts.BACKUP_TITLE, texts.BACKUP_ABOUT, "", state]), backup_menu(weekly)


async def _edit(message: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def _send_now(bot: Bot, config: Settings, settings_service: SettingsService) -> bool:
    try:
        await send_backup(bot, config, await settings_service.get_calendar())
    except (BackupError, OSError, sqlite3.Error):
        logger.exception("Backup failed")
        return False
    return True


@router.message(Command("backup"))
async def backup_command(
    message: Message, config: Settings, settings_service: SettingsService
) -> None:
    assert message.bot is not None
    if not await _send_now(message.bot, config, settings_service):
        await message.answer(texts.BACKUP_FAILED)


@router.callback_query(BackupCb.filter(F.action == "open"))
async def open_backup(query: CallbackQuery, settings_service: SettingsService) -> None:
    text, markup = await render_backup(settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    await query.answer()


@router.callback_query(BackupCb.filter(F.action == "now"))
async def backup_now(
    query: CallbackQuery, config: Settings, settings_service: SettingsService
) -> None:
    assert query.bot is not None
    ok = await _send_now(query.bot, config, settings_service)
    await query.answer(None if ok else texts.BACKUP_FAILED, show_alert=not ok)


@router.callback_query(BackupCb.filter(F.action == "weekly"))
async def toggle_weekly(query: CallbackQuery, settings_service: SettingsService) -> None:
    enabled = not await settings_service.backup_enabled()
    await settings_service.set_backup(enabled)
    text, markup = await render_backup(settings_service)
    if isinstance(query.message, Message):
        await _edit(query.message, text, markup)
    state = texts.BRIEFING_ON.format(time=f"{BACKUP_TIME:%H:%M}") if enabled else texts.BRIEFING_OFF
    await query.answer(texts.BACKUP_WEEKLY_CHANGED.format(state=state))


# --- Restore ---


def is_backup_file(document: Document | None) -> bool:
    if document is None:
        return False
    name_ok = bool(_BACKUP_NAME.search(document.file_name or ""))
    return name_ok or (document.mime_type or "") in _BACKUP_TYPES


async def _download(bot: Bot, file_id: str) -> bytes:
    buffer = await bot.download(file_id)
    assert buffer is not None
    return buffer.getvalue()


@router.message(F.document.func(is_backup_file))
async def got_backup(
    message: Message, state: FSMContext, config: Settings, settings_service: SettingsService
) -> None:
    document = message.document
    assert document is not None and message.bot is not None
    if document.file_size and document.file_size > MAX_UPLOAD:
        await message.answer(texts.RESTORE_TOO_BIG)
        return
    data = await _download(message.bot, document.file_id)
    try:
        info = await asyncio.to_thread(inspect_backup, data, known_revisions())
    except BackupError as exc:
        reply = (
            texts.RESTORE_NEWER if exc.newer else texts.RESTORE_INVALID.format(reason=exc.reason)
        )
        await message.answer(reply)
        return
    await state.set_state(BackupForm.confirm)
    await state.set_data({"restore_file": document.file_id})
    calendar = await settings_service.get_calendar()
    made = "—"
    if info.created is not None:
        made = f"{format_date(info.created.date(), calendar)}, {info.created:%H:%M}"
    await message.answer(
        texts.RESTORE_CHECK.format(date=made, counts=counts_text(info.counts)),
        reply_markup=restore_confirm(),
    )


@router.callback_query(BackupCb.filter(F.action == "restore"))
async def restore(
    query: CallbackQuery,
    state: FSMContext,
    config: Settings,
    settings_service: SettingsService,
    session: AsyncSession,
    llm: object,
) -> None:
    file_id = (await state.get_data()).get("restore_file")
    if await state.get_state() != BackupForm.confirm.state or not file_id:
        await query.answer(texts.RESTORE_EXPIRED, show_alert=True)
        return
    await state.clear()
    assert query.bot is not None
    data = await _download(query.bot, file_id)
    calendar = await settings_service.get_calendar()
    await session.commit()  # end this update's transaction before the database is replaced
    try:
        await send_backup(query.bot, config, calendar, caption=texts.BACKUP_BEFORE_RESTORE)
        info = await asyncio.to_thread(
            restore_backup, data, database_path(config.database_url), known_revisions()
        )
        await asyncio.to_thread(run_migrations, config.database_url)  # an older backup → today
    except BackupError as exc:
        await query.answer(texts.RESTORE_INVALID.format(reason=exc.reason), show_alert=True)
        return
    engine = session.bind
    await engine.dispose()  # type: ignore[union-attr]  # new connections see the restored data
    await _apply_saved_model(engine, config, llm)
    if isinstance(query.message, Message):
        await _edit(query.message, texts.RESTORE_DONE.format(counts=counts_text(info.counts)))
    await query.answer()


async def _apply_saved_model(engine, config: Settings, llm: object) -> None:
    """The restored settings may choose another AI model (🤖 AI model)."""
    from app.llm.providers import ProviderChain

    if not isinstance(llm, ProviderChain):
        return
    async with AsyncSession(engine) as session:
        saved = await SettingsService(session, config.default_calendar).get_ai_model()
    if saved:
        llm.prefer(*saved)
    else:
        llm.prefer(None)


@router.callback_query(BackupCb.filter(F.action == "cancel"))
async def cancel_restore(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(query.message, Message):
        await _edit(query.message, texts.RESTORE_CANCELLED)
    await query.answer()
