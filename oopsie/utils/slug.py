"""Slug generation utilities for URL-safe identifiers."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.models.organization import Organization


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug or "default"


async def generate_unique_slug(session: AsyncSession, name: str) -> str:
    """Generate a unique organization slug, appending -N on collision."""
    base = slugify(name)
    candidate = base
    counter = 2
    while True:
        existing = await session.execute(
            select(Organization.id).where(Organization.slug == candidate).limit(1)
        )
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1
