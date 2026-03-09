"""Membership model — joins User to Organization with a role."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class MemberRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"


# Ordered lowest → highest rank for comparison
_ROLE_ORDER: list[MemberRole] = [MemberRole.member, MemberRole.admin, MemberRole.owner]


def role_rank(role: MemberRole) -> int:
    """Return the numeric rank of a role (higher = more privileged)."""
    return _ROLE_ORDER.index(role)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="memberrole"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
