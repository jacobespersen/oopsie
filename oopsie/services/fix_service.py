"""Fix attempt DB logic."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oopsie.logging import logger
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus


def generate_branch_name(error_id: str | UUID) -> str:
    """Generate a branch name from an error ID."""
    return f"oopsie/fix-{str(error_id)[:8]}"


async def has_active_fix_attempt(session: AsyncSession, error_id: UUID) -> bool:
    """Return True if a PENDING or RUNNING FixAttempt exists for this error."""
    result = await session.execute(
        select(FixAttempt).where(
            FixAttempt.error_id == error_id,
            FixAttempt.status.in_([FixAttemptStatus.PENDING, FixAttemptStatus.RUNNING]),
        )
    )
    return result.scalar_one_or_none() is not None


async def create_fix_attempt(
    session: AsyncSession, error_id: UUID, branch_name: str
) -> FixAttempt:
    """Create a new FixAttempt in PENDING status."""
    fix_attempt = FixAttempt(
        error_id=error_id,
        branch_name=branch_name,
        status=FixAttemptStatus.PENDING,
    )
    session.add(fix_attempt)
    await session.flush()
    logger.info(
        "fix_attempt_created",
        fix_attempt_id=str(fix_attempt.id),
        error_id=str(error_id),
    )
    return fix_attempt


async def mark_fix_attempt_running(
    session: AsyncSession, fix_attempt_id: UUID
) -> FixAttempt:
    """Mark a FixAttempt as RUNNING and set started_at."""
    fix_attempt = await session.get(FixAttempt, fix_attempt_id)
    assert fix_attempt is not None
    fix_attempt.status = FixAttemptStatus.RUNNING
    fix_attempt.started_at = datetime.now(UTC)
    await session.flush()
    logger.info("fix_attempt_running", fix_attempt_id=str(fix_attempt_id))
    return fix_attempt


async def complete_fix_attempt(
    session: AsyncSession,
    fix_attempt_id: UUID,
    *,
    success: bool,
    pr_url: str | None,
    claude_output: str | None,
) -> FixAttempt:
    """Mark a FixAttempt as SUCCESS or FAILED."""
    fix_attempt = await session.get(FixAttempt, fix_attempt_id)
    assert fix_attempt is not None
    fix_attempt.status = (
        FixAttemptStatus.SUCCESS if success else FixAttemptStatus.FAILED
    )
    fix_attempt.pr_url = pr_url
    fix_attempt.claude_output = claude_output
    fix_attempt.completed_at = datetime.now(UTC)
    await session.flush()

    if success:
        error = await session.get(Error, fix_attempt.error_id)
        assert error is not None
        error.status = ErrorStatus.FIX_ATTEMPTED
        await session.flush()

    logger.info(
        "fix_attempt_completed",
        fix_attempt_id=str(fix_attempt_id),
        success=success,
    )
    return fix_attempt


async def get_fix_attempt_status_for_errors(
    session: AsyncSession, error_ids: list[UUID]
) -> dict[UUID, str | None]:
    """Batch query returning the latest FixAttempt status for each error ID.

    Returns a dict mapping error_id -> status string (or None if no attempts).
    """
    if not error_ids:
        return {}

    result = await session.execute(
        select(FixAttempt)
        .where(FixAttempt.error_id.in_(error_ids))
        .order_by(FixAttempt.created_at.desc())
    )
    attempts = result.scalars().all()

    status_map: dict[UUID, str | None] = {eid: None for eid in error_ids}
    for attempt in attempts:
        # First match wins (ordered by created_at desc = latest first)
        if status_map[attempt.error_id] is None:
            status_map[attempt.error_id] = attempt.status
    return status_map
