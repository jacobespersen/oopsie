"""Dependency injection (db session, auth)."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.database import get_session
from oopsie.models.project import Project
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
        raise HTTPException(status_code=401, detail="Invalid API key")
    return project


__all__ = ["get_session", "get_project_from_api_key"]
