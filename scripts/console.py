"""Interactive console with ORM models and a DB session pre-loaded."""

import asyncio
import code
import uuid as _uuid

from oopsie.config import get_settings
from oopsie.models import *  # noqa: F401, F403
from sqlalchemy import select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_settings = get_settings()
_engine = create_async_engine(_settings.database_url)
session = AsyncSession(_engine)

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def run(coro):
    """Run an async expression. Usage: run(session.execute(select(User)))"""
    return _loop.run_until_complete(coro)


# ---- Rails-style helpers ----


def fetch_all(model):
    """Fetch all rows.  Usage: fetch_all(User)"""
    return run(session.execute(select(model))).scalars().all()


def find(model, pk):
    """Find by primary key.  Usage: find(User, "some-uuid")"""
    if isinstance(pk, str):
        pk = _uuid.UUID(pk)
    return run(
        session.execute(select(model).where(model.id == pk))
    ).scalar_one_or_none()


def first(model):
    """Fetch the first row.  Usage: first(User)"""
    return run(session.execute(select(model).limit(1))).scalar_one_or_none()


def count(model):
    """Count rows.  Usage: count(Project)"""
    return len(fetch_all(model))


def where(model, **kwargs):
    """Filter by column values.  Usage: where(User, email="foo@bar.com")"""
    stmt = select(model)
    for col, val in kwargs.items():
        stmt = stmt.where(getattr(model, col) == val)
    return run(session.execute(stmt)).scalars().all()


def reload(obj):
    """Refresh an object from DB.  Usage: reload(user)"""
    run(session.refresh(obj))
    return obj


banner = (
    f"Connected to {_settings.database_url}\n\n"
    "  fetch_all(User)                 — fetch all rows\n"
    "  find(User, pk)                  — find by primary key\n"
    "  first(User)                     — first row\n"
    "  where(User, email='foo@b.com')  — filter by column\n"
    "  count(Project)                  — count rows\n"
    "  reload(obj)                     — refresh from DB\n\n"
    "  For complex queries: run(session.execute(select(User).where(...)))\n"
)

code.interact(local={**globals(), **locals()}, banner=banner)
_loop.run_until_complete(_engine.dispose())
