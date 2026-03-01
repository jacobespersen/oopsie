"""add error_occurrences

Revision ID: 002
Revises: 001
Create Date: 2025-02-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "error_id",
            sa.Uuid(),
            sa.ForeignKey("errors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_error_occurrences_error_id",
        "error_occurrences",
        ["error_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_error_occurrences_error_id", table_name="error_occurrences")
    op.drop_table("error_occurrences")
