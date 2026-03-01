"""Project API (CRUD for projects)."""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.api.deps import get_session
from oopsie.config import get_settings
from oopsie.models.project import Project
from oopsie.utils.encryption import encrypt_value, hash_api_key

router = APIRouter()


class ProjectCreateBody(BaseModel):
    """Request body for POST /api/v1/projects."""

    name: str
    github_repo_url: str
    github_token: str
    default_branch: str = "main"
    error_threshold: int = 10


class ProjectUpdateBody(BaseModel):
    """Request body for PUT /api/v1/projects/{id}."""

    name: str | None = None
    github_repo_url: str | None = None
    github_token: str | None = None
    default_branch: str | None = None
    error_threshold: int | None = None


@router.get("")
@router.get("/")
async def list_projects(
    session: AsyncSession = Depends(get_session),
):
    """List all projects."""
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "github_repo_url": p.github_repo_url,
            "default_branch": p.default_branch,
            "error_threshold": p.error_threshold,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get a project by id. Does not include api_key or github_token."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": str(project.id),
        "name": project.name,
        "github_repo_url": project.github_repo_url,
        "default_branch": project.default_branch,
        "error_threshold": project.error_threshold,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_project(
    body: ProjectCreateBody,
    session: AsyncSession = Depends(get_session),
):
    """Create a project and return its api_key (unauthenticated)."""
    settings = get_settings()
    api_key = secrets.token_urlsafe(32)
    project = Project(
        name=body.name,
        github_repo_url=body.github_repo_url,
        github_token_encrypted=encrypt_value(
            body.github_token,
            settings.encryption_key
        ),
        default_branch=body.default_branch,
        error_threshold=body.error_threshold,
        api_key_hash=hash_api_key(api_key),
    )
    session.add(project)
    await session.flush()
    return {
        "id": str(project.id),
        "name": project.name,
        "api_key": api_key,
    }


@router.put("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdateBody,
    session: AsyncSession = Depends(get_session),
):
    """Update a project."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = body.model_dump(exclude_unset=True)
    raw_token = updates.pop("github_token", None)
    if raw_token is not None:
        settings = get_settings()
        updates["github_token_encrypted"] = encrypt_value(
            raw_token, settings.encryption_key
        )
    for key, value in updates.items():
        setattr(project, key, value)
    await session.flush()
    return {
        "id": str(project.id),
        "name": project.name,
        "github_repo_url": project.github_repo_url,
        "default_branch": project.default_branch,
        "error_threshold": project.error_threshold,
    }


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.flush()
