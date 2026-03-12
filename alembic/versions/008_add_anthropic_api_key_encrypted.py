"""Add anthropic_api_key_encrypted to organizations and projects.

Revision ID: 008
Revises: fc31076df9ee
Create Date: 2026-03-12

"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "fc31076df9ee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "anthropic_api_key_encrypted")
    op.drop_column("organizations", "anthropic_api_key_encrypted")
