"""💬 Chat: free text goes to built-in tools first, then to the LLM with short memory."""

import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from loguru import logger

from app import texts
from app.bot.keyboards.reply import main_menu
from app.bot.streaming import MessageStreamer
from app.config import Settings
from app.llm.client import LLMError
from app.services.chat import ChatService
from app.services.settings import SettingsService
from app.services.tools import answer_builtin
from app.utils.calendar import now_local

router = Router(name="chat")

# One generation at a time: a CPU-bound model can't serve two answers in parallel anyway,
# and it keeps the conversation history in order.
_generation_lock = asyncio.Lock()


@router.message(F.text == texts.BTN_NEW_CHAT)
@router.message(Command("new"))
async def new_chat(message: Message, chat_service: ChatService) -> None:
    await chat_service.new_session()
    await message.answer(texts.NEW_CHAT, reply_markup=main_menu())


@router.message(F.text & ~F.text.startswith("/"))
async def chat(
    message: Message,
    config: Settings,
    chat_service: ChatService,
    settings_service: SettingsService,
) -> None:
    question = (message.text or "").strip()

    calendar = await settings_service.get_calendar()
    if (builtin := answer_builtin(question, now_local(config.timezone), calendar)) is not None:
        await message.answer(builtin)
        return

    streamer = MessageStreamer(message)
    async with _generation_lock, ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        try:
            async for piece in chat_service.stream_answer(question):
                await streamer.push(piece)
        except LLMError as exc:
            logger.warning("LLM error: {}", exc)
            notice = texts.LLM_ERRORS[exc.kind].format(model=config.effective_llm_model)
            if streamer.started:
                await streamer.finish(f"\n\n{notice}")
            else:
                await message.answer(notice)
            return

    if streamer.text.strip():
        await streamer.finish()
    else:
        await message.answer(texts.LLM_EMPTY)
