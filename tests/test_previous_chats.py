"""🗂 Chats: titles, listing, resuming, deleting and the CHAT_KEEP limit."""

from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.db.models import ChatHistory, ChatSession
from app.services.chat import ChatService, make_title
from tests.fakes import FakeLLM

TEHRAN = ZoneInfo("Asia/Tehran")


def make_service(session, llm=None, keep=20) -> ChatService:
    return ChatService(session, llm or FakeLLM("ok"), 10, TEHRAN, keep=keep)  # type: ignore[arg-type]


async def ask(service: ChatService, question: str) -> None:
    async for _ in service.stream_answer(question):
        pass


async def start_chat(service: ChatService, *questions: str) -> ChatSession:
    await service.new_session()
    for q in questions:
        await ask(service, q)
    return await service.active_session()


def test_make_title():
    assert make_title("  How   do I cook\nrice? ") == "How do I cook rice?"
    long = make_title("x" * 100)
    assert len(long) == 40 and long.endswith("…")


async def test_title_is_first_question(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        chat = await start_chat(service, "Capital of France?", "And Italy?")
        assert chat.title == "Capital of France?"


async def test_list_is_most_recent_first_and_skips_empty_chats(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        a = await start_chat(service, "first chat")
        b = await start_chat(service, "second chat")
        await service.new_session()  # empty: not listed
        assert [c.id for c in await service.list_chats()] == [b.id, a.id]
        assert await service.count_chats() == 2

        await service.open_chat(a.id)
        await ask(service, "back to the first")
        assert [c.id for c in await service.list_chats()] == [a.id, b.id]


async def test_new_chat_reuses_an_empty_chat(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        first = await service.new_session()
        second = await service.new_session()
        assert first.id == second.id


async def test_open_chat_continues_it(sessionmaker):
    llm = FakeLLM("ok")
    async with sessionmaker() as session:
        service = make_service(session, llm)
        old = await start_chat(service, "My name is Sara")
        await start_chat(service, "unrelated")

        opened = await service.open_chat(old.id)
        assert opened is not None and opened.id == old.id
        assert (await service.active_session()).id == old.id

        await ask(service, "What's my name?")
    contents = [m["content"] for m in llm.calls[-1][1:]]
    assert contents == ["My name is Sara", "ok", "What's my name?"]


async def test_opening_from_an_empty_chat_removes_it(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        old = await start_chat(service, "hello")
        empty = await service.new_session()
        await service.open_chat(old.id)
        assert await service.get_chat(empty.id) is None


async def test_open_missing_chat(sessionmaker):
    async with sessionmaker() as session:
        assert await make_service(session).open_chat(999) is None


async def test_last_exchanges(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        chat = await start_chat(service, "q1", "q2", "q3", "q4")
        exchanges = await service.last_exchanges(chat.id, count=3)
        assert [(e.question, e.answer) for e in exchanges] == [
            ("q2", "ok"),
            ("q3", "ok"),
            ("q4", "ok"),
        ]


async def test_delete_chat(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session)
        chat = await start_chat(service, "to be deleted")
        await service.delete_chat(chat.id)
        assert await service.get_chat(chat.id) is None
        assert await session.scalar(select(func.count()).select_from(ChatHistory)) == 0
        # A new, empty active chat is created on demand, with a fresh id.
        new = await service.active_session()
        assert new.id != chat.id
        assert new.title is None


async def test_only_newest_chats_are_kept(sessionmaker):
    async with sessionmaker() as session:
        service = make_service(session, keep=3)
        for i in range(5):
            await start_chat(service, f"chat {i}")
        titles = [c.title for c in await service.list_chats()]
        assert titles == ["chat 4", "chat 3", "chat 2"]
        stored = await session.scalar(select(func.count()).select_from(ChatHistory))
        assert stored == 6  # 3 chats x (question + answer)
