"""Q&A with the LLM using short-term memory (the last `CHAT_MEMORY` messages of the session)."""

from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Calendar
from app.db.models import ChatHistory, ChatSession, utcnow
from app.llm.client import ChatMessage, LLMClient
from app.llm.prompts.chat import CHAT_SYSTEM_PROMPT
from app.utils.calendar import format_date


class ChatService:
    def __init__(
        self, session: AsyncSession, llm: LLMClient, memory: int, timezone: ZoneInfo
    ) -> None:
        self.session = session
        self.llm = llm
        self.memory = memory
        self.timezone = timezone

    # --- Sessions ---

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
        """End the active session, drop old messages and start fresh."""
        current = await self.active_session()
        current.ended_at = utcnow()
        await self.session.execute(delete(ChatHistory))
        chat = ChatSession()
        self.session.add(chat)
        await self.session.commit()
        return chat

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
        """Store the exchange and keep only the last `memory` messages of the session."""
        self.session.add_all(
            [
                ChatHistory(session_id=session_id, role="user", content=question),
                ChatHistory(session_id=session_id, role="assistant", content=answer),
            ]
        )
        await self.session.flush()
        keep = (
            select(ChatHistory.id)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.id.desc())
            .limit(self.memory)
        )
        await self.session.execute(
            delete(ChatHistory).where(
                ChatHistory.session_id == session_id, ChatHistory.id.not_in(keep)
            )
        )
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
