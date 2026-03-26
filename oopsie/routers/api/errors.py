"""Error ingestion API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.models.project import Project
from oopsie.routers.dependencies import get_project_from_api_key, get_session
from oopsie.schemas.errors import ErrorIngestBody
from oopsie.services.error_service import upsert_error

router = APIRouter()


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
