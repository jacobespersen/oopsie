"""FastAPI app entry point."""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from oopsie.api.errors import router as errors_router
from oopsie.api.projects import router as projects_router
from oopsie.auth_routes import router as auth_router
from oopsie.config import get_settings
from oopsie.logging import RequestLoggingMiddleware, setup_logging
from oopsie.queue import close_arq_pool
from oopsie.web.projects import router as web_projects_router

_settings = get_settings()
setup_logging(_settings.log_level, _settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle — cleanup arq pool on shutdown."""
    yield
    await close_arq_pool()


app = FastAPI(
    title="Oopsie",
    description="AI-powered error fix service",
    lifespan=lifespan,
)

_session_secret = _settings.jwt_secret_key or secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router, tags=["auth"])
app.include_router(errors_router, prefix="/api/v1/errors", tags=["errors"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(web_projects_router, tags=["web"])


@app.get("/")
def root():
    """Redirect to projects UI."""
    return RedirectResponse(url="/projects")


@app.get("/health")
def health():
    """Health check for the API."""
    return {"status": "ok"}
