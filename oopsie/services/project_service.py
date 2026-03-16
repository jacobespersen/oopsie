"""Project-related business logic."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.models.error import Error
from oopsie.models.project import Project


async def list_projects_with_error_counts(
    session: AsyncSession, organization_id: uuid.UUID
) -> tuple[list[Project], dict[uuid.UUID, int]]:
    """List projects for an org with the count of distinct errors each has.

    Returns a tuple of (projects, error_counts) where error_counts is a
    dict mapping project ID to its number of distinct Error rows.
    Projects are ordered by created_at descending.
    """
    error_count_subq = (
        select(Error.project_id, func.count(Error.id).label("error_count"))
        .group_by(Error.project_id)
        .subquery()
    )
    result = await session.execute(
        select(
            Project,
            func.coalesce(error_count_subq.c.error_count, 0).label("error_count"),
        )
        .outerjoin(error_count_subq, Project.id == error_count_subq.c.project_id)
        .where(Project.organization_id == organization_id)
        .order_by(Project.created_at.desc())
    )
    rows = result.all()
    projects = [row[0] for row in rows]
    error_counts = {row[0].id: row[1] for row in rows}
    return projects, error_counts
