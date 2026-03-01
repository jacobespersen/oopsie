"""initial_schema

Revision ID: 001
Revises:
Create Date: 2025-02-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("github_repo_url", sa.String(2048), nullable=False),
        sa.Column("github_token_encrypted", sa.String(2048), nullable=False),
        sa.Column(
            "default_branch",
            sa.String(64),
            nullable=False,
            server_default="main",
        ),
        sa.Column("error_threshold", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("api_key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "errors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("error_class", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_errors_fingerprint", "errors", ["fingerprint"], unique=False)
    op.create_index(
        "ix_errors_project_fingerprint",
        "errors",
        ["project_id", "fingerprint"],
        unique=True,
    )

    op.create_table(
        "fix_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "error_id",
            sa.Uuid(),
            sa.ForeignKey("errors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("pr_url", sa.String(2048), nullable=True),
        sa.Column("claude_output", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("fix_attempts")
    op.drop_index("ix_errors_project_fingerprint", table_name="errors")
    op.drop_index("ix_errors_fingerprint", table_name="errors")
    op.drop_table("errors")
    op.drop_table("projects")
