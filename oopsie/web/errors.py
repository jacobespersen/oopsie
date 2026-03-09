"""Web UI routes for error viewing and fix triggering."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.deps import RequireRole, get_session
from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.membership import MemberRole, Membership
from oopsie.queue import enqueue_fix_job
from oopsie.services.fix_service import (
    get_fix_attempt_status_for_errors,
    get_fix_attempts_for_error,
)
from oopsie.web import templates
from oopsie.web.projects import _get_org_project

router = APIRouter()


@router.get(
    "/orgs/{org_slug}/projects/{project_id}/errors", response_class=HTMLResponse
)
async def project_errors_page(
    request: Request,
    org_slug: str,
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.member)),
) -> HTMLResponse:
    """Show errors for a project."""
    project = await _get_org_project(session, project_id, membership.organization_id)

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
        context={
            "project": project,
            "errors": errors,
            "fix_statuses": fix_statuses,
            "user": membership.user,
            "org_slug": org_slug,
        },
    )


@router.get(
    "/orgs/{org_slug}/projects/{project_id}/errors/{error_id}",
    response_class=HTMLResponse,
)
async def error_show_page(
    request: Request,
    org_slug: str,
    project_id: uuid.UUID,
    error_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.member)),
) -> HTMLResponse:
    """Show details for a single error."""
    project = await _get_org_project(session, project_id, membership.organization_id)

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
        context={
            "project": project,
            "error": error,
            "fix_attempts": fix_attempts,
            "user": membership.user,
            "org_slug": org_slug,
        },
    )


@router.post("/orgs/{org_slug}/projects/{project_id}/errors/{error_id}/fix")
async def trigger_fix_action(
    org_slug: str,
    project_id: uuid.UUID,
    error_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.member)),
) -> RedirectResponse:
    """Enqueue a fix job for an error and redirect back to errors page."""
    project = await _get_org_project(session, project_id, membership.organization_id)

    err_result = await session.execute(
        select(Error).where(Error.id == error_id, Error.project_id == project.id)
    )
    error = err_result.scalar_one_or_none()
    if not error:
        raise HTTPException(status_code=404, detail="Error not found")

    if error.status != ErrorStatus.OPEN:
        raise HTTPException(status_code=400, detail="Error is not in OPEN status")

    await enqueue_fix_job(str(error_id), str(project_id))
    logger.info(
        "fix_triggered_via_ui",
        error_id=str(error_id),
        project_id=str(project_id),
    )

    return RedirectResponse(
        url=f"/orgs/{org_slug}/projects/{project_id}/errors",
        status_code=303,
    )
