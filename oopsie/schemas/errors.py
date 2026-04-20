"""Pydantic schemas for the error ingestion API."""

from pydantic import BaseModel, Field

from oopsie.schemas.context import ExceptionEntry, ExecutionContext


class ErrorIngestBody(BaseModel):
    """Request body for POST /api/v1/errors."""

    error_class: str
    message: str
    stack_trace: str | None = None
    exception_chain: list[ExceptionEntry] | None = Field(None, max_length=20)
    execution_context: ExecutionContext | None = None
