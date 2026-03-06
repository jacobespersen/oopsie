"""JWT creation/decoding and Google OAuth helpers."""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from oopsie.models.invitation import Invitation
    from oopsie.models.membership import Membership

import jwt
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.config import get_settings
from oopsie.logging import logger
from oopsie.models.revoked_token import RevokedToken
from oopsie.models.user import User


@lru_cache(maxsize=1)
def _build_google_client() -> Any:
    """Create and cache the authlib Google OAuth client."""
    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.google


def get_google_oauth_client() -> Any:
    """Return the Google OAuth client (cached after first call)."""
    return _build_google_client()


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    """Encode a short-lived JWT access token."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_expiry_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Encode a long-lived JWT refresh token."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_refresh_expiry_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode a JWT token without DB checks. Raises ValueError on invalid input."""
    settings = get_settings()
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")


async def decode_jwt_token(token: str, session: AsyncSession) -> dict[str, Any]:
    """Decode JWT and verify it has not been revoked."""
    payload = decode_jwt(token)
    jti = payload.get("jti")
    if jti:
        result = await session.execute(
            select(RevokedToken).where(RevokedToken.jti == jti)
        )
        if result.scalar_one_or_none():
            raise ValueError("Token has been revoked")
    return payload


async def revoke_token(session: AsyncSession, jti: str, expires_at: datetime) -> None:
    """Add a token JTI to the deny list."""
    revoked = RevokedToken(jti=jti, expires_at=expires_at)
    session.add(revoked)
    await session.flush()
    logger.info("token_revoked", jti=jti)


async def upsert_user(session: AsyncSession, google_user_info: dict[str, Any]) -> User:
    """Find or create a user from Google userinfo. Updates fields if changed."""
    google_sub = google_user_info["sub"]
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=google_user_info["email"],
            name=google_user_info.get("name", google_user_info["email"]),
            google_sub=google_sub,
            avatar_url=google_user_info.get("picture"),
        )
        session.add(user)
        await session.flush()
        logger.info("user_created", user_id=str(user.id), email=user.email)
    else:
        user.email = google_user_info["email"]
        user.name = google_user_info.get("name", user.name)
        user.avatar_url = google_user_info.get("picture", user.avatar_url)
        await session.flush()
        logger.info("user_updated", user_id=str(user.id), email=user.email)

    return user


async def get_pending_invitation(
    session: AsyncSession, email: str
) -> "Invitation | None":
    """Return a pending invitation for the given email, or None."""
    from oopsie.models.invitation import Invitation, InvitationStatus

    result = await session.execute(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    return result.scalar_one_or_none()


async def accept_invitation(
    session: AsyncSession, invitation: "Invitation", user: User
) -> "Membership":
    """Mark an invitation accepted and create the corresponding Membership."""
    from oopsie.models.invitation import InvitationStatus
    from oopsie.models.membership import Membership

    invitation.status = InvitationStatus.ACCEPTED
    membership = Membership(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=invitation.role,
    )
    session.add(membership)
    await session.flush()
    logger.info(
        "invitation_accepted",
        invitation_id=str(invitation.id),
        user_id=str(user.id),
        role=invitation.role.value,
    )
    return membership
