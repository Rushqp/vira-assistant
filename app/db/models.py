"""SQLAlchemy ORM models. Tables are added per version together with an Alembic migration.

All timestamps are stored as naive UTC datetimes.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


# --- Reminders (v0.3) ---


class Reminder(Base):
    """Something to be reminded of.

    `event_at` is the (next) occurrence of the event. For repeating reminders it moves forward
    after each occurrence and the alerts are rebuilt from `alert_specs`.
    """

    __tablename__ = "reminders"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    event_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_rule: Mapped[str | None] = mapped_column(String(32), default=None)  # RepeatRule
    # Comma-separated alert specs relative to the event: at, before:15, day_before:22:00, ...
    alert_specs: Mapped[str] = mapped_column(String(255), default="at")
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    alerts: Mapped[list["ReminderAlert"]] = relationship(
        back_populates="reminder", cascade="all, delete-orphan", order_by="ReminderAlert.notify_at"
    )


class ReminderAlert(Base):
    """One notification of a reminder (a reminder can have several)."""

    __tablename__ = "reminder_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reminder_id: Mapped[int] = mapped_column(
        ForeignKey("reminders.id", ondelete="CASCADE"), index=True
    )
    notify_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # spec: generated from `alert_specs`; extra: one-off time or snooze (not repeated)
    kind: Mapped[str] = mapped_column(String(16), default="spec")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    reminder: Mapped[Reminder] = relationship(back_populates="alerts")
