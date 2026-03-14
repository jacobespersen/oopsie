"""SignupRequest model — public signup request for org creation.

A signup request captures interest from potential users who want to create
a new organization. Platform admins review and approve/reject requests.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class SignupRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SignupRequest(Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        # Only one pending request per email — allow resubmission after rejection
        Index(
            "ix_signup_requests_email_pending",
            "email",
            unique=True,
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    org_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SignupRequestStatus] = mapped_column(
        Enum(SignupRequestStatus, name="signuprequeststatus"),
        nullable=False,
        default=SignupRequestStatus.pending,
        server_default="pending",
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
