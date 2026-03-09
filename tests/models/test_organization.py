"""Organization model tests."""

import pytest
from oopsie.models.organization import Organization
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_organization_creation(db_session):
    """Organization can be created with name and slug."""
    org = Organization(name="Acme Corp", slug="acme-corp")
    db_session.add(org)
    await db_session.flush()

    assert org.id is not None
    assert org.name == "Acme Corp"
    assert org.slug == "acme-corp"
    assert org.created_at is not None
    assert org.updated_at is not None


@pytest.mark.asyncio
async def test_organization_slug_unique(db_session):
    """Organization slug must be unique."""
    db_session.add(Organization(name="Acme", slug="acme"))
    await db_session.flush()

    db_session.add(Organization(name="Acme 2", slug="acme"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
