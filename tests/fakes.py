"""Test doubles shared across test modules: fake LLM, fake speech engine and a fake Telegram
Bot API session."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    GetFile,
    SendChatAction,
    SendDocument,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    Audio,
    CallbackQuery,
    Chat,
    Document,
    File,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
    Voice,
)

from app.llm.client import ChatMessage, LLMError, LLMResponse, ToolCall
from app.llm.failover import Failover
from app.stt.engines import Transcription

OWNER_ID = 1001


def tool(name: str, **arguments) -> ToolCall:
    """A tool call as a model would return it."""
    return ToolCall(id=f"call_{name}_{len(arguments)}", name=name, arguments=json.dumps(arguments))


def calls(*tool_calls: ToolCall, text: str = "") -> LLMResponse:
    return LLMResponse(content=text, tool_calls=list(tool_calls), provider="fake")


def reply(text: str) -> LLMResponse:
    return LLMResponse(content=text, provider="fake")


class FakeLLM:
    """Streams a canned answer and records the messages it was called with.

    Agent turns (`respond`) follow `script`, a list of `LLMResponse`s (or callables taking the
    messages and returning one). With an empty script, `respond` acts like "no tool-capable
    model reachable", so the bot uses its rule-based fallback.
    """

    def __init__(self, answer: str = "Hello there!", error: LLMError | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[list[ChatMessage]] = []
        self.json_reply: dict | None = None  # None: structured output fails (model offline)
        self.json_calls: list[list[ChatMessage]] = []
        self.script: list = []
        self.respond_calls: list[list[ChatMessage]] = []
        self.model = "fake"
        self.streams = False  # like an API provider: the text arrives in one piece

    async def respond(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        on_text=None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        self.respond_calls.append([dict(m) for m in messages])
        if not self.script:
            raise LLMError("unreachable", "no scripted response")
        step = self.script.pop(0)
        if callable(step):
            step = step(messages)
        if step.content and on_text and self.streams:
            await on_text(step.content)
        return step

    async def stream_chat(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(messages)
        for word in self.answer.split(" "):
            yield word + " "
        if self.error:
            raise self.error

    async def complete_json(
        self, messages: list[ChatMessage], schema: dict, name: str = ""
    ) -> dict:
        self.json_calls.append(messages)
        if self.json_reply is None:
            raise LLMError("unreachable")
        return self.json_reply


class FakeSTT:
    """Stands in for `SpeechChain`: answers `text` (or raises `error`) and records the audio."""

    def __init__(self, text: str = "", error: LLMError | None = None) -> None:
        self.text = text
        self.error = error
        self.engines = ["fake"]
        self.audio: list = []
        self.failover = Failover(task="voice")

    @property
    def model(self) -> str:
        return "Fake Whisper"

    async def transcribe(self, audio) -> Transcription:
        self.audio.append(audio)
        if self.error:
            raise self.error
        return Transcription(self.text, "fa", "Fake Whisper")

    def drain_notices(self):
        return self.failover.drain()

    async def close(self) -> None:
        pass


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and records sent / edited texts."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[str] = []
        self.edits: list[str] = []
        self.markup: InlineKeyboardMarkup | None = None  # last inline keyboard shown
        self.alerts: list[str] = []  # callback answers
        self.documents: list[tuple[str, bytes, str]] = []  # (file name, content, caption)
        self.downloads: list[str] = []  # file ids the bot downloaded

    async def make_request(self, bot, method: TelegramMethod, timeout=None):  # noqa: ASYNC109
        if isinstance(method, SendMessage):
            self.sent.append(method.text)
            if isinstance(method.reply_markup, InlineKeyboardMarkup):
                self.markup = method.reply_markup
            return _message(method.text, from_bot=True).as_(bot)
        if isinstance(method, EditMessageText):
            self.edits.append(method.text)
            self.markup = method.reply_markup
            return True
        if isinstance(method, EditMessageReplyMarkup):
            self.markup = method.reply_markup
            return True
        if isinstance(method, AnswerCallbackQuery):
            if method.text:
                self.alerts.append(method.text)
            return True
        if isinstance(method, SendChatAction):
            return True
        if isinstance(method, GetFile):
            self.downloads.append(method.file_id)
            return File(file_id=method.file_id, file_unique_id="u", file_path="voice/file.oga")
        if isinstance(method, SendDocument):
            document = method.document
            self.documents.append(
                (document.filename, document.data, method.caption or "")  # type: ignore[union-attr]
            )
            return _message("(document)", from_bot=True).as_(bot)
        raise NotImplementedError(type(method).__name__)

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):
        yield b"fake-ogg-audio"


_counter = iter(range(1, 10_000))


def _message(text: str, *, from_bot: bool = False, user_id: int = OWNER_ID) -> Message:
    user = User(id=1 if from_bot else user_id, is_bot=from_bot, first_name="T")
    return Message(
        message_id=next(_counter),
        date=datetime.now(),
        chat=Chat(id=user_id, type="private"),
        from_user=user,
        text=text,
    )


@dataclass
class Env:
    send: object
    press: object
    session: RecordingSession
    llm: FakeLLM
    db: object = None  # sessionmaker, for checking the database
    feed: object = None  # feed(message): any Message (voice, audio …) through the dispatcher
    stt: object = None

    def __iter__(self):
        return iter((self.send, self.session, self.llm))

    def button(self, text_part: str) -> str:
        """callback_data of the first button in the last inline keyboard containing `text_part`."""
        assert self.session.markup is not None, "no inline keyboard shown"
        for row in self.session.markup.inline_keyboard:
            for b in row:
                if text_part in b.text:
                    return b.callback_data or ""
        raise AssertionError(f"no button with {text_part!r}")


def voice_message(
    duration: int = 3, kind: str = "voice", caption: str | None = None, size: int = 9000
) -> Message:
    """A voice message, an audio file ("audio") or an audio sent as a file ("document")."""
    media: dict = {}
    if kind == "voice":
        media["voice"] = Voice(
            file_id="voice-1", file_unique_id="v1", duration=duration, mime_type="audio/ogg",
            file_size=size,
        )  # fmt: skip
    elif kind == "audio":
        media["audio"] = Audio(
            file_id="audio-1", file_unique_id="a1", duration=duration, mime_type="audio/mpeg",
            file_name="memo.mp3", file_size=size,
        )  # fmt: skip
    else:
        media["document"] = Document(
            file_id="doc-1", file_unique_id="d1", mime_type="audio/mp4", file_name="memo.m4a",
            file_size=size,
        )  # fmt: skip
    return Message(
        message_id=next(_counter),
        date=datetime.now(),
        chat=Chat(id=OWNER_ID, type="private"),
        from_user=User(id=OWNER_ID, is_bot=False, first_name="T"),
        caption=caption,
        **media,
    )


def make_env(config, sessionmaker, llm=None, stt=None) -> Env:
    """A dispatcher wired to a recording fake Telegram session and a fake LLM (or `llm`)."""
    from app.main import build_dispatcher

    session = RecordingSession()
    bot = Bot(
        "123456:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    llm = llm or FakeLLM("Hi! How can I help?")
    dp = build_dispatcher(config, sessionmaker, llm, stt)  # type: ignore[arg-type]

    async def feed(message: Message) -> None:
        await dp.feed_update(bot, Update(update_id=next(_counter), message=message))

    async def send(text: str, user_id: int = OWNER_ID) -> None:
        update = Update(update_id=next(_counter), message=_message(text, user_id=user_id))
        await dp.feed_update(bot, update)

    async def press(data: str) -> None:
        query = CallbackQuery(
            id=str(next(_counter)),
            from_user=User(id=OWNER_ID, is_bot=False, first_name="T"),
            chat_instance="x",
            message=_message("(bot message)", from_bot=True),
            data=data,
        )
        await dp.feed_update(bot, Update(update_id=next(_counter), callback_query=query))

    return Env(send, press, session, llm, sessionmaker, feed, stt)
