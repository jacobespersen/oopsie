"""Web UI routes for projects (HTML forms)."""

import secrets
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.deps import RequireRole, get_session
from oopsie.logging import logger
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.project import Project
from oopsie.services.exceptions import GitHubApiError
from oopsie.services.github_app_service import list_installation_repos
from oopsie.utils.encryption import hash_api_key
from oopsie.web import templates

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


async def _get_installation_repos(
    session: AsyncSession, organization_id: uuid.UUID
) -> tuple[GithubInstallation | None, list[str]]:
    """Fetch the active installation and its accessible repos for an org.

    Returns (installation, repos). If there is no active installation or
    the GitHub API call fails, repos is an empty list.
    """
    result = await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.organization_id == organization_id
        )
    )
    installation = result.scalar_one_or_none()

    if installation and installation.status == InstallationStatus.ACTIVE:
        try:
            repos = await list_installation_repos(installation.github_installation_id)
        except GitHubApiError:
            logger.warning(
                "list_repos_failed_for_project_form",
                organization_id=str(organization_id),
            )
            repos = []
    else:
        repos = []

    return installation, repos


@router.get("/orgs/{org_slug}/projects/new", response_class=HTMLResponse)
async def new_project_page(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> HTMLResponse:
    """Show create project form."""
    installation, repos = await _get_installation_repos(
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
) -> RedirectResponse:
    """Create a project and redirect to the projects list.

    Validates that the submitted repo is accessible via the GitHub App
    installation before creating the project. The github_repo_url is
    derived server-side from the submitted full_name (REPO-02).

    A placeholder API key hash is generated so the project is valid,
    but the key is never exposed. Users generate a visible key via
    the "Generate API Key" action on the project's API key page.
    """
    _installation, repos = await _get_installation_repos(
        session, membership.organization_id
    )
    # Reject repos not in the accessible list — covers both no-installation
    # and repos the GitHub App cannot access (REPO-02 enforcement).
    if github_repo_full_name not in repos:
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
    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={
            "project": project,
            "title": "Edit Project",
            "user": membership.user,
            "org_slug": org_slug,
            # repos/installation not used in edit mode but required by template context
            "installation": None,
            "repos": [],
        },
    )


@router.post("/orgs/{org_slug}/projects/{project_id}")
async def update_project_action(
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
    name: str = Form(...),
    github_repo_url: str = Form(...),
    default_branch: str = Form("main"),
    error_threshold: int = Form(10),
) -> RedirectResponse:
    """Update a project and redirect to list."""
    project = await _get_org_project(session, project_id, membership.organization_id)

    project.name = name
    project.github_repo_url = github_repo_url
    project.default_branch = default_branch
    project.error_threshold = error_threshold
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
