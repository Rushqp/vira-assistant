"""Voice messages and audio files become text messages before routing.

Registered as an *outer* message middleware, so filters and handlers see the transcript as if
it had been typed: the agent, forms waiting for an answer, everything works the same. The
recognized text is shown first («🎙 …»), so a mistake is visible right away.
"""

import html
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, TelegramObject
from aiogram.utils.chat_action import ChatActionSender
from loguru import logger

from app import texts
from app.config import Settings
from app.llm.client import LLMError
from app.stt.engines import Audio

MAX_SECONDS = 600  # longer recordings are refused (free API quotas, CPU time)
MAX_BYTES = 20 * 1024 * 1024  # bots can't download bigger files
SHOWN_CHARS = 1500  # of the transcript, in the «🎙 …» message


@dataclass
class Media:
    file_id: str
    filename: str
    mime: str
    duration: int | None
    size: int | None


def media_of(message: Message) -> Media | None:
    """The voice message or audio file in a message, if any (round videos are not transcribed)."""
    if voice := message.voice:
        return Media(
            voice.file_id, "voice.ogg", voice.mime_type or "audio/ogg", voice.duration,
            voice.file_size,
        )  # fmt: skip
    if audio := message.audio:
        return Media(
            audio.file_id, audio.file_name or "audio.mp3", audio.mime_type or "audio/mpeg",
            audio.duration, audio.file_size,
        )  # fmt: skip
    document = message.document
    if document and (document.mime_type or "").startswith("audio/"):
        return Media(
            document.file_id, document.file_name or "audio", document.mime_type or "audio/mpeg",
            None, document.file_size,
        )  # fmt: skip
    return None


async def transcribe(message: Message, media: Media, data: dict[str, Any]) -> str | None:
    """The text to handle, or None after telling the user why there is none."""
    config: Settings = data["config"]
    stt = data.get("stt")
    if not config.stt_enabled:
        await message.answer(texts.VOICE_OFF)
        return None
    if stt is None or not stt.engines:
        await message.answer(texts.VOICE_NO_ENGINE)
        return None
    if media.duration and media.duration > MAX_SECONDS:
        await message.answer(
            texts.VOICE_TOO_LONG.format(minutes=round(media.duration / 60), limit=MAX_SECONDS // 60)
        )
        return None
    if media.size and media.size > MAX_BYTES:
        await message.answer(texts.VOICE_TOO_BIG)
        return None
    bot = message.bot
    assert bot is not None
    async with ChatActionSender.typing(chat_id=message.chat.id, bot=bot):
        try:
            buffer = await bot.download(media.file_id)
            assert buffer is not None
            result = await stt.transcribe(
                Audio(buffer.getvalue(), media.filename, media.mime, media.duration)
            )
        except (LLMError, TelegramAPIError) as exc:
            logger.warning("Voice message not transcribed: {}", exc)
            await message.answer(texts.VOICE_FAILED)
            return None
        except Exception:  # e.g. the download broke off: the user still gets an answer
            logger.exception("Voice message not transcribed")
            await message.answer(texts.VOICE_FAILED)
            return None
    if not result.text:
        await message.answer(texts.VOICE_EMPTY)
        return None
    shown = result.text if len(result.text) <= SHOWN_CHARS else result.text[:SHOWN_CHARS] + "…"
    await message.answer(texts.VOICE_HEARD.format(text=html.escape(shown)))
    caption = (message.caption or "").strip()
    return f"{caption}\n{result.text}" if caption else result.text


class VoiceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        media = media_of(event) if isinstance(event, Message) else None
        if media is None:
            return await handler(event, data)
        text = await transcribe(event, media, data)  # type: ignore[arg-type]
        if text is None:
            return None
        typed = event.model_copy(
            update={"text": text, "voice": None, "audio": None, "document": None, "caption": None}
        )
        data["voice_seconds"] = media.duration or 0  # the agent is told it came from speech
        return await handler(typed.as_(event.bot), data)
