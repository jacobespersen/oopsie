"""Document addition of MERGED status to FixAttemptStatus.

The status column uses String(32) so adding a new enum value requires no
DDL change — the column already stores arbitrary strings. This migration
exists as a changepoint marker so reviewers can see when the value was
introduced.

Revision ID: 008
Revises: 007
Create Date: 2026-03-11

"""

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No DDL required — status is String(32), not a Postgres ENUM type.
    # FixAttemptStatus.MERGED = "merged" is now a valid application-level value.
    pass


def downgrade() -> None:
    # No DDL to reverse.
    # Any rows with status="merged" would need to be manually updated before
    # rolling back to a code version that does not know about MERGED.
    pass
