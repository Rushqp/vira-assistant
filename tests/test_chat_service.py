from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.db.models import ChatHistory, ChatSession
from app.llm.client import LLMError
from app.services.chat import ChatService
from tests.fakes import FakeLLM

TEHRAN = ZoneInfo("Asia/Tehran")


def make_service(session, llm, memory=10) -> ChatService:
    return ChatService(session, llm, memory, TEHRAN)  # type: ignore[arg-type]


async def collect(service: ChatService, question: str) -> str:
    return "".join([piece async for piece in service.stream_answer(question)])


async def test_answer_is_streamed_and_saved(sessionmaker):
    llm = FakeLLM("Tehran is the capital.")
    async with sessionmaker() as session:
        service = make_service(session, llm)
        answer = await collect(service, "Capital of Iran?")
        assert answer.strip() == "Tehran is the capital."

        chat = await service.active_session()
        history = await service.history(chat.id)
        assert [(h.role, h.content) for h in history] == [
            ("user", "Capital of Iran?"),
            ("assistant", "Tehran is the capital."),
        ]


async def test_history_is_sent_as_context(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        service = make_service(session, llm)
        await collect(service, "My name is Sara")
        await collect(service, "What's my name?")

    messages = llm.calls[-1]
    assert messages[0]["role"] == "system"
    assert [m["content"] for m in messages[1:]] == ["My name is Sara", "ok", "What's my name?"]


async def test_system_prompt_contains_both_calendars(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        await collect(make_service(session, llm), "hi")
    system = llm.calls[0][0]["content"]
    assert "Jalali:" in system
    assert "Asia/Tehran" in system


async def test_only_recent_messages_are_sent_as_context(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        service = make_service(session, llm, memory=4)
        for i in range(5):
            await collect(service, f"q{i}")
        # Everything is kept for resuming the chat later...
        count = await session.scalar(select(func.count()).select_from(ChatHistory))
        assert count == 10
        # ...but only the last `memory` messages go to the model.
        chat = await service.active_session()
        assert [h.content for h in await service.history(chat.id)] == ["q3", "ok", "q4", "ok"]


async def test_history_per_chat_is_capped(sessionmaker, monkeypatch):
    monkeypatch.setattr("app.services.chat.HISTORY_PER_CHAT", 6)
    async with sessionmaker() as session:
        service = make_service(session, FakeLLM("ok"))
        for i in range(5):
            await collect(service, f"q{i}")
        assert await session.scalar(select(func.count()).select_from(ChatHistory)) == 6


async def test_new_session_clears_context(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        service = make_service(session, llm)
        await collect(service, "remember this")
        first = await service.active_session()

        second = await service.new_session()
        assert second.id != first.id
        assert first.ended_at is not None
        assert await service.history(second.id) == []

        await collect(service, "fresh question")
    assert [m["content"] for m in llm.calls[-1][1:]] == ["fresh question"]


async def test_failed_answer_is_not_saved(sessionmaker):
    llm = FakeLLM("partial", error=LLMError("unreachable"))
    async with sessionmaker() as session:
        service = make_service(session, llm)
        with pytest.raises(LLMError):
            await collect(service, "hello?")
        assert await session.scalar(select(func.count()).select_from(ChatHistory)) == 0


async def test_zero_memory_sends_no_history(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        service = make_service(session, llm, memory=0)
        await collect(service, "one")
        await collect(service, "two")
    assert len(llm.calls[-1]) == 2  # system + current question


async def test_only_one_active_session(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session, FakeLLM())
        await service.active_session()
        await service.new_session()
        await service.new_session()
        active = await session.scalar(
            select(func.count()).select_from(ChatSession).where(ChatSession.ended_at.is_(None))
        )
        assert active == 1
