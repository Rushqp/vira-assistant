"""notes and to-dos

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(length=255), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "todos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_todos_due_date", "todos", ["due_date"])


def downgrade() -> None:
    op.drop_index("ix_todos_due_date", table_name="todos")
    op.drop_table("todos")
    op.drop_table("notes")
