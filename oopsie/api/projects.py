"""Project API (CRUD for projects)."""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.api.deps import RequireRole, get_current_user, get_session
from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.project import Project
from oopsie.models.user import User
from oopsie.utils.encryption import encrypt_value, hash_api_key

router = APIRouter()


class ProjectCreateBody(BaseModel):
    """Request body for POST /api/v1/orgs/{org_slug}/projects."""

    name: str
    github_repo_url: str
    github_token: str
    default_branch: str = "main"
    error_threshold: int = 10


class ProjectUpdateBody(BaseModel):
    """Request body for PUT /api/v1/orgs/{org_slug}/projects/{id}."""

    name: str | None = None
    github_repo_url: str | None = None
    github_token: str | None = None
    default_branch: str | None = None
    error_threshold: int | None = None


@router.get("/{org_slug}/projects")
@router.get("/{org_slug}/projects/")
async def list_projects(
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.MEMBER)),
):
    """List projects in the current org."""
    result = await session.execute(
        select(Project)
        .where(Project.organization_id == membership.organization_id)
        .order_by(Project.created_at.desc())
    )
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


@router.get("/{org_slug}/projects/{project_id}")
async def get_project(
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.MEMBER)),
):
    """Get a project by id (must belong to current org)."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == membership.organization_id,
        )
    )
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


@router.post("/{org_slug}/projects", status_code=201)
@router.post("/{org_slug}/projects/", status_code=201)
async def create_project(
    org_slug: str,
    body: ProjectCreateBody,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
):
    """Create a project in the current org and return its api_key."""
    settings = get_settings()
    api_key = secrets.token_urlsafe(32)
    project = Project(
        name=body.name,
        github_repo_url=body.github_repo_url,
        github_token_encrypted=encrypt_value(
            body.github_token, settings.encryption_key
        ),
        default_branch=body.default_branch,
        error_threshold=body.error_threshold,
        api_key_hash=hash_api_key(api_key),
        organization_id=membership.organization_id,
    )
    session.add(project)
    await session.flush()
    logger.info("project_created", project_id=str(project.id), name=body.name)
    return {
        "id": str(project.id),
        "name": project.name,
        "api_key": api_key,
    }


@router.put("/{org_slug}/projects/{project_id}")
async def update_project(
    org_slug: str,
    project_id: uuid.UUID,
    body: ProjectUpdateBody,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
):
    """Update a project (must belong to current org)."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == membership.organization_id,
        )
    )
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


@router.delete("/{org_slug}/projects/{project_id}", status_code=204)
async def delete_project(
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
):
    """Delete a project (must belong to current org)."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == membership.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.flush()
    logger.info("project_deleted", project_id=str(project_id))
