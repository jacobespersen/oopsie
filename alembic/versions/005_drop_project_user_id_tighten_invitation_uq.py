"""Drop project user_id column (projects now connect through org).

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
    op.drop_constraint("fk_projects_user_id", "projects", type_="foreignkey")
    op.drop_column("projects", "user_id")


def downgrade() -> None:
    # --- Projects: re-add user_id column ---
    op.add_column(
        "projects",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_user_id",
        "projects",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
