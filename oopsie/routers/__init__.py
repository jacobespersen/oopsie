"""Consolidated routers — import all router instances for main.py."""

from oopsie.routers.api.errors import router as errors_router
from oopsie.routers.auth import router as auth_router
from oopsie.routers.github import router as github_router
from oopsie.routers.web.admin import router as admin_router
from oopsie.routers.web.errors import router as web_errors_router
from oopsie.routers.web.landing import router as landing_router
from oopsie.routers.web.members import router as web_members_router
from oopsie.routers.web.projects import router as web_projects_router
from oopsie.routers.web.settings import router as web_settings_router

__all__ = [
    "auth_router",
    "errors_router",
    "github_router",
    "web_projects_router",
    "web_errors_router",
    "web_members_router",
    "web_settings_router",
    "admin_router",
    "landing_router",
]
