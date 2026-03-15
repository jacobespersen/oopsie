"""Tests for resolve_or_register_user with org-creation invitations."""

import pytest
from oopsie.auth import NoInvitationError, resolve_or_register_user
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole
from oopsie.models.org_creation_invitation import OrgCreationInvitation
from oopsie.models.organization import Organization
from sqlalchemy import select

from tests.factories import (
    OrganizationFactory,
    OrgCreationInvitationFactory,
    SignupRequestFactory,
    UserFactory,
)


def _google_info(email: str, sub: str = "google-sub-new") -> dict:
    return {"email": email, "sub": sub, "name": "Test User"}


@pytest.mark.asyncio
async def test_new_user_with_org_creation_invitation(db_session, factory):
    """New user with an org-creation invitation gets org + OWNER membership."""
    sr = await factory(SignupRequestFactory, email="new@example.com")
    admin = await factory(UserFactory)
    await factory(
        OrgCreationInvitationFactory,
        email="new@example.com",
        org_name="New Org",
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )

    user, memberships = await resolve_or_register_user(
        db_session, _google_info("new@example.com")
    )

    assert user.email == "new@example.com"
    assert len(memberships) == 1
    assert memberships[0].role == MemberRole.owner

    # Verify org was created
    result = await db_session.execute(
        select(Organization).where(Organization.name == "New Org")
    )
    org = result.scalar_one()
    assert org.slug == "new-org"

    # Verify invitation was deleted
    inv_result = await db_session.execute(
        select(OrgCreationInvitation).where(
            OrgCreationInvitation.email == "new@example.com"
        )
    )
    assert inv_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_existing_user_picks_up_org_creation_invitation(db_session, factory):
    """Existing user picks up pending org-creation invitation on re-login."""
    existing = await factory(UserFactory, email="existing@example.com")
    sr = await factory(SignupRequestFactory, email="existing@example.com")
    admin = await factory(UserFactory)
    await factory(
        OrgCreationInvitationFactory,
        email="existing@example.com",
        org_name="Another Org",
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )

    user, memberships = await resolve_or_register_user(
        db_session,
        _google_info("existing@example.com", sub=existing.google_sub),
    )

    assert user.id == existing.id
    assert len(memberships) == 1
    assert memberships[0].role == MemberRole.owner


@pytest.mark.asyncio
async def test_new_user_no_invitations_rejected(db_session):
    """New user with no invitations of either type is rejected."""
    with pytest.raises(NoInvitationError, match="no_invitation"):
        await resolve_or_register_user(db_session, _google_info("nobody@example.com"))


@pytest.mark.asyncio
async def test_platform_admin_flag_set_on_login(db_session, factory, monkeypatch):
    """User matching ADMIN_EMAIL gets is_platform_admin=True on login."""
    from oopsie.config import Settings, get_settings

    # Create an invitation so the user can register
    org = await factory(OrganizationFactory)

    invitation = Invitation(
        organization_id=org.id,
        email="admin@example.com",
        role=MemberRole.owner,
        invited_by_id=None,
    )
    db_session.add(invitation)
    await db_session.flush()

    # Monkeypatch settings to set admin_email
    original_settings = get_settings()
    monkeypatch.setattr(
        "oopsie.auth.get_settings",
        lambda: Settings(
            database_url=original_settings.database_url,
            redis_url=original_settings.redis_url,
            admin_email="admin@example.com",
        ),
    )

    user, _ = await resolve_or_register_user(
        db_session, _google_info("admin@example.com", sub="admin-sub")
    )
    assert user.is_platform_admin is True


@pytest.mark.asyncio
async def test_non_admin_email_no_platform_admin_flag(db_session, factory, monkeypatch):
    """User not matching ADMIN_EMAIL does not get is_platform_admin."""
    from oopsie.config import Settings, get_settings

    org = await factory(OrganizationFactory)

    invitation = Invitation(
        organization_id=org.id,
        email="regular@example.com",
        role=MemberRole.member,
        invited_by_id=None,
    )
    db_session.add(invitation)
    await db_session.flush()

    original_settings = get_settings()
    monkeypatch.setattr(
        "oopsie.auth.get_settings",
        lambda: Settings(
            database_url=original_settings.database_url,
            redis_url=original_settings.redis_url,
            admin_email="admin@example.com",
        ),
    )

    user, _ = await resolve_or_register_user(
        db_session, _google_info("regular@example.com", sub="regular-sub")
    )
    assert user.is_platform_admin is False


