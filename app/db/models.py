"""SQLAlchemy ORM models. Tables are added per version together with an Alembic migration.

All timestamps are stored as naive UTC datetimes.
"""

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
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
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | done | cancelled
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


# --- Expenses (v0.4) ---


class Category(Base):
    """Expense category. Defaults are seeded by migration 0005; the user can add / remove."""

    __tablename__ = "categories"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    emoji: Mapped[str] = mapped_column(String(8), default="📦")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=100)


class CategoryKeyword(Base):
    """Learned from corrections: an expense description → the category the user picked."""

    __tablename__ = "category_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))


class Expense(Base):
    """One spending record. `amount` is a whole number in the configured CURRENCY."""

    __tablename__ = "expenses"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float | None] = mapped_column(Float, default=None)
    unit: Mapped[str | None] = mapped_column(String(16), default=None)
    spent_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    raw_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    category: Mapped[Category] = relationship(lazy="joined")


# --- Agent (v0.4) ---


class AgentAction(Base):
    """Something the assistant did, with what is needed to undo it (↩️ Undo survives restarts).

    kind: expenses_added | expenses_deleted | expense_updated | reminder_created |
          reminders_cancelled | reminder_updated | settings_updated | todos_added |
          todos_updated | todos_deleted | note_saved | note_updated | notes_deleted
    """

    __tablename__ = "agent_actions"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text)  # JSON
    summary: Mapped[str] = mapped_column(Text, default="")  # one line, shown to the model
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


# --- Notes and to-dos (v0.7) ---


class Note(Base):
    """A note. `tags` are words without "#", separated by spaces (e.g. "خرید ماشین")."""

    __tablename__ = "notes"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    text: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, default=None)  # long / voice notes
    tags: Mapped[str] = mapped_column(String(255), default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="text")  # text | voice
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Todo(Base):
    """A task for a day (`due_date`, local). Unfinished tasks of earlier days are shown in
    today's list until they are done ("carried over")."""

    __tablename__ = "todos"
    __table_args__ = {"sqlite_autoincrement": True}  # ids are used in buttons

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def done(self) -> bool:
        return self.done_at is not None
