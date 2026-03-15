"""Add unique constraint on memberships.user_id to enforce single org per user.

Revision ID: 011
Revises: 010
Create Date: 2026-03-15
"""

from alembic import op
from sqlalchemy import text

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safety net: assert no user has multiple memberships before adding constraint.
    # There are no production multi-org users, so this should always pass.
    conn = op.get_bind()
    result = conn.execute(
        text(
            "SELECT user_id, COUNT(*) as cnt "
            "FROM memberships GROUP BY user_id HAVING COUNT(*) > 1"
        )
    )
    violations = result.fetchall()
    if violations:
        raise RuntimeError(
            f"Cannot add single-org constraint: {len(violations)} user(s) have "
            "multiple memberships. Manual cleanup required before migration."
        )

    op.create_unique_constraint("uq_membership_user", "memberships", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_membership_user", "memberships", type_="unique")
