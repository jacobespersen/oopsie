"""GithubInstallation model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class InstallationStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class GithubInstallation(Base):
    __tablename__ = "github_installations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # GitHub's numeric installation ID assigned when the App is installed
    github_installation_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    github_account_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[InstallationStatus] = mapped_column(
        String(32), default=InstallationStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization = relationship("Organization", back_populates="github_installation")

    __table_args__ = (
        # One installation per Oopsie org — enforced at DB level
        UniqueConstraint("organization_id", name="uq_github_installation_org"),
    )
