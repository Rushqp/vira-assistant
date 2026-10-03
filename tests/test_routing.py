"""End-to-end routing: real updates through the dispatcher with a fake Telegram session."""

from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, SendChatAction, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

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

    async def make_request(self, bot, method: TelegramMethod, timeout=None):  # noqa: ASYNC109
        if isinstance(method, SendMessage):
            self.sent.append(method.text)
            return _message(method.text, from_bot=True).as_(bot)
        if isinstance(method, EditMessageText):
            self.edits.append(method.text)
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

    yield send, session, llm


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
