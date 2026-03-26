"""ErrorOccurrence model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class ErrorOccurrence(Base):
    __tablename__ = "error_occurrences"
    __table_args__ = (
        Index("ix_error_occurrences_error_id_occurred_at", "error_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    error_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("errors.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    exception_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    execution_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )

    error = relationship("Error", back_populates="occurrences")
