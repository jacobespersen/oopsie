"""Pydantic schemas for error context (exception chains, execution context)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class MechanismInfo(BaseModel):
    """How an exception was raised (chained, generic, etc.)."""

    type: str = Field(min_length=1)
    handled: bool = True


class StackFrame(BaseModel):
    """A single frame in an exception's stack trace."""

    file: str = Field(min_length=1)
    function: str | None = None
    lineno: int | None = Field(None, ge=1)
    module: str | None = None
    in_app: bool = True
    context_line: str | None = None
    pre_context: list[str] | None = Field(None, max_length=5)
    post_context: list[str] | None = Field(None, max_length=5)
    vars: dict[str, Any] | None = None

    @field_validator("vars")
    @classmethod
    def _validate_vars_max_keys(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(v) > 50:
            msg = f"vars must have at most 50 keys, got {len(v)}"
            raise ValueError(msg)
        return v


class ExceptionEntry(BaseModel):
    """One exception in a chain, with optional structured stack frames."""

    type: str = Field(min_length=1)
    value: str = Field(min_length=1)
    module: str | None = None
    mechanism: MechanismInfo | None = None
    stacktrace: list[StackFrame] | None = Field(None, max_length=100)


class ExecutionContext(BaseModel):
    """What the application was doing when the error occurred."""

    type: str = Field(min_length=1)
    description: str | None = None
    data: dict[str, Any] | None = None

    @field_validator("data")
    @classmethod
    def _validate_data_max_keys(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(v) > 32:
            msg = f"data must have at most 32 top-level keys, got {len(v)}"
            raise ValueError(msg)
        return v
