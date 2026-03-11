"""GithubInstallation model tests."""

import pytest
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.organization import Organization
from sqlalchemy.exc import IntegrityError
from tests.factories import GithubInstallationFactory, OrganizationFactory


@pytest.mark.asyncio
async def test_github_installation_persists_and_retrieves(db_session):
    """GithubInstallation can be created, flushed, and retrieved with correct fields."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    installation = GithubInstallationFactory.build(organization_id=org.id)
    db_session.add(installation)
    await db_session.flush()

    assert installation.id is not None
    assert installation.organization_id == org.id
    assert isinstance(installation.github_installation_id, int)
    # github_account_login is nullable; factory defaults to None
    assert installation.github_account_login is None
    assert installation.status == InstallationStatus.ACTIVE
    assert installation.created_at is not None
    assert installation.updated_at is not None


@pytest.mark.asyncio
async def test_installation_status_enum_values():
    """InstallationStatus enum has exactly ACTIVE, SUSPENDED, REMOVED values."""
    assert InstallationStatus.ACTIVE == "active"
    assert InstallationStatus.SUSPENDED == "suspended"
    assert InstallationStatus.REMOVED == "removed"
    # Verify there are exactly 3 values
    values = list(InstallationStatus)
    assert len(values) == 3


@pytest.mark.asyncio
async def test_unique_constraint_on_organization_id(db_session):
    """A second GithubInstallation for the same org raises IntegrityError."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    inst1 = GithubInstallationFactory.build(organization_id=org.id)
    db_session.add(inst1)
    await db_session.flush()

    inst2 = GithubInstallationFactory.build(organization_id=org.id)
    db_session.add(inst2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_cascade_delete_removes_installation(db_session):
    """Deleting an Organization also deletes its GithubInstallation (CASCADE)."""
    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    installation = GithubInstallationFactory.build(organization_id=org.id)
    db_session.add(installation)
    await db_session.flush()
    installation_id = installation.id

    await db_session.delete(org)
    await db_session.flush()

    result = await db_session.get(GithubInstallation, installation_id)
    assert result is None


@pytest.mark.asyncio
async def test_organization_github_installation_relationship(db_session):
    """Organization.github_installation returns the related installation."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    org = OrganizationFactory.build()
    db_session.add(org)
    await db_session.flush()

    installation = GithubInstallationFactory.build(organization_id=org.id)
    db_session.add(installation)
    await db_session.flush()

    # Reload org with relationship eagerly loaded
    stmt = (
        select(Organization)
        .where(Organization.id == org.id)
        .options(selectinload(Organization.github_installation))
    )
    result = await db_session.execute(stmt)
    loaded_org = result.scalar_one()

    assert loaded_org.github_installation is not None
    assert loaded_org.github_installation.id == installation.id
