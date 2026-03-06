"""Authentication routes: login, callback, logout, refresh."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from oopsie.api.deps import get_session
from oopsie.auth import (
    accept_invitation,
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    get_google_oauth_client,
    get_pending_invitation,
    revoke_token,
    upsert_user,
)
from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.user import User

router = APIRouter(prefix="/auth")
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_COOKIE_OPTS: dict[str, Any] = {
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    settings = get_settings()
    response.set_cookie(
        "access_token", access_token, **_COOKIE_OPTS, secure=settings.cookie_secure
    )
    response.set_cookie(
        "refresh_token", refresh_token, **_COOKIE_OPTS, secure=settings.cookie_secure
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
    return await google.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Handle Google OAuth callback: exchange code, upsert user, set cookies."""
    google = get_google_oauth_client()
    token = await google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(
            status_code=400, detail="Could not retrieve user info from Google"
        )

    from sqlalchemy import select

    from oopsie.models.user import User as _User

    # Check if user already exists in DB
    google_sub = user_info["sub"]
    result = await session.execute(select(_User).where(_User.google_sub == google_sub))
    existing = result.scalar_one_or_none()

    invitation = None
    if existing is None:
        # New user — require a pending invitation
        invitation = await get_pending_invitation(session, user_info["email"])
        if invitation is None:
            return RedirectResponse(
                url="/auth/login?error=no_invitation", status_code=303
            )

    user = await upsert_user(session, user_info)

    if invitation is not None:
        await accept_invitation(session, invitation, user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Resolve user's org for redirect
    from sqlalchemy.orm import joinedload as _joinedload

    from oopsie.models.membership import Membership as _Membership

    mem_result = await session.execute(
        select(_Membership)
        .options(_joinedload(_Membership.organization))
        .where(_Membership.user_id == user.id)
        .limit(1)
    )
    mem = mem_result.scalar_one_or_none()
    if mem and mem.organization:
        redirect_url = f"/orgs/{mem.organization.slug}/projects"
    else:
        redirect_url = "/auth/login?error=no_organization"

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
