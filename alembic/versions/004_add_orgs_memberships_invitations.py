"""Add organizations, memberships, invitations tables and organization_id on projects.

Revision ID: 004
Revises: 003
Create Date: 2026-03-06
"""

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE memberrole AS ENUM ('owner', 'admin', 'member')")

    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # memberships
    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "member", name="memberrole", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_membership_org_user"
        ),
    )
    op.create_index(
        "ix_memberships_organization_id", "memberships", ["organization_id"]
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    # invitations
    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "member", name="memberrole", create_type=False),
            nullable=False,
        ),
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", name="uq_invitation_org_email"),
    )
    op.create_index(
        "ix_invitations_organization_id", "invitations", ["organization_id"]
    )
    op.create_index("ix_invitations_email", "invitations", ["email"])

    # Add organization_id FK to projects
    op.add_column(
        "projects",
        sa.Column("organization_id", sa.UUID(), nullable=False),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_foreign_key(
        "fk_projects_organization_id",
        "projects",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_organization_id", "projects", type_="foreignkey")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_column("projects", "organization_id")

    op.drop_table("invitations")
    op.drop_table("memberships")
    op.drop_table("organizations")

    sa.Enum(name="memberrole").drop(op.get_bind(), checkfirst=True)
