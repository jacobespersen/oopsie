"""Dependency injection (db session, auth)."""

from fastapi import Depends, HTTPException, Request

# Keep HTTPBearer only for API key auth (get_project_from_api_key)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.database import get_session
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership, role_rank
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

    Raises 401 if missing, invalid, or expired.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = await get_session_user_id(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

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
    except HTTPException:
        return None


async def get_current_membership(
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> "Membership":
    """Return the current user's Membership for the given org slug.

    Raises 403 if the user is not a member of that organization.
    """
    from oopsie.models.organization import Organization

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
        org_slug: str,
        session: AsyncSession = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) -> Membership:
        membership = await get_current_membership(org_slug, session, current_user)
        if role_rank(membership.role) < self._min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {self._label}",
            )
        # Populate the user relationship so callers don't need a separate dep
        membership.user = current_user
        return membership
