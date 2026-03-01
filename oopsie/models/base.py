"""Declarative base and shared model utilities."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models. Use this for Alembic metadata."""

    pass
