"""Bootstrap service tests."""

import pytest
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole
from oopsie.models.organization import Organization
from oopsie.services.bootstrap_service import bootstrap_if_needed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_bootstrap_creates_org_and_invitation(db_session: AsyncSession):
    """When no orgs exist and admin_email is set, creates org and owner invitation."""
    await bootstrap_if_needed(
        db_session, admin_email="admin@example.com", org_name="Acme"
    )

    orgs = (await db_session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 1
    assert orgs[0].name == "Acme"
    assert orgs[0].slug == "acme"

    invitations = (await db_session.execute(select(Invitation))).scalars().all()
    assert len(invitations) == 1
    assert invitations[0].email == "admin@example.com"
    assert invitations[0].role == MemberRole.owner
    assert invitations[0].invited_by_id is None


@pytest.mark.asyncio
async def test_bootstrap_skipped_when_org_exists(db_session: AsyncSession, factory):
    """When orgs already exist, bootstrap does nothing."""
    from tests.factories import OrganizationFactory

    await factory(OrganizationFactory)
    await bootstrap_if_needed(
        db_session, admin_email="admin@example.com", org_name="Acme"
    )

    orgs = (await db_session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 1  # still just the one we created


@pytest.mark.asyncio
async def test_bootstrap_skipped_when_no_admin_email(db_session: AsyncSession):
    """When admin_email is empty, bootstrap does nothing even if no orgs exist."""
    await bootstrap_if_needed(db_session, admin_email="", org_name="Acme")

    orgs = (await db_session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 0


@pytest.mark.asyncio
async def test_bootstrap_idempotent(db_session: AsyncSession):
    """Calling bootstrap_if_needed twice does not create duplicate data."""
    await bootstrap_if_needed(
        db_session, admin_email="admin@example.com", org_name="Acme"
    )
    await bootstrap_if_needed(
        db_session, admin_email="admin@example.com", org_name="Acme"
    )

    orgs = (await db_session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 1

    invitations = (await db_session.execute(select(Invitation))).scalars().all()
    assert len(invitations) == 1
