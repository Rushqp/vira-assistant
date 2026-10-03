"""🗂 Chats: list previous conversations, continue one, or delete it."""

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import texts
from app.bot.keyboards.inline import (
    CHATS_PAGE_SIZE,
    ChatsCb,
    chat_delete_confirm,
    chat_opened,
    chats_list,
)
from app.config import Settings
from app.services.chat import ChatService
from app.services.settings import SettingsService
from app.utils.calendar import format_date, to_local

router = Router(name="chats")

RECAP_LENGTH = 300


def _shorten(text: str, limit: int = RECAP_LENGTH) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


async def _render_list(
    chat_service: ChatService, settings_service: SettingsService, config: Settings, page: int
):
    """Returns (text, keyboard) for a page of the chat list."""
    total = await chat_service.count_chats()
    if total == 0:
        return texts.CHATS_EMPTY, None
    page = min(page, (total - 1) // CHATS_PAGE_SIZE)
    chats = await chat_service.list_chats(page * CHATS_PAGE_SIZE, CHATS_PAGE_SIZE)
    calendar = await settings_service.get_calendar()
    current = await chat_service.active_session()
    items = []
    for chat in chats:
        day = format_date(
            to_local(chat.updated_at, config.timezone).date(), calendar, weekday=False
        )
        items.append((chat.id, f"{chat.title} · {day}"))
    return (
        texts.CHATS_TITLE.format(total=total),
        chats_list(items, page, total, current.id),
    )


@router.message(F.text == texts.BTN_CHATS)
@router.message(Command("chats"))
async def show_chats(
    message: Message,
    config: Settings,
    chat_service: ChatService,
    settings_service: SettingsService,
) -> None:
    text, keyboard = await _render_list(chat_service, settings_service, config, page=0)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(ChatsCb.filter(F.action == "page"))
async def chats_page(
    query: CallbackQuery,
    callback_data: ChatsCb,
    config: Settings,
    chat_service: ChatService,
    settings_service: SettingsService,
) -> None:
    text, keyboard = await _render_list(chat_service, settings_service, config, callback_data.page)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(ChatsCb.filter(F.action == "open"))
async def open_chat(
    query: CallbackQuery, callback_data: ChatsCb, chat_service: ChatService
) -> None:
    chat = await chat_service.open_chat(callback_data.chat_id)
    if chat is None:
        await query.answer(texts.CHAT_NOT_FOUND, show_alert=True)
        return

    lines = [texts.CHAT_RESUMED.format(title=html.escape(chat.title or "")), ""]
    for exchange in await chat_service.last_exchanges(chat.id, count=3):
        lines.append(
            texts.CHAT_RECAP_QUESTION.format(text=html.escape(_shorten(exchange.question)))
        )
        if exchange.answer:
            lines.append(
                texts.CHAT_RECAP_ANSWER.format(text=html.escape(_shorten(exchange.answer)))
            )
        lines.append("")
    lines.append(texts.CHAT_RESUMED_FOOTER)

    if isinstance(query.message, Message):
        await query.message.edit_text(
            "\n".join(lines), reply_markup=chat_opened(chat.id, callback_data.page)
        )
    await query.answer()


@router.callback_query(ChatsCb.filter(F.action == "delete"))
async def ask_delete(
    query: CallbackQuery, callback_data: ChatsCb, chat_service: ChatService
) -> None:
    chat = await chat_service.get_chat(callback_data.chat_id)
    if chat is None:
        await query.answer(texts.CHAT_NOT_FOUND, show_alert=True)
        return
    if isinstance(query.message, Message):
        await query.message.edit_text(
            texts.CHAT_DELETE_CONFIRM.format(title=html.escape(chat.title or "")),
            reply_markup=chat_delete_confirm(chat.id, callback_data.page),
        )
    await query.answer()


@router.callback_query(ChatsCb.filter(F.action == "confirm_delete"))
async def confirm_delete(
    query: CallbackQuery,
    callback_data: ChatsCb,
    config: Settings,
    chat_service: ChatService,
    settings_service: SettingsService,
) -> None:
    await chat_service.delete_chat(callback_data.chat_id)
    text, keyboard = await _render_list(chat_service, settings_service, config, callback_data.page)
    if isinstance(query.message, Message):
        await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer(texts.CHAT_DELETED)
