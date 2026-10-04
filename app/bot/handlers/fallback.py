"""Catch-all for anything no other handler took: unknown commands and media.

Voice messages and audio files never get here: they are turned into text before routing
(`app/bot/middlewares/voice.py`).
"""

from aiogram import F, Router
from aiogram.types import Message

from app import texts
from app.bot.keyboards.reply import main_menu

router = Router(name="fallback")


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND, reply_markup=main_menu())


@router.message()
async def unsupported(message: Message) -> None:
    await message.answer(texts.UNSUPPORTED_MESSAGE, reply_markup=main_menu())
