"""Public landing page and signup request form."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.exceptions import AlreadyHasOrganizationError
from oopsie.models.user import User
from oopsie.routers.dependencies import get_optional_user, get_session
from oopsie.routers.web import templates
from oopsie.services.signup_request_service import create_signup_request
from oopsie.session import get_session_org_slug

router = APIRouter()


class SignupRequestForm(BaseModel):
    """Validation schema for the signup request form."""

    name: str = Field(max_length=255)
    email: EmailStr
    org_name: str = Field(max_length=255)
    reason: str = Field(max_length=2000)


def _extract_field_errors(exc: ValidationError) -> dict[str, str]:
    """Extract a {field_name: message} dict from a Pydantic ValidationError."""
    errors: dict[str, str] = {}
    for err in exc.errors():
        # loc is a tuple like ("name",); use the first element as field name
        field = str(err["loc"][0]) if err["loc"] else "unknown"
        errors[field] = err["msg"]
    return errors


@router.get("/", response_class=HTMLResponse, response_model=None)
async def landing_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    """Public landing page — redirects logged-in users to their org."""
    if user is not None:
        # org_slug is always cached in the Redis session at login
        token = request.cookies.get("session_id")
        if token:
            org_slug = await get_session_org_slug(token)
            if org_slug:
                return RedirectResponse(
                    url=f"/orgs/{org_slug}/projects", status_code=302
                )

    return templates.TemplateResponse(
        request=request,
        name="landing.html",
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
    field_errors: dict[str, str] = {}

    # Validate form data against the Pydantic model before processing
    try:
        SignupRequestForm(name=name, email=email, org_name=org_name, reason=reason)
    except ValidationError as exc:
        field_errors = _extract_field_errors(exc)
        return templates.TemplateResponse(
            request=request,
            name="landing.html",
            context={
                "user": None,
                "field_errors": field_errors,
                "form_name": name,
                "form_email": email,
                "form_org_name": org_name,
                "form_reason": reason,
            },
        )

    try:
        await create_signup_request(
            session, name=name, email=email, org_name=org_name, reason=reason
        )
        success = True
    except (ValueError, AlreadyHasOrganizationError) as exc:
        error = str(exc)
    except IntegrityError:
        # Race condition: concurrent submission passed the app-level check but
        # hit the unique partial index on (email) WHERE status = 'pending'.
        await session.rollback()
        error = "A signup request for this email is already pending review."

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
