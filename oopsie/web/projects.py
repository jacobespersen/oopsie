"""Web UI routes for projects (HTML forms)."""

import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from oopsie.api.deps import get_session
from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.project import Project
from oopsie.queue import enqueue_fix_job
from oopsie.services.fix_service import (
    get_fix_attempt_status_for_errors,
    get_fix_attempts_for_error,
)
from oopsie.utils.encryption import encrypt_value, hash_api_key

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/projects", response_class=HTMLResponse)
async def list_projects_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """List all projects."""
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="projects/list.html",
        context={"projects": projects},
    )


@router.get("/projects/new", response_class=HTMLResponse)
async def new_project_page(request: Request):
    """Show create project form."""
    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={"project": None, "title": "New Project"},
    )


@router.post("/projects")
async def create_project_action(
    request: Request,
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    github_repo_url: str = Form(...),
    github_token: str = Form(...),
    default_branch: str = Form("main"),
    error_threshold: int = Form(10),
):
    """Create a project and redirect to list."""
    settings = get_settings()
    api_key = secrets.token_urlsafe(32)
    project = Project(
        name=name,
        github_repo_url=github_repo_url,
        github_token_encrypted=encrypt_value(github_token, settings.encryption_key),
        default_branch=default_branch,
        error_threshold=error_threshold,
        api_key_hash=hash_api_key(api_key),
    )
    session.add(project)
    await session.flush()
    logger.info("project_created", project_id=str(project.id), name=name)
    # Redirect to a "created" page that shows the API key, then link to list
    return RedirectResponse(
        url=f"/projects/{project.id}/created?api_key={api_key}",
        status_code=303,
    )


@router.get("/projects/{project_id}/created", response_class=HTMLResponse)
async def project_created_page(
    request: Request,
    project_id: uuid.UUID,
    api_key: str,
):
    """Show API key after create (only time it's visible)."""
    return templates.TemplateResponse(
        request=request,
        name="projects/created.html",
        context={"project_id": project_id, "api_key": api_key},
    )


@router.get("/projects/{project_id}/api-key", response_class=HTMLResponse)
async def project_api_key_page(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    api_key: str | None = None,
):
    """Show API key for a project. api_key query param shows newly regenerated key."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        request=request,
        name="projects/api_key.html",
        context={
            "project": project,
            "api_key": api_key,
            "just_regenerated": api_key is not None,
        },
    )


@router.post("/projects/{project_id}/regenerate-api-key")
async def regenerate_api_key_action(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Regenerate API key and redirect to show the new key."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    new_api_key = secrets.token_urlsafe(32)
    project.api_key_hash = hash_api_key(new_api_key)
    await session.flush()
    logger.info("api_key_regenerated", project_id=str(project_id))
    return RedirectResponse(
        url=f"/projects/{project_id}/api-key?api_key={new_api_key}",
        status_code=303,
    )


@router.get("/projects/{project_id}/errors", response_class=HTMLResponse)
async def project_errors_page(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Show errors for a project."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    errors_result = await session.execute(
        select(Error)
        .where(Error.project_id == project_id)
        .order_by(Error.last_seen_at.desc())
    )
    errors = errors_result.scalars().all()

    error_ids = [e.id for e in errors]
    fix_statuses = (
        await get_fix_attempt_status_for_errors(session, error_ids) if error_ids else {}
    )

    return templates.TemplateResponse(
        request=request,
        name="projects/errors.html",
        context={"project": project, "errors": errors, "fix_statuses": fix_statuses},
    )


@router.get("/projects/{project_id}/errors/{error_id}", response_class=HTMLResponse)
async def error_show_page(
    request: Request,
    project_id: uuid.UUID,
    error_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Show details for a single error."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    err_result = await session.execute(
        select(Error).where(Error.id == error_id, Error.project_id == project_id)
    )
    error = err_result.scalar_one_or_none()
    if not error:
        raise HTTPException(status_code=404, detail="Error not found")

    fix_attempts = await get_fix_attempts_for_error(session, error_id)

    return templates.TemplateResponse(
        request=request,
        name="projects/error_show.html",
        context={"project": project, "error": error, "fix_attempts": fix_attempts},
    )


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
async def edit_project_page(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Show edit project form."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        request=request,
        name="projects/form.html",
        context={"project": project, "title": "Edit Project"},
    )


@router.post("/projects/{project_id}")
async def update_project_action(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    github_repo_url: str = Form(...),
    github_token: str = Form(""),  # optional - leave blank to keep
    default_branch: str = Form("main"),
    error_threshold: int = Form(10),
):
    """Update a project and redirect to list."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.name = name
    project.github_repo_url = github_repo_url
    if github_token:
        settings = get_settings()
        project.github_token_encrypted = encrypt_value(
            github_token, settings.encryption_key
        )
    project.default_branch = default_branch
    project.error_threshold = error_threshold
    await session.flush()
    return RedirectResponse(url="/projects", status_code=303)


@router.post("/projects/{project_id}/delete")
async def delete_project_action(
    request: Request,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project and redirect to list."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.flush()
    logger.info("project_deleted", project_id=str(project_id))
    return RedirectResponse(url="/projects", status_code=303)


@router.post("/projects/{project_id}/errors/{error_id}/fix")
async def trigger_fix_action(
    request: Request,
    project_id: uuid.UUID,
    error_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Enqueue a fix job for an error and redirect back to errors page."""
    proj_result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    err_result = await session.execute(
        select(Error).where(Error.id == error_id, Error.project_id == project_id)
    )
    error = err_result.scalar_one_or_none()
    if not error:
        raise HTTPException(status_code=404, detail="Error not found")

    if error.status != ErrorStatus.OPEN:
        raise HTTPException(status_code=400, detail="Error is not in OPEN status")

    # if await has_active_fix_attempt(session, error_id):
    #     raise HTTPException(
    #         status_code=409, detail="A fix attempt is already in progress"
    #     )

    await enqueue_fix_job(str(error_id), str(project_id))
    logger.info(
        "fix_triggered_via_ui",
        error_id=str(error_id),
        project_id=str(project_id),
    )

    return RedirectResponse(
        url=f"/projects/{project_id}/errors",
        status_code=303,
    )
