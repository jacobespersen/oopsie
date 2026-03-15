"""FastAPI app entry point."""

import re
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette_csrf import CSRFMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from oopsie.api.errors import router as errors_router
from oopsie.auth_routes import router as auth_router
from oopsie.config import get_settings
from oopsie.logging import RequestLoggingMiddleware, setup_logging
from oopsie.queue import close_arq_pool
from oopsie.services.bootstrap_service import bootstrap_if_needed
from oopsie.session import close_redis
from oopsie.web.admin import router as admin_router
from oopsie.web.errors import router as web_errors_router
from oopsie.web.github import router as github_router
from oopsie.web.landing import router as landing_router
from oopsie.web.members import router as web_members_router
from oopsie.web.projects import router as web_projects_router
from oopsie.web.settings import router as web_settings_router


class FormCSRFMiddleware(CSRFMiddleware):
    """CSRFMiddleware extended to accept tokens from form fields.

    The upstream starlette-csrf only checks the ``x-csrftoken`` header.
    HTML forms cannot set custom headers, so this subclass also looks for
    the token in URL-encoded form bodies under the ``csrftoken`` field name.
    """

    async def _get_submitted_csrf_token(self, request: Request) -> str | None:
        # Check header first (API / fetch callers)
        header_token = request.headers.get(self.header_name)
        if header_token:
            return header_token

        # Fall back to form body for regular HTML form submissions
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            token = form.get(self.cookie_name)
            # Close the form to release the request body stream so
            # downstream handlers can read it again.
            await form.close()
            if token and isinstance(token, str):
                return token

        return None


_settings = get_settings()
setup_logging(_settings.log_level, _settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run bootstrap on startup, cleanup arq pool on shutdown."""
    from oopsie.database import async_session_factory

    async with async_session_factory() as session:
        async with session.begin():
            await bootstrap_if_needed(
                session,
                admin_email=_settings.admin_email,
                org_name=_settings.org_name,
            )
    yield
    await close_arq_pool()
    await close_redis()


app = FastAPI(
    title="Oopsie",
    description="AI-powered error fix service",
    lifespan=lifespan,
)

# Random secret that only protects transient OAuth state (CSRF nonce).
# Not used for session authentication — sessions live in Redis.
_session_secret = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
app.mount("/static", StaticFiles(directory="static"), name="static")

# CSRF double-submit cookie protection for all state-changing requests.
# Exempt: API routes (use Bearer token auth), /signup-request (public,
# unauthenticated), and /webhooks/github (verified via webhook signature).
_csrf_secret = secrets.token_urlsafe(32)
app.add_middleware(
    FormCSRFMiddleware,
    secret=_csrf_secret,
    sensitive_cookies={"session_id"},
    exempt_urls=[
        re.compile(r"/api/.*"),
        re.compile(r"/signup-request"),
        re.compile(r"/webhooks/github"),
    ],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

app.include_router(auth_router, tags=["auth"])
app.include_router(errors_router, prefix="/api/v1/errors", tags=["errors"])
app.include_router(github_router, tags=["github"])
app.include_router(web_projects_router, tags=["web"])
app.include_router(web_errors_router, tags=["web"])
app.include_router(web_members_router, tags=["web"])
app.include_router(web_settings_router, tags=["web"])
app.include_router(admin_router, tags=["admin"])
app.include_router(landing_router, tags=["web"])


@app.get("/health")
def health():
    """Health check for the API."""
    return {"status": "ok"}
