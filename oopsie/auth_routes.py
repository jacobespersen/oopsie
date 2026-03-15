"""Authentication routes: login, callback, logout."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.auth import get_google_oauth_client, resolve_or_register_user
from oopsie.config import get_settings
from oopsie.deps import get_session
from oopsie.exceptions import NoInvitationError
from oopsie.logging import logger
from oopsie.session import create_session, delete_session, get_session_user_id
from oopsie.web import templates

router = APIRouter(prefix="/auth")


def _set_session_cookie(response: Response, session_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "session_id",
        session_token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie("session_id", path="/")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Show the login page."""
    return templates.TemplateResponse(
        request=request, name="auth/login.html", context={}
    )


@router.get("/login/google")
async def login_google(request: Request) -> Response:
    """Redirect to Google OAuth consent screen."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth is not configured")
    google = get_google_oauth_client()
    redirect_uri = str(request.url_for("auth_callback"))
    response: Response = await google.authorize_redirect(request, redirect_uri)
    return response


@router.get("/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Handle Google OAuth callback: exchange code, upsert user, create session."""
    google = get_google_oauth_client()
    token = await google.authorize_access_token(request)

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(
            status_code=400, detail="Could not retrieve user info from Google"
        )

    # Register or authenticate the user (invitation-gated for new users)
    try:
        user, new_memberships = await resolve_or_register_user(session, user_info)
    except NoInvitationError:
        return RedirectResponse(url="/auth/login?error=no_invitation", status_code=303)

    # Create a Redis session
    session_token = await create_session(user.id)

    # Derive redirect URL from eagerly-loaded memberships.
    # For new users, new_memberships contains just-accepted invitations.
    # For returning users, user.memberships was loaded via joinedload.
    all_memberships = new_memberships or list(user.memberships)
    if all_memberships:
        org_slug = all_memberships[0].organization.slug
        redirect_url = f"/orgs/{org_slug}/projects"
    else:
        redirect_url = "/auth/login?error=no_organization"

    # Return a "Signing you in..." transition page instead of a bare 303
    # redirect. The page shows immediate visual feedback and redirects
    # client-side, eliminating the blank-page flash during the OAuth dance.
    response = templates.TemplateResponse(
        request=request,
        name="auth/signing_in.html",
        context={"redirect_url": redirect_url},
    )
    _set_session_cookie(response, session_token)
    logger.info("user_logged_in", user_id=str(user.id), email=user.email)
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    """Delete session from Redis, clear cookie, redirect to login."""
    session_token = request.cookies.get("session_id")
    user_id: str | None = None

    if session_token:
        # Read user ID before deleting so we can log it
        uid = await get_session_user_id(session_token)
        if uid:
            user_id = str(uid)
        await delete_session(session_token)

    if user_id:
        logger.info("user_logged_out", user_id=user_id)

    response: Response = RedirectResponse(url="/auth/login", status_code=303)
    _clear_session_cookie(response)
    return response
