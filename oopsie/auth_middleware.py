"""Pure ASGI middleware for transparent JWT token refresh.

Intercepts web requests and refreshes expired/near-expiry access tokens
using the refresh token cookie. Skips API routes, auth routes, static
files, and health checks.
"""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from oopsie.auth import (
    AUTH_COOKIE_OPTS,
    decode_jwt_allow_expired,
    rotate_tokens,
)
from oopsie.config import get_settings
from oopsie.logging import logger

# Paths where the middleware should not attempt token refresh
_SKIP_PREFIXES = ("/auth/", "/static/", "/api/v1/")
_SKIP_EXACT = ("/health",)

# Refresh proactively when the access token expires within this window
_NEAR_EXPIRY = timedelta(minutes=5)


def _parse_cookies(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Extract cookies from raw ASGI headers."""
    cookies: dict[str, str] = {}
    for key, value in headers:
        if key == b"cookie":
            cookie = SimpleCookie(value.decode("latin-1"))
            for morsel_name, morsel in cookie.items():
                cookies[morsel_name] = morsel.value
    return cookies


def _should_skip(path: str) -> bool:
    """Return True if the middleware should not process this path."""
    if path in _SKIP_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _build_set_cookie_header(
    name: str, value: str, *, delete: bool = False
) -> tuple[bytes, bytes]:
    """Build a raw Set-Cookie header for ASGI injection."""
    settings = get_settings()
    if delete:
        parts = [f"{name}=", "Path=/", "Max-Age=0"]
    else:
        parts = [
            f"{name}={value}",
            f"Path={AUTH_COOKIE_OPTS['path']}",
            "HttpOnly" if AUTH_COOKIE_OPTS["httponly"] else "",
            f"SameSite={AUTH_COOKIE_OPTS['samesite']}",
        ]
        if settings.cookie_secure:
            parts.append("Secure")
    header_value = "; ".join(p for p in parts if p)
    return (b"set-cookie", header_value.encode("latin-1"))


def _clear_cookie_headers() -> list[tuple[bytes, bytes]]:
    """Return Set-Cookie headers that delete both auth cookies."""
    return [
        _build_set_cookie_header("access_token", "", delete=True),
        _build_set_cookie_header("refresh_token", "", delete=True),
    ]


def _replace_cookie_in_headers(
    headers: list[tuple[bytes, bytes]],
    cookies: dict[str, str],
) -> list[tuple[bytes, bytes]]:
    """Build a new headers list with the updated Cookie header."""
    # Rebuild the Cookie header from the modified cookies dict
    cookie_value = "; ".join(f"{k}={v}" for k, v in cookies.items())
    new_headers = []
    for key, value in headers:
        if key == b"cookie":
            continue  # skip old cookie header
        new_headers.append((key, value))
    new_headers.append((b"cookie", cookie_value.encode("latin-1")))
    return new_headers


class TokenRefreshMiddleware:
    """ASGI middleware that transparently refreshes JWT tokens.

    When the access token is expired or near expiry and a valid refresh
    token is present, this middleware:
    1. Rotates both tokens (revokes old refresh, issues new pair)
    2. Updates the request Cookie header so downstream handlers see the new access token
    3. Injects Set-Cookie headers into the response so the browser stores the new tokens
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if _should_skip(path):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        cookies = _parse_cookies(headers)
        access_token = cookies.get("access_token")

        if not access_token:
            await self.app(scope, receive, send)
            return

        result = await self._maybe_refresh(access_token, cookies)

        if result is None:
            await self.app(scope, receive, send)
            return

        response_headers, new_cookies = result

        # Update the request scope so downstream handlers see the new access token
        scope["headers"] = _replace_cookie_in_headers(headers, new_cookies)

        # Wrap send to inject Set-Cookie headers into the response
        async def send_with_cookies(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.extend(response_headers)
                message["headers"] = existing_headers
            await send(message)

        await self.app(scope, receive, send_with_cookies)

    async def _maybe_refresh(
        self,
        access_token: str,
        cookies: dict[str, str],
    ) -> tuple[list[tuple[bytes, bytes]], dict[str, str]] | None:
        """Attempt to refresh tokens if the access token is expired or near expiry.

        Returns (response_headers, updated_cookies) or None if no refresh needed.
        On failure, returns (clear_headers, original_cookies) to delete stale cookies.
        """
        try:
            access_payload = decode_jwt_allow_expired(access_token)
        except ValueError:
            logger.info("token_refresh_invalid_access_token")
            return _clear_cookie_headers(), cookies

        if access_payload.get("type") != "access":
            # Wrong token type in the access_token cookie — pass through,
            # let get_current_user reject it
            return None

        exp_timestamp = access_payload.get("exp")
        if exp_timestamp is None:
            logger.warning("token_refresh_missing_exp", sub=access_payload.get("sub"))
            return None

        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)
        now = datetime.now(tz=UTC)
        if exp_dt - now > _NEAR_EXPIRY:
            # Token is still fresh — no refresh needed
            return None

        refresh_token = cookies.get("refresh_token")
        if not refresh_token:
            logger.info("token_refresh_no_refresh_cookie")
            return _clear_cookie_headers(), cookies

        return await self._do_refresh(refresh_token, cookies)

    async def _do_refresh(
        self, refresh_token: str, cookies: dict[str, str]
    ) -> tuple[list[tuple[bytes, bytes]], dict[str, str]] | None:
        """Validate refresh token, rotate tokens, return headers + cookies."""
        from oopsie.database import async_session_factory

        try:
            async with async_session_factory() as session:
                async with session.begin():
                    try:
                        new_access, new_refresh = await rotate_tokens(
                            session, refresh_token
                        )
                    except ValueError as exc:
                        logger.info("token_refresh_failed", reason=str(exc))
                        return _clear_cookie_headers(), cookies

                    updated_cookies = {
                        **cookies,
                        "access_token": new_access,
                        "refresh_token": new_refresh,
                    }

                    response_headers = [
                        _build_set_cookie_header("access_token", new_access),
                        _build_set_cookie_header("refresh_token", new_refresh),
                    ]

                    return response_headers, updated_cookies
        except (SQLAlchemyError, OSError, ConnectionRefusedError) as exc:
            logger.warning(
                "token_refresh_db_error",
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None
