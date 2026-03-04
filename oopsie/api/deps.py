"""Dependency injection (db session, auth)."""

import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.auth import decode_jwt_token
from oopsie.database import get_session
from oopsie.logging import logger
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
