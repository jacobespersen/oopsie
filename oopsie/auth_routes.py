"""Authentication routes: login, callback, logout, refresh."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.auth import (
    AUTH_COOKIE_OPTS,
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    get_google_oauth_client,
    get_user_default_redirect,
    resolve_or_register_user,
    revoke_token,
)
from oopsie.config import get_settings
from oopsie.deps import get_session
from oopsie.logging import logger
from oopsie.models.user import User
from oopsie.web import templates

router = APIRouter(prefix="/auth")


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    settings = get_settings()
    response.set_cookie(
        "access_token", access_token, **AUTH_COOKIE_OPTS, secure=settings.cookie_secure
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        **AUTH_COOKIE_OPTS,
        secure=settings.cookie_secure,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


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
    """Handle Google OAuth callback: exchange code, upsert user, set cookies."""
    # Exchange the authorization code for user info
    google = get_google_oauth_client()
    token = await google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(
            status_code=400, detail="Could not retrieve user info from Google"
        )

    # Register or authenticate the user (invitation-gated for new users)
    try:
        user, _memberships = await resolve_or_register_user(session, user_info)
    except ValueError:
        return RedirectResponse(url="/auth/login?error=no_invitation", status_code=303)

    # Issue JWT tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Redirect to the user's default org
    redirect_url = await get_user_default_redirect(session, user.id)
    response: Response = RedirectResponse(url=redirect_url, status_code=303)
    _set_auth_cookies(response, access_token, refresh_token)
    logger.info("user_logged_in", user_id=str(user.id), email=user.email)
    return response


@router.post("/refresh")
async def refresh_token_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Issue new access + refresh tokens, rotating the refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = await decode_jwt_token(refresh_token, session)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    exp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp, tz=UTC) if exp else datetime.now(tz=UTC)
    await revoke_token(session, payload["jti"], expires_at)

    result = await session.execute(
        select(User).where(User.id == uuid.UUID(payload["sub"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)

    response = Response(content='{"status":"ok"}', media_type="application/json")
    _set_auth_cookies(response, new_access, new_refresh)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke access + refresh tokens, clear cookies, redirect to login."""
    # Best-effort revocation — don't fail on invalid tokens
    user_id: str | None = None
    for cookie_name in ("access_token", "refresh_token"):
        token = request.cookies.get(cookie_name)
        if token:
            try:
                payload = await decode_jwt_token(token, session)
                if cookie_name == "access_token":
                    user_id = payload.get("sub")
                exp = payload.get("exp")
                expires_at = (
                    datetime.fromtimestamp(exp, tz=UTC) if exp else datetime.now(tz=UTC)
                )
                await revoke_token(session, payload["jti"], expires_at)
            except ValueError:
                pass

    if user_id:
        logger.info("user_logged_out", user_id=user_id)

    response: Response = RedirectResponse(url="/auth/login", status_code=303)
    _clear_auth_cookies(response)
    return response
