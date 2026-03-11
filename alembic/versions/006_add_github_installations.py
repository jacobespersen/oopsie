"""Add github_installations table.

Revision ID: 006
Revises: 005
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_installations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("github_installation_id", sa.Integer(), nullable=False),
        sa.Column("github_account_login", sa.String(255), nullable=False),
        # Use String(32) per project convention — no sa.Enum
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_github_installation_org"),
    )
    op.create_index(
        "ix_github_installations_organization_id",
        "github_installations",
        ["organization_id"],
    )
    op.create_index(
        "ix_github_installations_github_installation_id",
        "github_installations",
        ["github_installation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_github_installations_github_installation_id",
        table_name="github_installations",
    )
    op.drop_index(
        "ix_github_installations_organization_id",
        table_name="github_installations",
    )
    op.drop_table("github_installations")
