"""Dependency injection (db session, auth)."""

from fastapi import Depends, HTTPException, Request

# Keep HTTPBearer only for API key auth (get_project_from_api_key)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from oopsie.database import get_session
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership, role_rank
from oopsie.models.organization import Organization
from oopsie.models.project import Project
from oopsie.models.user import User
from oopsie.session import extend_session, get_session_user_id
from oopsie.utils.encryption import hash_api_key

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_project_from_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Project:
    """Resolve project from Authorization: Bearer <api_key>.

    Raises 401 if missing or invalid.
    """
    if not credentials or not credentials.credentials:
        logger.warning("auth_missing_credentials")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )
    hashed = hash_api_key(credentials.credentials)
    result = await session.execute(
        select(Project).where(Project.api_key_hash == hashed)
    )
    project = result.scalar_one_or_none()
    if not project:
        logger.warning("auth_invalid_api_key")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return project


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Extract session_id from cookie and return the current user.

    Raises 401 if missing, invalid, or expired. Eagerly loads the user's
    membership + organization (single query) and stashes org_slug on
    request.state for downstream use.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = await get_session_user_id(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Single query: user + their membership's organization (user can only
    # belong to one org due to uq_membership_user constraint).
    result = await session.execute(
        select(User)
        .outerjoin(Membership, Membership.user_id == User.id)
        .outerjoin(Organization, Organization.id == Membership.organization_id)
        .options(joinedload(User.memberships).joinedload(Membership.organization))
        .where(User.id == user_id)
    )
    user = result.unique().scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Stash org_slug from the DB for downstream use (e.g., landing redirect)
    membership = user.memberships[0] if user.memberships else None
    request.state.org_slug = membership.organization.slug if membership else None

    # Reset sliding window TTL so active users stay logged in
    await extend_session(token)

    return user


async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request, session)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


async def get_authenticated_membership(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
) -> Membership:
    """Resolve session → user → membership + org in a single DB query.

    Combines what was previously get_current_user + get_current_membership
    into one round-trip for org-scoped pages.

    Raises 401 if session is missing/invalid, 403 if user is not a member.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = await get_session_user_id(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Single query: membership + user + organization
    result = await session.execute(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .join(Organization, Organization.id == Membership.organization_id)
        .options(
            joinedload(Membership.user),
            joinedload(Membership.organization),
        )
        .where(User.id == user_id, Organization.slug == org_slug)
    )
    membership = result.unique().scalar_one_or_none()

    if not membership:
        # Distinguish 401 (user doesn't exist) from 403 (not a member).
        # Check whether the user exists at all.
        user_result = await session.execute(select(User.id).where(User.id == user_id))
        if user_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=401, detail="User not found")
        raise HTTPException(
            status_code=403, detail="You are not a member of this organization"
        )

    # Reset sliding window TTL so active users stay logged in
    await extend_session(token)

    return membership


async def get_current_membership(
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> "Membership":
    """Return the current user's Membership for the given org slug.

    Raises 403 if the user is not a member of that organization.
    """
    result = await session.execute(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Organization.slug == org_slug,
            Membership.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=403, detail="You are not a member of this organization"
        )
    return membership


class RequireRole:
    """FastAPI dependency that enforces a minimum organization role.

    The lowest role passed to the constructor sets the minimum required rank.
    Any role equal to or higher than that minimum is accepted.

    Uses get_authenticated_membership to resolve session → user → membership
    in a single DB query (instead of separate get_current_user +
    get_current_membership calls).

    Usage::

        @router.get("/admin-only")
        async def admin_view(
            membership: Membership = Depends(RequireRole(MemberRole.admin)),
        ):
            ...
    """

    def __init__(self, *allowed_roles: MemberRole) -> None:
        min_role = min(allowed_roles, key=role_rank)
        self._min_rank = role_rank(min_role)
        self._label = min_role.value

    async def __call__(
        self,
        request: Request,
        org_slug: str,
        session: AsyncSession = Depends(get_session),
    ) -> Membership:
        membership = await get_authenticated_membership(request, org_slug, session)
        if role_rank(membership.role) < self._min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {self._label}",
            )
        return membership


async def require_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Gate access to platform admin features.

    Reuses get_current_user for session verification, then checks
    the is_platform_admin flag. Returns 403 for non-admins.
    """
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return current_user
