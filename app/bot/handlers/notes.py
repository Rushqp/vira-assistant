"""📝 Notes: the list (pinned first, newest next), a note in full, 📌 pin, ✏️ edit (the next
message goes to the agent) and 🗑 delete.

Saving and finding notes by talking («یادداشت کن …», «یادداشت‌های ماشین») is done by the
agent (`app/agent/tools/notes.py`).
"""

import html
import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import texts
from app.bot import views
from app.bot.keyboards.inline import NoteCb, note_delete_confirm, note_detail, notes_list
from app.bot.states import AgentForm
from app.config import Settings
from app.services.notes import NoteService
from app.services.settings import SettingsService

router = Router(name="notes")

PAGE_SIZE = 8


def note_label(note) -> str:
    return (texts.NOTE_PIN if note.pinned else "") + note.title


async def render_list(
    page: int, config: Settings, note_service: NoteService, settings_service: SettingsService
) -> tuple[str, InlineKeyboardMarkup | None]:
    calendar = await settings_service.get_calendar()
    total = await note_service.count()
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    page = min(max(page, 0), pages - 1)
    notes = await note_service.recent(PAGE_SIZE, page * PAGE_SIZE)
    text = views.notes_list(notes, total, config.timezone, calendar, first=page * PAGE_SIZE + 1)
    if not notes:
        return text, None
    return text, notes_list([(n.id, note_label(n)) for n in notes], page, pages)


async def _show(query: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    if not isinstance(query.message, Message):
        return
    try:
        await query.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.message(F.text == texts.BTN_NOTES)
async def show_notes(
    message: Message, config: Settings, note_service: NoteService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await render_list(0, config, note_service, settings_service)
    await message.answer(text, reply_markup=markup)


@router.callback_query(NoteCb.filter(F.action == "page"))
async def page(
    query: CallbackQuery, callback_data: NoteCb, config: Settings, note_service: NoteService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    text, markup = await render_list(callback_data.page, config, note_service, settings_service)
    await _show(query, text, markup)
    await query.answer()


@router.callback_query(NoteCb.filter(F.action.in_({"open", "pin"})))
async def open_note(
    query: CallbackQuery, callback_data: NoteCb, config: Settings, note_service: NoteService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    note = await note_service.get(callback_data.nid)
    if note is None:
        await query.answer(texts.NOTE_NOT_FOUND, show_alert=True)
        return
    toast = None
    if callback_data.action == "pin":
        changed = await note_service.update(note.id, pinned=not note.pinned)
        assert changed is not None
        note = changed[0]
        toast = texts.NOTE_PINNED if note.pinned else texts.NOTE_UNPINNED
    calendar = await settings_service.get_calendar()
    text = views.note_card(note, config.timezone, calendar)
    await _show(query, text, note_detail(note.id, note.pinned, callback_data.page))
    await query.answer(toast)


@router.callback_query(NoteCb.filter(F.action == "edit"))
async def edit_note(query: CallbackQuery, callback_data: NoteCb, state: FSMContext) -> None:
    await state.set_state(AgentForm.edit)
    await state.set_data({"edit_note": callback_data.nid})
    if isinstance(query.message, Message):
        await query.message.answer(texts.NOTE_EDIT_PROMPT)
    await query.answer()


@router.callback_query(NoteCb.filter(F.action == "delete"))
async def ask_delete(
    query: CallbackQuery, callback_data: NoteCb, note_service: NoteService
) -> None:
    note = await note_service.get(callback_data.nid)
    if note is None:
        await query.answer(texts.NOTE_NOT_FOUND, show_alert=True)
        return
    text = texts.NOTE_DELETE_CONFIRM.format(title=html.escape(note.title))
    await _show(query, text, note_delete_confirm(note.id, callback_data.page))
    await query.answer()


@router.callback_query(NoteCb.filter(F.action == "confirm_delete"))
async def confirm_delete(
    query: CallbackQuery, callback_data: NoteCb, config: Settings, note_service: NoteService,
    settings_service: SettingsService,
) -> None:  # fmt: skip
    await note_service.delete([callback_data.nid])
    text, markup = await render_list(callback_data.page, config, note_service, settings_service)
    await _show(query, text, markup)
    await query.answer(texts.NOTE_DELETED)
