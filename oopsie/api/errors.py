"""Error ingestion API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.deps import get_project_from_api_key, get_session
from oopsie.models.project import Project
from oopsie.services.error_service import upsert_error

router = APIRouter()


class ErrorIngestBody(BaseModel):
    """Request body for POST /api/v1/errors."""

    error_class: str
    message: str
    stack_trace: str | None = None


@router.post("", status_code=202)
@router.post("/", status_code=202)
async def ingest_error(
    body: ErrorIngestBody,
    session: AsyncSession = Depends(get_session),
    project: Project = Depends(get_project_from_api_key),
) -> dict[str, str]:
    """Accept an error report; deduplicate by fingerprint.

    Records an occurrence. Returns 202 Accepted.
    """
    await upsert_error(
        session,
        project.id,
        body.error_class,
        body.message,
        body.stack_trace,
    )
    return {"status": "accepted"}
