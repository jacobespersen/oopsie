"""GitHub App install flow and webhook routes.

Routes span three path prefixes:
  - /orgs/{org_slug}/github/...  — install redirect (requires org context)
  - /github/...                  — OAuth-style callback (org read from session)
  - /webhooks/github             — incoming webhook from GitHub (no user auth)
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.deps import RequireRole, get_current_user, get_session
from oopsie.logging import logger
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.user import User
from oopsie.services.github_app_service import verify_webhook
from oopsie.services.github_installation_service import (
    handle_installation_event,
    handle_pr_event,
    process_install_callback,
)

router = APIRouter()


@router.get("/orgs/{org_slug}/github/install")
async def github_install_redirect(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
) -> RedirectResponse:
    """Redirect to GitHub App installation page with CSRF state.

    Stores 'github_install_state' and 'github_install_org_slug' in the session
    so the callback (which has no org in its path) can validate state and
    recover the org slug.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    # Store both the CSRF state and the org slug for the stateless callback route
    request.session["github_install_state"] = state
    request.session["github_install_org_slug"] = org_slug
    install_url = (
        f"https://github.com/apps/{settings.github_app_slug}"
        f"/installations/new?state={state}"
    )
    return RedirectResponse(install_url, status_code=303)


@router.get("/github/callback")
async def github_install_callback(
    request: Request,
    installation_id: int,
    setup_action: str,
    state: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    """Handle GitHub App installation callback.

    Validates the CSRF state, delegates to the service layer for org lookup
    and installation upsert, then redirects to the org's settings page.
    """
    expected_state = request.session.pop("github_install_state", None)
    org_slug = request.session.pop("github_install_org_slug", None)

    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="State mismatch")

    if not org_slug:
        raise HTTPException(status_code=400, detail="Missing org context in session")

    try:
        await process_install_callback(
            session,
            org_slug=org_slug,
            github_installation_id=installation_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Organization not found")

    logger.info(
        "github_install_callback",
        org_slug=org_slug,
        installation_id=installation_id,
        setup_action=setup_action,
    )

    return RedirectResponse(url=f"/orgs/{org_slug}/settings", status_code=303)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Receive and dispatch GitHub webhook events.

    Signature is verified using HMAC-SHA256 before any dispatch. Returns 403
    on invalid/missing signature. Returns 200 for all valid-signature requests,
    including unknown event types (GitHub may send events we don't care about).
    """
    # Read raw body first — must happen before any JSON parsing
    raw_body = await request.body()

    settings = get_settings()
    if not settings.github_webhook_secret:
        logger.error("webhook_rejected_secret_not_configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing signature header")

    if not verify_webhook(settings.github_webhook_secret, raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event_name = request.headers.get("X-GitHub-Event", "")

    try:
        if event_name == "installation":
            await handle_installation_event(session, raw_body)
        elif event_name == "pull_request":
            await handle_pr_event(session, raw_body)
        else:
            logger.info("webhook_event_ignored", event_name=event_name)
    except Exception:
        logger.error(
            "webhook_event_processing_failed",
            event_name=event_name,
            exc_info=True,
        )
        return JSONResponse({"status": "error", "detail": "processing failed"})

    return JSONResponse({"status": "ok"})
