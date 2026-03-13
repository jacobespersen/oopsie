"""Google OAuth helpers and invitation-gated registration."""

import uuid
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import joinedload

if TYPE_CHECKING:
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.user import User


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

    result = await session.execute(select(Invitation).where(Invitation.email == email))
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


async def resolve_or_register_user(
    session: AsyncSession, google_user_info: dict[str, Any]
) -> tuple[User, "list[Membership]"]:
    """Authenticate a Google OAuth user, handling invitation-gated registration.

    Returns the user and a list of new Memberships from accepted invitations.
    Raises ValueError with a redirect hint if the user is new and has no invitation.
    """
    google_sub = google_user_info["sub"]
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    existing = result.scalar_one_or_none()

    # Check for pending invitations (both new and existing users)
    invitations = await get_pending_invitations(session, google_user_info["email"])

    if existing is None and not invitations:
        # New user with no invitation — reject registration
        raise ValueError("no_invitation")

    user = await upsert_user(session, google_user_info, existing=existing)

    memberships: list[Membership] = []
    for invitation in invitations:
        membership = await accept_invitation(session, invitation, user)
        memberships.append(membership)

    return user, memberships


async def get_user_default_redirect(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Look up the user's first org membership and return a redirect URL.

    Falls back to the login page with an error if the user has no organization.
    """
    from oopsie.models.membership import Membership

    mem_result = await session.execute(
        select(Membership)
        .options(joinedload(Membership.organization))
        .where(Membership.user_id == user_id)
        .limit(1)
    )
    mem = mem_result.scalar_one_or_none()
    if mem and mem.organization:
        return f"/orgs/{mem.organization.slug}/projects"
    return "/auth/login?error=no_organization"
