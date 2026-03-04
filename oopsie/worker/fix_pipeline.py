"""Fix pipeline arq job."""

from oopsie.services import pipeline_service


async def run_fix_pipeline(ctx: dict, error_id: str, project_id: str) -> None:
    """Arq job entry point: delegates to pipeline_service."""
    await pipeline_service.run(error_id, project_id)
