"""FastAPI app entry point."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from oopsie.api.errors import router as errors_router
from oopsie.api.projects import router as projects_router
from oopsie.web.projects import router as web_projects_router

app = FastAPI(title="Oopsie", description="AI-powered error fix service")

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
