"""Drop project user_id column and tighten invitation unique constraint.

Revision ID: 005
Revises: 004
Create Date: 2026-03-07
"""

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Projects: remove vestigial user_id (projects now connect through org) ---
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_constraint(
        "projects_user_id_fkey", "projects", type_="foreignkey"
    )
    op.drop_column("projects", "user_id")

    # --- Invitations: tighten unique constraint to (org, email) ---
    op.drop_constraint(
        "uq_invitation_org_email_status", "invitations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_invitation_org_email", "invitations", ["organization_id", "email"]
    )


def downgrade() -> None:
    # --- Invitations: restore original (org, email, status) constraint ---
    op.drop_constraint(
        "uq_invitation_org_email", "invitations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_invitation_org_email_status",
        "invitations",
        ["organization_id", "email", "status"],
    )

    # --- Projects: re-add user_id column ---
    op.add_column(
        "projects",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "projects_user_id_fkey",
        "projects",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
