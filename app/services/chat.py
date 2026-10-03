"""Q&A with the LLM using short-term memory, plus the list of previous chats.

- Each chat keeps up to `HISTORY_PER_CHAT` messages so it can be resumed later.
- Only the last `memory` (CHAT_MEMORY) messages are sent to the model as context.
- Only the newest `keep` (CHAT_KEEP) chats are stored; older ones are removed automatically.
"""

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Calendar
from app.db.models import ChatHistory, ChatSession, utcnow
from app.llm.client import ChatMessage, LanguageModel
from app.llm.prompts.chat import CHAT_SYSTEM_PROMPT
from app.utils.calendar import format_date

HISTORY_PER_CHAT = 100
TITLE_LENGTH = 40


@dataclass
class Exchange:
    question: str
    answer: str


def strip_notes(text: str) -> str:
    """Remove the agent's "[done: …]" / "[asked: …]" lines (kept only for the model)."""
    lines = [line for line in text.splitlines() if not re.match(r"^\[(?:done|asked):", line)]
    return "\n".join(lines).strip()


def make_title(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= TITLE_LENGTH else title[: TITLE_LENGTH - 1].rstrip() + "…"


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LanguageModel,
        memory: int,
        timezone: ZoneInfo,
        keep: int = 20,
    ) -> None:
        self.session = session
        self.llm = llm
        self.memory = memory
        self.timezone = timezone
        self.keep = keep

    # --- Active chat ---

    async def active_session(self) -> ChatSession:
        chat = await self.session.scalar(
            select(ChatSession)
            .where(ChatSession.ended_at.is_(None))
            .order_by(ChatSession.id.desc())
        )
        if chat is None:
            chat = ChatSession()
            self.session.add(chat)
            await self.session.commit()
        return chat

    async def new_session(self) -> ChatSession:
        """End the active chat and start a new one (an unused empty chat is simply reused)."""
        current = await self.active_session()
        if current.title is None:
            return current
        current.ended_at = utcnow()
        chat = ChatSession()
        self.session.add(chat)
        await self.session.commit()
        return chat

    # --- Previous chats ---

    async def count_chats(self) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(ChatSession).where(ChatSession.title.is_not(None))
            )
            or 0
        )

    async def list_chats(self, offset: int = 0, limit: int = 10) -> list[ChatSession]:
        """Chats that have at least one message, most recently used first."""
        rows = await self.session.scalars(
            select(ChatSession)
            .where(ChatSession.title.is_not(None))
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.all())

    async def get_chat(self, chat_id: int) -> ChatSession | None:
        return await self.session.get(ChatSession, chat_id)

    async def open_chat(self, chat_id: int) -> ChatSession | None:
        """Make `chat_id` the active chat so new messages continue it."""
        chat = await self.get_chat(chat_id)
        if chat is None or chat.title is None:
            return None
        current = await self.active_session()
        if current.id != chat.id:
            if current.title is None:
                await self.session.delete(current)  # empty chat: nothing to keep
            else:
                current.ended_at = utcnow()
            chat.ended_at = None
            await self.session.commit()
        return chat

    async def delete_chat(self, chat_id: int) -> None:
        await self.session.execute(delete(ChatHistory).where(ChatHistory.session_id == chat_id))
        await self.session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
        await self.session.commit()

    async def last_exchanges(self, chat_id: int, count: int = 3) -> list[Exchange]:
        rows = await self.session.scalars(
            select(ChatHistory)
            .where(ChatHistory.session_id == chat_id)
            .order_by(ChatHistory.id.desc())
            .limit(count * 2)
        )
        messages = list(reversed(rows.all()))
        exchanges: list[Exchange] = []
        for row in messages:
            if row.role == "user":
                exchanges.append(Exchange(question=row.content, answer=""))
            elif exchanges:
                exchanges[-1].answer = strip_notes(row.content)
        return exchanges[-count:]

    async def _prune_old_chats(self) -> None:
        old_ids = (
            select(ChatSession.id)
            .where(ChatSession.title.is_not(None))
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .offset(self.keep)
        )
        ids = list((await self.session.scalars(old_ids)).all())
        if ids:
            await self.session.execute(delete(ChatHistory).where(ChatHistory.session_id.in_(ids)))
            await self.session.execute(delete(ChatSession).where(ChatSession.id.in_(ids)))

    # --- Memory ---

    async def history(self, session_id: int) -> list[ChatHistory]:
        if self.memory == 0:
            return []
        rows = await self.session.scalars(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.id.desc())
            .limit(self.memory)
        )
        return list(reversed(rows.all()))

    async def remember(self, session_id: int, question: str, answer: str) -> None:
        """Store the exchange, update the chat's title / activity and apply the size limits."""
        self.session.add_all(
            [
                ChatHistory(session_id=session_id, role="user", content=question),
                ChatHistory(session_id=session_id, role="assistant", content=answer),
            ]
        )
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(
                updated_at=utcnow(),
                title=func.coalesce(ChatSession.title, make_title(question)),
            )
        )
        await self.session.flush()
        keep = (
            select(ChatHistory.id)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.id.desc())
            .limit(HISTORY_PER_CHAT)
        )
        await self.session.execute(
            delete(ChatHistory).where(
                ChatHistory.session_id == session_id, ChatHistory.id.not_in(keep)
            )
        )
        await self._prune_old_chats()
        await self.session.commit()

    async def add_note(self, note: str) -> None:
        """Add an assistant line (e.g. "[done: …]" after a button press) to the active chat."""
        if not note:
            return
        chat = await self.active_session()
        self.session.add(ChatHistory(session_id=chat.id, role="assistant", content=note))
        await self.session.commit()

    # --- Answering ---

    def system_prompt(self, now: datetime) -> str:
        return CHAT_SYSTEM_PROMPT.format(
            today_gregorian=format_date(now.date(), Calendar.GREGORIAN),
            today_jalali=format_date(now.date(), Calendar.JALALI),
            time=f"{now:%H:%M}",
            timezone=self.timezone.key,
        )

    async def build_messages(self, session_id: int, question: str) -> list[ChatMessage]:
        now = datetime.now(self.timezone)
        messages: list[ChatMessage] = [{"role": "system", "content": self.system_prompt(now)}]
        for row in await self.history(session_id):
            messages.append({"role": row.role, "content": row.content})  # type: ignore[typeddict-item]
        messages.append({"role": "user", "content": question})
        return messages

    async def stream_answer(self, question: str) -> AsyncIterator[str]:
        """Yield the answer as it is generated; the exchange is saved once it completes.

        Raises `LLMError` if the model fails; nothing is saved in that case.
        """
        chat = await self.active_session()
        messages = await self.build_messages(chat.id, question)
        parts: list[str] = []
        async for piece in self.llm.stream_chat(messages):
            parts.append(piece)
            yield piece
        answer = "".join(parts).strip()
        if answer:
            await self.remember(chat.id, question, answer)
