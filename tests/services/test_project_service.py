"""Tests for project service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import ErrorFactory, OrganizationFactory, ProjectFactory


@pytest.mark.asyncio
async def test_list_projects_with_error_counts(db_session: AsyncSession, factory):
    """Returns projects with correct error counts."""
    org = await factory(OrganizationFactory)
    project_a = await factory(ProjectFactory, name="project-a", organization_id=org.id)
    project_b = await factory(ProjectFactory, name="project-b", organization_id=org.id)

    await factory(ErrorFactory, project_id=project_a.id, fingerprint="fp-1")
    await factory(ErrorFactory, project_id=project_a.id, fingerprint="fp-2")
    await factory(ErrorFactory, project_id=project_a.id, fingerprint="fp-3")
    # project_b has no errors

    from oopsie.services.project_service import list_projects_with_error_counts

    projects, error_counts = await list_projects_with_error_counts(db_session, org.id)

    assert len(projects) == 2
    assert error_counts[project_a.id] == 3
    assert error_counts[project_b.id] == 0


@pytest.mark.asyncio
async def test_list_projects_with_error_counts_empty(db_session: AsyncSession, factory):
    """Returns empty list when org has no projects."""
    org = await factory(OrganizationFactory)

    from oopsie.services.project_service import list_projects_with_error_counts

    projects, error_counts = await list_projects_with_error_counts(db_session, org.id)

    assert projects == []
    assert error_counts == {}


@pytest.mark.asyncio
async def test_list_projects_with_error_counts_scoped_to_org(
    db_session: AsyncSession, factory
):
    """Only returns projects belonging to the specified org."""
    org_a = await factory(OrganizationFactory)
    org_b = await factory(OrganizationFactory)
    await factory(ProjectFactory, name="org-a-project", organization_id=org_a.id)
    await factory(ProjectFactory, name="org-b-project", organization_id=org_b.id)

    from oopsie.services.project_service import list_projects_with_error_counts

    projects, _ = await list_projects_with_error_counts(db_session, org_a.id)

    assert len(projects) == 1
    assert projects[0].name == "org-a-project"
