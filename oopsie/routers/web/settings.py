"""Web UI route for the org settings page.

Consolidates GitHub connection status and member management on one page.
The old /orgs/{slug}/members GET view redirects here (see members.py).
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.organization import Organization
from oopsie.routers.dependencies import RequireRole, get_session
from oopsie.routers.web import templates
from oopsie.services.anthropic_key_service import (
    clear_anthropic_api_key,
    get_anthropic_api_key,
    mask_anthropic_api_key,
    set_anthropic_api_key,
)
from oopsie.services.invitation_service import list_invitations
from oopsie.services.membership_service import list_members

router = APIRouter()


@router.get("/orgs/{org_slug}/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.member)),
) -> HTMLResponse:
    """Show org settings: GitHub connection status and member management."""
    # Query the most-recent (or only) GitHub installation for this org.
    # Orgs have at most one installation row (unique constraint on organization_id).
    result = await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.organization_id == membership.organization_id
        )
    )
    installation = result.scalar_one_or_none()

    members = await list_members(session, organization_id=membership.organization_id)
    invitations = await list_invitations(
        session, organization_id=membership.organization_id
    )

    # Resolve masked Anthropic key for display
    org = await session.get(Organization, membership.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    settings = get_settings()
    decrypted = get_anthropic_api_key(org, settings.encryption_key)
    anthropic_key_masked = mask_anthropic_api_key(decrypted) if decrypted else None

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "org_slug": org_slug,
            "installation": installation,
            "members": members,
            "invitations": invitations,
            "current_membership": membership,
            "user": membership.user,
            "MemberRole": MemberRole,
            "InstallationStatus": InstallationStatus,
            "anthropic_key_masked": anthropic_key_masked,
        },
    )


@router.post("/orgs/{org_slug}/settings/anthropic-key")
async def update_org_anthropic_key(
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    membership: Membership = Depends(RequireRole(MemberRole.admin)),
    anthropic_api_key: str = Form(""),
    clear: str = Form(""),
) -> RedirectResponse:
    """Set or clear the organization's Anthropic API key."""
    org = await session.get(Organization, membership.organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if clear:
        clear_anthropic_api_key(org)
    elif anthropic_api_key:
        set_anthropic_api_key(org, anthropic_api_key, get_settings().encryption_key)
    # Empty submission with no clear flag → preserve existing key

    await session.flush()
    return RedirectResponse(url=f"/orgs/{org_slug}/settings", status_code=303)
