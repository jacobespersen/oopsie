"""Platform admin routes for managing signup requests."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.database import get_session
from oopsie.deps import require_platform_admin
from oopsie.exceptions import AlreadyHasOrganizationError
from oopsie.logging import logger
from oopsie.models.signup_request import SignupRequestStatus
from oopsie.models.user import User
from oopsie.services.signup_request_service import (
    approve_signup_request,
    list_signup_requests,
    reject_signup_request,
)
from oopsie.web import templates

router = APIRouter()


@router.get("/admin/signup-requests", response_class=HTMLResponse)
async def signup_requests_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
    status: str = "pending",
) -> HTMLResponse:
    """List signup requests for platform admin review."""
    try:
        filter_status = SignupRequestStatus(status)
    except ValueError:
        valid = [s.value for s in SignupRequestStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: {valid}",
        )

    requests_list = await list_signup_requests(session, status=filter_status)

    return templates.TemplateResponse(
        request=request,
        name="admin/signup_requests.html",
        context={
            "user": current_user,
            "signup_requests": requests_list,
            "current_status": filter_status,
            "SignupRequestStatus": SignupRequestStatus,
        },
    )


@router.post("/admin/signup-requests/{request_id}/approve")
async def approve_request(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
) -> RedirectResponse:
    """Approve a signup request and create an org-creation invitation."""
    try:
        await approve_signup_request(
            session,
            signup_request_id=request_id,
            reviewer_id=current_user.id,
        )
    except LookupError as exc:
        logger.warning(
            "approve_request_not_found",
            request_id=str(request_id),
            error=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, AlreadyHasOrganizationError) as exc:
        logger.warning(
            "approve_request_conflict",
            request_id=str(request_id),
            error=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc))

    return RedirectResponse(
        url="/admin/signup-requests?status=pending", status_code=303
    )


@router.post("/admin/signup-requests/{request_id}/reject")
async def reject_request(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_platform_admin),
) -> RedirectResponse:
    """Reject a signup request."""
    try:
        await reject_signup_request(
            session,
            signup_request_id=request_id,
            reviewer_id=current_user.id,
        )
    except LookupError as exc:
        logger.warning(
            "reject_request_not_found",
            request_id=str(request_id),
            error=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        logger.warning(
            "reject_request_conflict",
            request_id=str(request_id),
            error=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc))

    return RedirectResponse(
        url="/admin/signup-requests?status=pending", status_code=303
    )
