"""Google OAuth helpers and invitation-gated registration."""

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import joinedload

if TYPE_CHECKING:
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership
    from oopsie.models.org_creation_invitation import OrgCreationInvitation

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.user import User


class NoInvitationError(Exception):
    """Raised when a new user attempts to register without a pending invitation."""


@lru_cache(maxsize=1)
def _build_google_client() -> Any:
    """Create and cache the authlib Google OAuth client."""
    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.google


def get_google_oauth_client() -> Any:
    """Return the Google OAuth client (cached after first call)."""
    return _build_google_client()


async def upsert_user(
    session: AsyncSession,
    google_user_info: dict[str, Any],
    existing: User | None = None,
) -> User:
    """Find or create a user from Google userinfo. Updates fields if changed.

    If *existing* is provided the lookup-by-google-sub is skipped.
    """
    if existing is None:
        google_sub = google_user_info["sub"]
        result = await session.execute(
            select(User).where(User.google_sub == google_sub)
        )
        existing = result.scalar_one_or_none()

    if existing is None:
        user = User(
            email=google_user_info["email"],
            name=google_user_info.get("name", google_user_info["email"]),
            google_sub=google_user_info["sub"],
            avatar_url=google_user_info.get("picture"),
        )
        session.add(user)
        await session.flush()
        logger.info("user_created", user_id=str(user.id), email=user.email)
    else:
        user = existing
        user.email = google_user_info["email"]
        user.name = google_user_info.get("name", user.name)
        user.avatar_url = google_user_info.get("picture", user.avatar_url)
        await session.flush()
        logger.info("user_updated", user_id=str(user.id), email=user.email)

    return user


async def get_pending_invitations(
    session: AsyncSession, email: str
) -> "list[Invitation]":
    """Return all pending invitations for the given email."""
    from oopsie.models.invitation import Invitation

    result = await session.execute(
        select(Invitation)
        .options(joinedload(Invitation.organization))
        .where(Invitation.email == email)
    )
    return list(result.scalars().all())


async def accept_invitation(
    session: AsyncSession, invitation: "Invitation", user: User
) -> "Membership":
    """Accept an invitation: create Membership and delete the invitation row."""
    from oopsie.models.membership import Membership

    invitation_id = invitation.id
    membership = Membership(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
    )
    # Set the relationship directly so callers can access .organization
    # without triggering a lazy load (which fails in async context).
    membership.organization = invitation.organization
    session.add(membership)
    # Invitation is transient — delete now that it's fulfilled
    await session.delete(invitation)
    await session.flush()
    logger.info(
        "invitation_accepted",
        invitation_id=str(invitation_id),
        user_id=str(user.id),
        role=membership.role.value,
    )
    return membership


async def get_pending_org_creation_invitations(
    session: AsyncSession, email: str
) -> "list[OrgCreationInvitation]":
    """Return all pending org-creation invitations for the given email."""
    from oopsie.models.org_creation_invitation import OrgCreationInvitation

    result = await session.execute(
        select(OrgCreationInvitation).where(OrgCreationInvitation.email == email)
    )
    return list(result.scalars().all())


async def accept_org_creation_invitation(
    session: AsyncSession,
    invitation: "OrgCreationInvitation",
    user: User,
) -> "Membership":
    """Accept an org-creation invitation: create Organization + OWNER Membership.

    The invitation row is deleted after acceptance (matching the existing
    Invitation pattern).
    """
    from oopsie.models.membership import MemberRole, Membership
    from oopsie.models.organization import Organization
    from oopsie.utils.slug import generate_unique_slug

    slug = await generate_unique_slug(session, invitation.org_name)
    org = Organization(name=invitation.org_name, slug=slug)
    session.add(org)
    await session.flush()

    membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.owner,
    )
    # Set the relationship directly so callers can access .organization
    # without triggering a lazy load (which fails in async context).
    membership.organization = org
    session.add(membership)

    invitation_id = invitation.id
    org_name = invitation.org_name
    await session.delete(invitation)
    await session.flush()

    logger.info(
        "org_creation_invitation_accepted",
        invitation_id=str(invitation_id),
        user_id=str(user.id),
        org_id=str(org.id),
        org_name=org_name,
    )
    return membership


async def resolve_or_register_user(
    session: AsyncSession, google_user_info: dict[str, Any]
) -> tuple[User, "list[Membership]"]:
    """Authenticate a Google OAuth user, handling invitation-gated registration.

    Returns the user and a list of new Memberships from accepted invitations.
    Raises NoInvitationError if the user is new and has no invitation.

    Handles both membership invitations and org-creation invitations.
    Sets is_platform_admin when email matches ADMIN_EMAIL.
    Eagerly loads memberships + organizations so callers can derive redirect URLs
    without an additional query.
    """
    from oopsie.models.membership import Membership

    google_sub = google_user_info["sub"]
    result = await session.execute(
        select(User)
        .options(joinedload(User.memberships).joinedload(Membership.organization))
        .where(User.google_sub == google_sub)
    )
    existing = result.unique().scalar_one_or_none()

    email = google_user_info["email"]

    # Check for pending org-creation invitations (needed for both new and existing)
    org_creation_invitations = await get_pending_org_creation_invitations(
        session, email
    )

    if existing is not None and not org_creation_invitations:
        # Returning user with no org-creation invitations — just update profile
        user = await upsert_user(session, google_user_info, existing=existing)
        _set_platform_admin_if_needed(user, email)
        if user.is_platform_admin:
            await session.flush()
        return user, []

    # New user or existing user with org-creation invitations — check all invitations
    invitations = await get_pending_invitations(session, email)

    if existing is None and not invitations and not org_creation_invitations:
        # New user with no invitation of either type — reject registration
        raise NoInvitationError("no_invitation")

    user = await upsert_user(session, google_user_info, existing=existing)
    _set_platform_admin_if_needed(user, email)
    if user.is_platform_admin:
        await session.flush()

    memberships: list[Membership] = []
    for invitation in invitations:
        membership = await accept_invitation(session, invitation, user)
        memberships.append(membership)

    # Accept any pending org-creation invitations (creates org + OWNER membership)
    for org_invitation in org_creation_invitations:
        membership = await accept_org_creation_invitation(session, org_invitation, user)
        memberships.append(membership)

    return user, memberships


def _set_platform_admin_if_needed(user: User, email: str) -> None:
    """Set is_platform_admin flag if email matches ADMIN_EMAIL."""
    settings = get_settings()
    if settings.admin_email and email.lower() == settings.admin_email.lower():
        user.is_platform_admin = True
