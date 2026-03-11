"""Drop github_token_encrypted from projects table.

Auth now uses GitHub App installation access tokens (Phase 4);
per-project PATs are no longer stored.

Revision ID: 007
Revises: 006
Create Date: 2026-03-11

"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("projects", "github_token_encrypted")


def downgrade() -> None:
    # Nullable because existing rows have no token value to restore.
    op.add_column(
        "projects",
        sa.Column(
            "github_token_encrypted",
            sa.String(2048),
            nullable=True,
        ),
    )
