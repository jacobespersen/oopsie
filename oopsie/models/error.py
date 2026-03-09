"""Error model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class ErrorStatus(enum.StrEnum):
    OPEN = "open"
    FIX_ATTEMPTED = "fix_attempted"
    FIX_MERGED = "fix_merged"
    IGNORED = "ignored"


class Error(Base):
    __tablename__ = "errors"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    error_class: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=ErrorStatus.OPEN,
        nullable=False,
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

    project = relationship("Project", back_populates="errors")
    occurrences = relationship(
        "ErrorOccurrence", back_populates="error", cascade="all, delete-orphan"
    )
    fix_attempts = relationship(
        "FixAttempt", back_populates="error", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_errors_project_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
        ),
    )
