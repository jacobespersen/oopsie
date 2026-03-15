"""Add unique constraint on org_creation_invitations.signup_request_id and
CHECK constraint on signup_requests review fields.

Revision ID: 010
Revises: 009
Create Date: 2026-03-15
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_org_creation_invitations_signup_request_id",
        "org_creation_invitations",
        ["signup_request_id"],
    )
    op.create_check_constraint(
        "ck_signup_requests_review_fields_match_status",
        "signup_requests",
        (
            "(status = 'pending' AND reviewed_by_id IS NULL AND reviewed_at IS NULL) "
            "OR "
            "(status != 'pending' AND reviewed_by_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_signup_requests_review_fields_match_status",
        "signup_requests",
        type_="check",
    )
    op.drop_constraint(
        "uq_org_creation_invitations_signup_request_id",
        "org_creation_invitations",
        type_="unique",
    )
