"""reminders and their alerts

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("repeat_rule", sa.String(length=32), nullable=True),
        sa.Column("alert_specs", sa.String(length=255), nullable=False),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_reminders_event_at", "reminders", ["event_at"])
    op.create_table(
        "reminder_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "reminder_id",
            sa.Integer(),
            sa.ForeignKey("reminders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notify_at", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_reminder_alerts_reminder_id", "reminder_alerts", ["reminder_id"])
    op.create_index("ix_reminder_alerts_notify_at", "reminder_alerts", ["notify_at"])


def downgrade() -> None:
    op.drop_index("ix_reminder_alerts_notify_at", table_name="reminder_alerts")
    op.drop_index("ix_reminder_alerts_reminder_id", table_name="reminder_alerts")
    op.drop_table("reminder_alerts")
    op.drop_index("ix_reminders_event_at", table_name="reminders")
    op.drop_table("reminders")
