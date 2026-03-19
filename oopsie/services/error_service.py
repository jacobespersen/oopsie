"""Error ingestion and deduplication."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.error_occurrence import ErrorOccurrence
from oopsie.utils.fingerprint import compute_fingerprint


async def upsert_error(
    session: AsyncSession,
    project_id: UUID,
    error_class: str,
    message: str,
    stack_trace: str | None = None,
) -> Error:
    """Find or create an Error by fingerprint.

    Records an ErrorOccurrence. Returns the Error.
    """
    fingerprint = compute_fingerprint(error_class, message, stack_trace)
    result = await session.execute(
        select(Error).where(
            Error.project_id == project_id,
            Error.fingerprint == fingerprint,
        )
    )
    error = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if error:
        error.occurrence_count += 1
        error.last_seen_at = now
        error.updated_at = now
        logger.info(
            "error_deduplicated",
            error_id=str(error.id),
            project_id=str(project_id),
            occurrence_count=error.occurrence_count,
        )
    else:
        error = Error(
            project_id=project_id,
            error_class=error_class,
            message=message,
            stack_trace=stack_trace,
            fingerprint=fingerprint,
            occurrence_count=1,
            status=ErrorStatus.OPEN,
        )
        session.add(error)
    await session.flush()
    if error.occurrence_count == 1:
        logger.info(
            "error_created",
            error_id=str(error.id),
            project_id=str(project_id),
            error_class=error_class,
        )
    occurrence = ErrorOccurrence(error_id=error.id)
    session.add(occurrence)
    await session.flush()
    return error


async def get_errors_for_project(
    session: AsyncSession,
    project_id: UUID,
    page: int,
    per_page: int,
) -> tuple[Sequence[Error], int]:
    """Return a page of errors for a project, ordered by last_seen_at desc.

    Returns (errors, total_count).
    """
    total_count = (
        await session.scalar(
            select(func.count())
            .select_from(Error)
            .where(Error.project_id == project_id)
        )
        or 0
    )

    result = await session.execute(
        select(Error)
        .where(Error.project_id == project_id)
        .order_by(Error.last_seen_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    errors = result.scalars().all()

    return errors, total_count
