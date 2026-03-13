"""drop revoked_tokens table

Revision ID: 2f23da1ebac2
Revises: 008
Create Date: 2026-03-14 00:14:19.805030

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2f23da1ebac2"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the revoked_tokens table (token revocation now handled via Redis)."""
    op.drop_index(op.f("ix_revoked_tokens_jti"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")


def downgrade() -> None:
    """Recreate the revoked_tokens table."""
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("jti", sa.VARCHAR(length=64), autoincrement=False, nullable=False),
        sa.Column(
            "expires_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("revoked_tokens_pkey")),
    )
    op.create_index(
        op.f("ix_revoked_tokens_jti"), "revoked_tokens", ["jti"], unique=True
    )
