"""Organization model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
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

    memberships = relationship(
        "Membership", back_populates="organization", cascade="all, delete-orphan"
    )
    invitations = relationship(
        "Invitation", back_populates="organization", cascade="all, delete-orphan"
    )
    projects = relationship(
        "Project", back_populates="organization", cascade="all, delete-orphan"
    )
    github_installation = relationship(
        "GithubInstallation",
        back_populates="organization",
        cascade="all, delete-orphan",
        uselist=False,
    )
