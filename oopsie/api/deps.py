"""Dependency injection (db session, auth)."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.auth import decode_jwt_token
from oopsie.database import get_session
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.project import Project
from oopsie.models.user import User
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
    """Extract JWT from cookie or Authorization header and return the current user.

    Raises 401 if missing, invalid, expired, or revoked.
    """
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = await decode_jwt_token(token, session)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await session.execute(
        select(User).where(User.id == uuid.UUID(user_id_str))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
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


__all__ = [
    "get_session",
    "get_project_from_api_key",
    "get_current_user",
    "get_optional_user",
]


_ROLE_ORDER: list[MemberRole] = [MemberRole.MEMBER, MemberRole.ADMIN, MemberRole.OWNER]


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


def require_role(*allowed_roles: MemberRole) -> Callable[..., Any]:
    """Return a FastAPI dependency that enforces a minimum role.

    The lowest role in *allowed_roles* determines the minimum required. Any role
    that is equal to or higher than the minimum is accepted.
    """
    # Determine minimum rank
    min_rank = min(_ROLE_ORDER.index(r) for r in allowed_roles)

    async def _check(
        org_slug: str,
        session: AsyncSession = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) -> Membership:
        membership = await get_current_membership(org_slug, session, current_user)
        user_rank = _ROLE_ORDER.index(membership.role)
        if user_rank < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {allowed_roles[0].value}",
            )
        return membership

    return _check
