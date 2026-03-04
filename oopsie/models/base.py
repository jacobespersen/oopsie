"""Declarative base and shared model utilities."""

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models. Use this for Alembic metadata."""

    def __repr__(self) -> str:
        mapper = inspect(type(self))
        cols = {c.key: getattr(self, c.key) for c in mapper.column_attrs}
        pairs = ", ".join(f"{k}={v!r}" for k, v in cols.items())
        return f"{type(self).__name__}({pairs})"
