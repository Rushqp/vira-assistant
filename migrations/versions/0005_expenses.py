"""expenses, categories (with defaults) and learned category keywords

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CATEGORIES = [
    ("Groceries", "🛒"),
    ("Food", "🍞"),
    ("Restaurant", "🍽"),
    ("Home", "🏠"),
    ("Fuel", "⛽"),
    ("Transport", "🚕"),
    ("Bills", "🧾"),
    ("Health", "💊"),
    ("Clothing", "👕"),
    ("Education", "📚"),
    ("Gifts", "🎁"),
    ("Leisure", "🎉"),
    ("Other", "📦"),
]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False, unique=True),
        sa.Column("emoji", sa.String(length=8), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.bulk_insert(
        categories,
        [
            {"name": name, "emoji": emoji, "is_default": True, "position": i}
            for i, (name, emoji) in enumerate(DEFAULT_CATEGORIES)
        ],
    )
    op.create_table(
        "category_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=100), nullable=False, unique=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("spent_at", sa.DateTime(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])
    op.create_index("ix_expenses_spent_at", "expenses", ["spent_at"])


def downgrade() -> None:
    op.drop_index("ix_expenses_spent_at", table_name="expenses")
    op.drop_index("ix_expenses_category_id", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("category_keywords")
    op.drop_table("categories")
