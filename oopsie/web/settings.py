"""Web UI route for the org settings page.

Consolidates GitHub connection status and member management on one page.
The old /orgs/{slug}/members GET view redirects here (see members.py).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.deps import RequireRole, get_session
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.membership import MemberRole, Membership
from oopsie.services.invitation_service import list_invitations
from oopsie.services.membership_service import list_members
from oopsie.web import templates

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
        },
    )
