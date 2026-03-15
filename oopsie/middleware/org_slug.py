"""Lightweight middleware to set request.state.org_slug from the session cookie.

Reads the session token from the cookie, looks up org_slug in Redis (no DB
query), and sets request.state.org_slug so that templates can access it via
the Jinja2 context processor.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from oopsie.session import get_session_org_slug


class OrgSlugMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        org_slug: str | None = None
        session_token = request.cookies.get("session_id")
        if session_token:
            org_slug = await get_session_org_slug(session_token)
        request.state.org_slug = org_slug
        return await call_next(request)
