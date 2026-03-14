"""OrgCreationInvitation model — invitation to create a new organization.

Created when a platform admin approves a SignupRequest. Consumed during
OAuth login: the user gets a new org with OWNER membership, then the
invitation row is deleted (matching the existing Invitation pattern).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class OrgCreationInvitation(Base):
    __tablename__ = "org_creation_invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    org_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signup_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signup_requests.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    signup_request = relationship("SignupRequest", foreign_keys=[signup_request_id])
    invited_by = relationship("User", foreign_keys=[invited_by_id])
