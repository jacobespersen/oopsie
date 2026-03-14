"""Public landing page and signup request form."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.database import get_session
from oopsie.deps import get_optional_user
from oopsie.models.user import User
from oopsie.services.signup_request_service import create_signup_request
from oopsie.web import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse:
    """Public landing page with signup request form."""
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"user": user},
    )


@router.post("/signup-request", response_class=HTMLResponse)
async def submit_signup_request(
    request: Request,
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    email: str = Form(...),
    org_name: str = Form(...),
    reason: str = Form(...),
) -> HTMLResponse:
    """Handle signup request form submission."""
    error = None
    success = False
    try:
        await create_signup_request(
            session, name=name, email=email, org_name=org_name, reason=reason
        )
        success = True
    except ValueError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "user": None,
            "success": success,
            "error": error,
            "form_name": name,
            "form_email": email,
            "form_org_name": org_name,
            "form_reason": reason,
        },
    )
