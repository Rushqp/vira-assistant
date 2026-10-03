"""SQLAlchemy ORM models. Tables are added per version together with an Alembic migration.

All timestamps are stored as naive UTC datetimes.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    """Key/value store for user settings (calendar, report time, ...)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# --- Chat (v0.2) ---


class ChatSession(Base):
    """One conversation.

    The session with `ended_at IS NULL` is the active one. 💬 New Chat ends it and starts a new
    one; 🗂 Chats can re-open an older session (its `ended_at` is cleared again).
    """

    __tablename__ = "chat_sessions"
    __table_args__ = {"sqlite_autoincrement": True}  # never reuse ids of deleted chats

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(100), default=None)  # first question
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)  # last message
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class ChatHistory(Base):
    """Messages of a session. Only the last `CHAT_MEMORY` are sent to the model as context."""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
