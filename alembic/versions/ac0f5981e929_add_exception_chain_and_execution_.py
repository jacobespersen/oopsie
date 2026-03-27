"""add exception_chain and execution_context to error_occurrences

Revision ID: ac0f5981e929
Revises: 011
Create Date: 2026-03-26 20:23:49.060090

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ac0f5981e929"
down_revision: str | Sequence[str] | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "error_occurrences",
        sa.Column(
            "exception_chain",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "error_occurrences",
        sa.Column(
            "execution_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.drop_index(op.f("ix_error_occurrences_error_id"), table_name="error_occurrences")
    op.create_index(
        "ix_error_occurrences_error_id_occurred_at",
        "error_occurrences",
        ["error_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_error_occurrences_error_id_occurred_at", table_name="error_occurrences"
    )
    op.create_index(
        op.f("ix_error_occurrences_error_id"),
        "error_occurrences",
        ["error_id"],
        unique=False,
    )
    op.drop_column("error_occurrences", "execution_context")
    op.drop_column("error_occurrences", "exception_chain")
