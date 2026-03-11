"""make github_account_login nullable and use enum types

Revision ID: fc31076df9ee
Revises: 007
Create Date: 2026-03-11 22:33:07.703574

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc31076df9ee"
down_revision: str | Sequence[str] | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "github_installations",
        "github_account_login",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "github_installations",
        "github_account_login",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
