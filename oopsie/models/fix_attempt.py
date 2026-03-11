"""FixAttempt model."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class FixAttemptStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    # PR was merged on GitHub; distinct from SUCCESS which means 'PR opened'
    MERGED = "merged"


class FixAttempt(Base):
    __tablename__ = "fix_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    error_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("errors.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[FixAttemptStatus] = mapped_column(
        String(32), default=FixAttemptStatus.PENDING, nullable=False
    )
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    claude_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    error = relationship("Error", back_populates="fix_attempts")
