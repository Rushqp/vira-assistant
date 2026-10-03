"""chat titles and last activity, for the previous-chats list

The table is rebuilt with AUTOINCREMENT so ids of deleted chats are never reused
(an old "open chat" button must not open a different chat).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sqlite_autoincrement=True,
    )
    # Existing chats: title = first question, last activity = last message (or start time).
    op.execute(
        """
        INSERT INTO chat_sessions_new (id, title, started_at, updated_at, ended_at)
        SELECT
            s.id,
            (SELECT substr(h.content, 1, 100) FROM chat_history h
             WHERE h.session_id = s.id AND h.role = 'user' ORDER BY h.id LIMIT 1),
            s.started_at,
            coalesce((SELECT max(h.created_at) FROM chat_history h WHERE h.session_id = s.id),
                     s.started_at),
            s.ended_at
        FROM chat_sessions s
        """
    )
    # chat_history references chat_sessions: switch foreign keys off while swapping tables.
    op.execute("PRAGMA foreign_keys=OFF")
    op.drop_table("chat_sessions")
    op.rename_table("chat_sessions_new", "chat_sessions")
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("title")
