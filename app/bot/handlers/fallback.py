"""Catch-all for anything no other handler took: unknown commands, voice, media."""

from aiogram import F, Router
from aiogram.types import Message

from app import texts
from app.bot.keyboards.reply import main_menu

router = Router(name="fallback")


@router.message(F.voice | F.audio)
async def voice_not_ready(message: Message) -> None:
    await message.answer(texts.COMING_SOON.format(feature="Voice messages", version="v0.6"))


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND, reply_markup=main_menu())


@router.message()
async def unsupported(message: Message) -> None:
    await message.answer(texts.UNSUPPORTED_MESSAGE, reply_markup=main_menu())
