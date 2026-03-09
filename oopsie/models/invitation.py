"""Invitation model — pending membership for an email address.

An invitation exists only while it is pending.  Once accepted, the row is
deleted and the corresponding Membership becomes the source of truth.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base
from oopsie.models.membership import MemberRole


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "email",
            name="uq_invitation_org_email",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="memberrole"),
        nullable=False,
    )
    # Nullable: bootstrap invitations have no inviter
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization = relationship("Organization", back_populates="invitations")
    invited_by = relationship("User", foreign_keys=[invited_by_id])
