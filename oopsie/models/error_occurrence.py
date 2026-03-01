"""ErrorOccurrence model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from oopsie.models.base import Base


class ErrorOccurrence(Base):
    __tablename__ = "error_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=None
    )
    error_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("errors.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    error = relationship("Error", back_populates="occurrences")
