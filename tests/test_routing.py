"""End-to-end routing: real updates through the dispatcher with a fake Telegram session."""

from dataclasses import dataclass, field
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendChatAction,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User

from app import texts
from app.llm.client import LLMError
from app.main import build_dispatcher
from tests.conftest import OWNER_ID
from tests.fakes import FakeLLM


class RecordingSession(BaseSession):
    """Answers every Bot API call locally and records sent / edited texts."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[str] = []
        self.edits: list[str] = []
        self.markup: InlineKeyboardMarkup | None = None  # last inline keyboard shown
        self.alerts: list[str] = []  # callback answers

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
        if isinstance(method, AnswerCallbackQuery):
            if method.text:
                self.alerts.append(method.text)
            return True
        if isinstance(method, SendChatAction):
            return True
        raise NotImplementedError(type(method).__name__)

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield b""


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
    buttons: dict = field(default_factory=dict)

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


@pytest.fixture
async def env(config, sessionmaker):
    session = RecordingSession()
    bot = Bot(
        "123456:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    llm = FakeLLM("Hi! How can I help?")
    dp = build_dispatcher(config, sessionmaker, llm)  # type: ignore[arg-type]

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

    yield Env(send, press, session, llm)


async def test_free_text_goes_to_llm(env):
    send, session, llm = env
    await send("Hello Vira")
    assert len(llm.calls) == 1
    assert llm.calls[0][-1] == {"role": "user", "content": "Hello Vira"}
    shown = session.edits[-1] if session.edits else session.sent[-1]
    assert shown == "Hi! How can I help?"


async def test_calculator_skips_llm(env):
    send, session, llm = env
    await send("۱۲ × ۳۵۰۰۰۰")
    assert llm.calls == []
    assert "4,200,000" in session.sent[-1]


async def test_date_question_skips_llm(env):
    send, session, llm = env
    await send("امروز چندمه؟")
    assert llm.calls == []
    assert "امروز" in session.sent[-1]


async def test_new_chat_button_and_command(env):
    send, session, llm = env
    await send("first")
    await send(texts.BTN_NEW_CHAT)
    assert session.sent[-1] == texts.NEW_CHAT
    await send("second")
    assert [m["content"] for m in llm.calls[-1][1:]] == ["second"]
    await send("/new")
    assert session.sent[-1] == texts.NEW_CHAT


async def test_planned_buttons_and_commands_do_not_reach_llm(env):
    send, session, llm = env
    await send(texts.BTN_ADD_EXPENSE)
    await send("/backup")
    await send("/whatever")
    assert llm.calls == []
    assert "v0.4" in session.sent[0]
    assert "v0.7" in session.sent[1]
    assert session.sent[2] == texts.UNKNOWN_COMMAND


async def test_llm_failure_shows_notice(env):
    send, session, llm = env
    llm.answer, llm.error = "", LLMError("unreachable")
    await send("hello?")
    assert session.sent[-1] == texts.LLM_ERRORS["unreachable"]


async def test_strangers_are_ignored(env):
    send, session, llm = env
    await send("hi", user_id=999)
    assert session.sent == [] and llm.calls == []


async def test_previous_chats_flow(env):
    await env.send("My name is Sara")
    await env.send(texts.BTN_NEW_CHAT)
    await env.send("Second topic")

    await env.send(texts.BTN_CHATS)
    assert env.session.sent[-1].startswith("🗂 <b>Your chats</b> (2)")

    await env.press(env.button("My name is Sara"))
    recap = env.session.edits[-1]
    assert "Continuing: <b>My name is Sara</b>" in recap
    assert "🧑 My name is Sara" in recap

    await env.send("What's my name?")
    assert [m["content"] for m in env.llm.calls[-1][1:]] == [
        "My name is Sara",
        "Hi! How can I help?",
        "What's my name?",
    ]


async def test_delete_chat_flow(env):
    await env.send("Delete me")
    await env.send(texts.BTN_CHATS)
    await env.press(env.button("Delete me"))
    await env.press(env.button(texts.BTN_DELETE))
    assert "This can't be undone" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.CHAT_DELETED
    assert env.session.edits[-1] == texts.CHATS_EMPTY


async def test_chats_empty(env):
    await env.send("/chats")
    assert env.session.sent[-1] == texts.CHATS_EMPTY
