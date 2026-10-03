"""💬 New Chat: start a fresh conversation (free text itself is handled in `assistant.py`)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app import texts
from app.bot.keyboards.reply import main_menu
from app.services.chat import ChatService

router = Router(name="chat")


@router.message(F.text == texts.BTN_NEW_CHAT)
@router.message(Command("new"))
async def new_chat(message: Message, chat_service: ChatService) -> None:
    await chat_service.new_session()
    await message.answer(texts.NEW_CHAT, reply_markup=main_menu())
