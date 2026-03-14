"""Tests for slug utility."""

import pytest
from oopsie.utils.slug import generate_unique_slug, slugify

from tests.factories import OrganizationFactory


def test_slugify_basic():
    assert slugify("My Company") == "my-company"


def test_slugify_special_chars():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_multiple_spaces():
    assert slugify("  lots   of   spaces  ") == "lots-of-spaces"


def test_slugify_underscores_and_hyphens():
    assert slugify("under_score-and-hyphen") == "under-score-and-hyphen"


def test_slugify_empty_string():
    assert slugify("") == "default"


def test_slugify_only_special_chars():
    assert slugify("!!!") == "default"


@pytest.mark.asyncio
async def test_generate_unique_slug_no_collision(db_session):
    """generate_unique_slug returns base slug when no collision."""
    slug = await generate_unique_slug(db_session, "My Company")
    assert slug == "my-company"


@pytest.mark.asyncio
async def test_generate_unique_slug_with_collision(db_session, factory):
    """generate_unique_slug appends -N on collision."""
    await factory(OrganizationFactory, slug="my-company")
    slug = await generate_unique_slug(db_session, "My Company")
    assert slug == "my-company-2"


@pytest.mark.asyncio
async def test_generate_unique_slug_multiple_collisions(db_session, factory):
    """generate_unique_slug increments counter for multiple collisions."""
    await factory(OrganizationFactory, slug="my-company")
    await factory(OrganizationFactory, slug="my-company-2")
    slug = await generate_unique_slug(db_session, "My Company")
    assert slug == "my-company-3"
