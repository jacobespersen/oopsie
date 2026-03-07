"""Web UI routes for org members and invitations."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from oopsie.api.deps import RequireRole, get_current_user, get_session
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.user import User
from oopsie.services.invitation_service import (
    create_invitation,
    list_invitations,
    revoke_invitation,
)
from oopsie.services.membership_service import (
    list_members,
    remove_member,
    update_member_role,
)

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/orgs/{org_slug}/members", response_class=HTMLResponse)
async def members_list_page(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.MEMBER)),
):
    """Show members and pending invitations for the org."""
    members = await list_members(session, organization_id=membership.organization_id)
    invitations = await list_invitations(
        session, organization_id=membership.organization_id
    )
    return templates.TemplateResponse(
        request=request,
        name="members/list.html",
        context={
            "org_slug": org_slug,
            "members": members,
            "invitations": invitations,
            "current_membership": membership,
            "user": current_user,
            "MemberRole": MemberRole,
        },
    )


@router.post("/orgs/{org_slug}/members/invite")
async def invite_member_action(
    request: Request,
    org_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
    email: str = Form(...),
    role: str = Form(...),
):
    """Create an invitation and redirect back to members page."""
    try:
        member_role = MemberRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    try:
        await create_invitation(
            session,
            organization_id=membership.organization_id,
            email=email,
            role=member_role,
            invited_by_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return RedirectResponse(url=f"/orgs/{org_slug}/members", status_code=303)


@router.post("/orgs/{org_slug}/members/invitations/{invitation_id}/revoke")
async def revoke_invitation_action(
    request: Request,
    org_slug: str,
    invitation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
):
    """Revoke a pending invitation and redirect back to members page."""
    try:
        await revoke_invitation(
            session,
            invitation_id=invitation_id,
            organization_id=membership.organization_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RedirectResponse(url=f"/orgs/{org_slug}/members", status_code=303)


@router.post("/orgs/{org_slug}/members/{membership_id}/role")
async def update_member_role_action(
    request: Request,
    org_slug: str,
    membership_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
    role: str = Form(...),
):
    """Update a member's role and redirect back to members page."""
    try:
        new_role = MemberRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    try:
        await update_member_role(
            session,
            membership_id=membership_id,
            organization_id=membership.organization_id,
            new_role=new_role,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RedirectResponse(url=f"/orgs/{org_slug}/members", status_code=303)


@router.post("/orgs/{org_slug}/members/{membership_id}/remove")
async def remove_member_action(
    request: Request,
    org_slug: str,
    membership_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(RequireRole(MemberRole.ADMIN)),
):
    """Remove a member from the org and redirect back to members page."""
    try:
        await remove_member(
            session,
            membership_id=membership_id,
            organization_id=membership.organization_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RedirectResponse(url=f"/orgs/{org_slug}/members", status_code=303)
