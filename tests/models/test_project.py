"""Tests for Project model."""

import uuid

import pytest
from oopsie.models import Error, Project
from sqlalchemy import select
from sqlalchemy.orm import selectinload


@pytest.mark.asyncio
async def test_project_creation(saved_project, sample_project_data):
    """Project can be created with required fields and has expected defaults."""
    assert saved_project.id is not None
    assert isinstance(saved_project.id, uuid.UUID)
    assert saved_project.name == sample_project_data["name"]
    assert saved_project.github_repo_url == sample_project_data["github_repo_url"]
    assert saved_project.default_branch == "main"
    assert saved_project.error_threshold == 10
    assert saved_project.created_at is not None
    assert saved_project.updated_at is not None


@pytest.mark.asyncio
async def test_project_default_branch_override(db_session, sample_project_data):
    """Project accepts custom default_branch."""
    sample_project_data["default_branch"] = "develop"
    project = Project(**sample_project_data)
    db_session.add(project)
    await db_session.flush()
    assert project.default_branch == "develop"


@pytest.mark.asyncio
async def test_project_error_threshold_override(db_session, sample_project_data):
    """Project accepts custom error_threshold."""
    sample_project_data["error_threshold"] = 5
    project = Project(**sample_project_data)
    db_session.add(project)
    await db_session.flush()
    assert project.error_threshold == 5


@pytest.mark.asyncio
async def test_project_errors_relationship(db_session, saved_project, saved_error):
    """Project.errors returns linked Error records."""
    result = await db_session.execute(
        select(Project)
        .where(Project.id == saved_project.id)
        .options(selectinload(Project.errors))
    )
    project_loaded = result.scalar_one()
    assert len(project_loaded.errors) == 1
    assert project_loaded.errors[0].id == saved_error.id


@pytest.mark.asyncio
async def test_cascade_delete_project_deletes_errors(
    db_session, saved_project, saved_error
):
    """Deleting a project deletes its errors (cascade)."""
    error_id = saved_error.id
    await db_session.delete(saved_project)
    await db_session.flush()

    result = await db_session.execute(select(Error).where(Error.id == error_id))
    assert result.scalar_one_or_none() is None
