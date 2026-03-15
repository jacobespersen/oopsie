"""Web UI routes for projects (HTML forms)."""

import secrets
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.project import Project
from oopsie.routers.dependencies import RequireRole, get_session
from oopsie.routers.web import templates
from oopsie.services.anthropic_key_service import (
    clear_anthropic_api_key,
    get_anthropic_api_key,
    mask_anthropic_api_key,
    set_anthropic_api_key,
)
from oopsie.services.github_installation_service import get_installation_repos
from oopsie.utils.encryption import hash_api_key

router = APIRouter()


async def _get_org_project(
    session: AsyncSession, project_id: uuid.UUID, organization_id: uuid.UUID
) -> Project:
    """Fetch a project by id, verifying org ownership. Raises 404 if not found."""
    result = await session.execute(
        select(Project).where(
            Project.id == project_id, Project.organization_id == organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/orgs/{org_slug}/projects", response_class=HTMLResponse)
async def list_projects_page(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.member)),
) -> HTMLResponse:
    """List projects in the current org."""
    result = await session.execute(
        select(Project)
        .where(Project.organization_id == membership.organization_id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="projects/list.html",
        context={"projects": projects, "user": membership.user, "org_slug": org_slug},
    )


@router.get("/orgs/{org_slug}/projects/new", response_class=HTMLResponse)
async def new_project_page(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> HTMLResponse:
    """Show create project form."""
    installation, repos, repo_error = await get_installation_repos(
        session, membership.organization_id
    )
    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "project": None,
            "title": "New Project",
            "user": membership.user,
            "org_slug": org_slug,
            "installation": installation,
            "repos": repos,
            "repo_error": repo_error,
            "anthropic_key_masked": None,
        },
    )


@router.post("/orgs/{org_slug}/projects")
async def create_project_action(
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
    name: str = Form(...),
    github_repo_full_name: str = Form(...),
    default_branch: str = Form("main"),
    error_threshold: int = Form(10),
    anthropic_api_key: str = Form(""),
) -> RedirectResponse:
    """Create a project and redirect to the projects list.

    Validates that the submitted repo is accessible via the GitHub App
    installation before creating the project. The github_repo_url is
    derived server-side from the submitted full_name (REPO-02).

    A placeholder API key hash is generated so the project is valid,
    but the key is never exposed. Users generate a visible key via
    the "Generate API Key" action on the project's API key page.
    """
    _installation, repos, _error = await get_installation_repos(
        session, membership.organization_id
    )
    # Reject repos not in the accessible list — covers both no-installation
    # and repos the GitHub App cannot access (REPO-02 enforcement).
    if repos and github_repo_full_name not in repos:
        raise HTTPException(
            status_code=400, detail="Repository not accessible via GitHub App"
        )
    github_repo_url = f"https://github.com/{github_repo_full_name}"
    project = Project(
        name=name,
        github_repo_url=github_repo_url,
        default_branch=default_branch,
        error_threshold=error_threshold,
        api_key_hash=hash_api_key(secrets.token_urlsafe(32)),
        organization_id=membership.organization_id,
    )
    session.add(project)
    await session.flush()
    if anthropic_api_key:
        set_anthropic_api_key(project, anthropic_api_key, get_settings().encryption_key)
        await session.flush()
    logger.info("project_created", project_id=str(project.id), name=name)
    return RedirectResponse(
        url=f"/orgs/{org_slug}/projects",
        status_code=303,
    )


@router.get(
    "/orgs/{org_slug}/projects/{project_id}/api-key", response_class=HTMLResponse
)
async def project_api_key_page(
    request: Request,
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> HTMLResponse:
    """Show API key page for a project."""
    project = await _get_org_project(session, project_id, membership.organization_id)
    # Consume the API key from session — it's only shown once after regeneration
    api_key = request.session.pop("flash_api_key", None)
    return templates.TemplateResponse(
        request=request,
        name="projects/api_key.html",
        context={
            "project": project,
            "api_key": api_key,
            "just_regenerated": api_key is not None,
            "user": membership.user,
            "org_slug": org_slug,
        },
    )


@router.post("/orgs/{org_slug}/projects/{project_id}/regenerate-api-key")
async def regenerate_api_key_action(
    request: Request,
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> RedirectResponse:
    """Regenerate API key and redirect to show the new key."""
    project = await _get_org_project(session, project_id, membership.organization_id)
    new_api_key = secrets.token_urlsafe(32)
    project.api_key_hash = hash_api_key(new_api_key)
    await session.flush()
    logger.info("api_key_regenerated", project_id=str(project_id))
    # Store API key in session so it never appears in the URL or browser history
    request.session["flash_api_key"] = new_api_key
    return RedirectResponse(
        url=f"/orgs/{org_slug}/projects/{project_id}/api-key",
        status_code=303,
    )


@router.get("/orgs/{org_slug}/projects/{project_id}/edit", response_class=HTMLResponse)
async def edit_project_page(
    request: Request,
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> HTMLResponse:
    """Show edit project form."""
    project = await _get_org_project(session, project_id, membership.organization_id)
    installation, repos, repo_error = await get_installation_repos(
        session, membership.organization_id
    )
    decrypted = get_anthropic_api_key(project, get_settings().encryption_key)
    anthropic_key_masked = mask_anthropic_api_key(decrypted) if decrypted else None
    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "project": project,
            "title": "Edit Project",
            "user": membership.user,
            "org_slug": org_slug,
            "installation": installation,
            "repos": repos,
            "repo_error": repo_error,
            "anthropic_key_masked": anthropic_key_masked,
        },
    )


@router.post("/orgs/{org_slug}/projects/{project_id}")
async def update_project_action(
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
    name: str = Form(...),
    github_repo_full_name: str = Form(...),
    default_branch: str = Form("main"),
    error_threshold: int = Form(10),
    anthropic_api_key: str = Form(""),
    clear_anthropic_key: str = Form(""),
) -> RedirectResponse:
    """Update a project and redirect to list."""
    project = await _get_org_project(session, project_id, membership.organization_id)

    _installation, repos, _error = await get_installation_repos(
        session, membership.organization_id
    )
    if repos and github_repo_full_name not in repos:
        raise HTTPException(
            status_code=400, detail="Repository not accessible via GitHub App"
        )

    github_repo_url = f"https://github.com/{github_repo_full_name}"
    project.name = name
    project.github_repo_url = github_repo_url
    project.default_branch = default_branch
    project.error_threshold = error_threshold
    if clear_anthropic_key:
        clear_anthropic_api_key(project)
    elif anthropic_api_key:
        set_anthropic_api_key(project, anthropic_api_key, get_settings().encryption_key)
    await session.flush()
    return RedirectResponse(url=f"/orgs/{org_slug}/projects", status_code=303)


@router.post("/orgs/{org_slug}/projects/{project_id}/delete")
async def delete_project_action(
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> RedirectResponse:
    """Delete a project and redirect to list."""
    project = await _get_org_project(session, project_id, membership.organization_id)
    await session.delete(project)
    await session.flush()
    logger.info("project_deleted", project_id=str(project_id))
    return RedirectResponse(url=f"/orgs/{org_slug}/projects", status_code=303)
