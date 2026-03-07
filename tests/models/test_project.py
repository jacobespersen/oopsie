"""Tests for Project model."""

import uuid

import pytest
from oopsie.models import Error, Project
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from tests.factories import ErrorFactory, OrganizationFactory, ProjectFactory


@pytest.mark.asyncio
async def test_project_creation(factory):
    """Project can be created with required fields and has expected defaults."""
    project = await factory(ProjectFactory)
    assert project.id is not None
    assert isinstance(project.id, uuid.UUID)
    assert project.default_branch == "main"
    assert project.error_threshold == 10
    assert project.created_at is not None
    assert project.updated_at is not None


@pytest.mark.asyncio
async def test_project_default_branch_override(factory):
    """Project accepts custom default_branch."""
    project = await factory(ProjectFactory, default_branch="develop")
    assert project.default_branch == "develop"


@pytest.mark.asyncio
async def test_project_error_threshold_override(factory):
    """Project accepts custom error_threshold."""
    project = await factory(ProjectFactory, error_threshold=5)
    assert project.error_threshold == 5


@pytest.mark.asyncio
async def test_project_errors_relationship(db_session, factory):
    """Project.errors returns linked Error records."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)

    result = await db_session.execute(
        select(Project)
        .where(Project.id == project.id)
        .options(selectinload(Project.errors))
    )
    project_loaded = result.scalar_one()
    assert len(project_loaded.errors) == 1
    assert project_loaded.errors[0].id == error.id


@pytest.mark.asyncio
async def test_cascade_delete_project_deletes_errors(db_session, factory):
    """Deleting a project deletes its errors (cascade)."""
    project = await factory(ProjectFactory)
    error = await factory(ErrorFactory, project_id=project.id)
    error_id = error.id

    await db_session.delete(project)
    await db_session.flush()

    result = await db_session.execute(select(Error).where(Error.id == error_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_project_organization_relationship(db_session, factory):
    """Project can be linked to an organization."""
    org = await factory(OrganizationFactory)
    project = await factory(ProjectFactory, organization_id=org.id)

    assert project.organization_id == org.id

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    loaded = result.scalar_one()
    assert loaded.organization_id == org.id
