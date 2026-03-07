"""Bootstrap service — seeds the first org and admin invitation on first deploy.

Called during application startup when ADMIN_EMAIL is configured.  Creates the
default organization and an OWNER invitation so the first admin can sign up
via Google OAuth without a manual database insert.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole
from oopsie.models.organization import Organization


def _slugify(name: str) -> str:
    """Convert an organization name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug or "default"


async def bootstrap_if_needed(
    session: AsyncSession,
    admin_email: str,
    org_name: str,
) -> None:
    """Create the default org and owner invitation when no orgs exist.

    This is a no-op if:
    - admin_email is empty, or
    - at least one organization already exists.
    """
    if not admin_email:
        return

    # Only bootstrap on the very first deploy — once any org exists, skip.
    org_count = await session.scalar(select(func.count()).select_from(Organization))
    if org_count and org_count > 0:
        return

    # Create the seed organization from the configured ORG_NAME.
    slug = _slugify(org_name)
    org = Organization(name=org_name, slug=slug)
    session.add(org)
    await session.flush()

    # Guard against duplicate invitations (idempotency for retried startups).
    existing = await session.scalar(
        select(func.count())
        .select_from(Invitation)
        .where(
            Invitation.organization_id == org.id,
            Invitation.email == admin_email,
        )
    )
    if existing and existing > 0:
        return

    # Seed an OWNER invitation for the admin email so they can register.
    invitation = Invitation(
        organization_id=org.id,
        email=admin_email,
        role=MemberRole.OWNER,
        invited_by_id=None,  # No inviter — system-generated bootstrap
    )
    session.add(invitation)
    await session.flush()

    logger.info(
        "bootstrap_complete",
        org_name=org_name,
        org_id=str(org.id),
        admin_email=admin_email,
    )