@pytest.mark.asyncio
async def test_slug_collision_handled(db_session, factory):
    """Org creation with a slug collision appends -2."""
    # Create existing org with the slug that would be generated
    await factory(OrganizationFactory, slug="collision-org")

    sr = await factory(SignupRequestFactory, email="collision@example.com")
    admin = await factory(UserFactory)
    await factory(
        OrgCreationInvitationFactory,
        email="collision@example.com",
        org_name="Collision Org",
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )

    user, memberships = await resolve_or_register_user(
        db_session, _google_info("collision@example.com")
    )

    # Verify slug has -2 suffix
    result = await db_session.execute(
        select(Organization).where(Organization.name == "Collision Org")
    )
    org = result.scalar_one()
    assert org.slug == "collision-org-2"


async def test_existing_admin_user_fast_return_path(db_session, factory, monkeypatch):
    """Existing admin-email user without org-creation invitations takes fast path."""
    from oopsie.config import Settings, get_settings

    from tests.factories import MembershipFactory

    org = await factory(OrganizationFactory)
    existing = await factory(
        UserFactory, email="admin@example.com", google_sub="admin-sub-fast"
    )
    await factory(
        MembershipFactory,
        user_id=existing.id,
        organization_id=org.id,
        role=MemberRole.owner,
    )

    original_settings = get_settings()
    monkeypatch.setattr(
        "oopsie.auth.get_settings",
        lambda: Settings(
            database_url=original_settings.database_url,
            redis_url=original_settings.redis_url,
            admin_email="admin@example.com",
        ),
    )

    user, memberships = await resolve_or_register_user(
        db_session, _google_info("admin@example.com", sub="admin-sub-fast")
    )
    assert user.id == existing.id
    assert user.is_platform_admin is True
    # Fast path: no new memberships returned
    assert memberships == []


async def test_new_user_with_both_invitation_types(db_session, factory):
    """New user with both a regular invitation AND an org-creation invitation."""
    org = await factory(OrganizationFactory)
    admin = await factory(UserFactory)

    # Regular invitation to existing org
    invitation = Invitation(
        organization_id=org.id,
        email="both@example.com",
        role=MemberRole.member,
        invited_by_id=admin.id,
    )
    db_session.add(invitation)
    await db_session.flush()

    # Org-creation invitation
    sr = await factory(SignupRequestFactory, email="both@example.com")
    await factory(
        OrgCreationInvitationFactory,
        email="both@example.com",
        org_name="Both Org",
        signup_request_id=sr.id,
        invited_by_id=admin.id,
    )

    user, memberships = await resolve_or_register_user(
        db_session, _google_info("both@example.com", sub="both-sub")
    )
    assert len(memberships) == 2
    roles = {m.role for m in memberships}
    assert MemberRole.member in roles
    assert MemberRole.owner in roles


async def test_case_insensitive_admin_email(db_session, factory, monkeypatch):
    """Admin email matching is case-insensitive."""
    from oopsie.config import Settings, get_settings

    org = await factory(OrganizationFactory)
    invitation = Invitation(
        organization_id=org.id,
        email="Admin@Example.COM",
        role=MemberRole.member,
        invited_by_id=None,
    )
    db_session.add(invitation)
    await db_session.flush()

    original_settings = get_settings()
    monkeypatch.setattr(
        "oopsie.auth.get_settings",
        lambda: Settings(
            database_url=original_settings.database_url,
            redis_url=original_settings.redis_url,
            admin_email="admin@example.com",
        ),
    )

    user, _ = await resolve_or_register_user(
        db_session, _google_info("Admin@Example.COM", sub="case-sub")
    )
    assert user.is_platform_admin is True


async def test_non_no_invitation_error_propagates(db_session, monkeypatch):
    """Non-NoInvitationError exceptions propagate from resolve_or_register_user."""

    async def _raise_runtime(*args, **kwargs):
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(
        "oopsie.auth.get_pending_org_creation_invitations", _raise_runtime
    )

    with pytest.raises(RuntimeError, match="something unexpected"):
        await resolve_or_register_user(db_session, _google_info("error@example.com"))
