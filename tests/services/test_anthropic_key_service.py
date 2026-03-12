"""Tests for anthropic_key_service."""

import pytest
from oopsie.services.anthropic_key_service import (
    clear_anthropic_api_key,
    get_anthropic_api_key,
    mask_anthropic_api_key,
    resolve_anthropic_api_key,
    set_anthropic_api_key,
)
from oopsie.services.exceptions import AnthropicKeyNotConfiguredError

from tests.factories import OrganizationFactory, ProjectFactory

# The test conftest.py sets ENCRYPTION_KEY to a known test value.
_TEST_ENCRYPTION_KEY = "sH0fafIOlcxd9fb7s-lXn4sKh3Kh_sddG68RK6meO6U="


class TestSetAndGetAnthropicApiKey:
    async def test_set_and_get_on_organization(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()

        set_anthropic_api_key(org, "sk-ant-test-key-1234", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        result = get_anthropic_api_key(org, _TEST_ENCRYPTION_KEY)
        assert result == "sk-ant-test-key-1234"

    async def test_set_and_get_on_project(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()
        project = ProjectFactory.build(organization_id=org.id)
        db_session.add(project)
        await db_session.flush()

        set_anthropic_api_key(project, "sk-ant-proj-key-5678", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        result = get_anthropic_api_key(project, _TEST_ENCRYPTION_KEY)
        assert result == "sk-ant-proj-key-5678"

    async def test_get_returns_none_when_not_set(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()

        result = get_anthropic_api_key(org, _TEST_ENCRYPTION_KEY)
        assert result is None


class TestClearAnthropicApiKey:
    async def test_clear_removes_key(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()

        set_anthropic_api_key(org, "sk-ant-to-clear", _TEST_ENCRYPTION_KEY)
        await db_session.flush()
        assert get_anthropic_api_key(org, _TEST_ENCRYPTION_KEY) is not None

        clear_anthropic_api_key(org)
        await db_session.flush()
        assert get_anthropic_api_key(org, _TEST_ENCRYPTION_KEY) is None


class TestMaskAnthropicApiKey:
    def test_masks_key_showing_last_4(self):
        assert (
            mask_anthropic_api_key("sk-ant-api03-abcdefghijk")
            == "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022hijk"
        )

    def test_short_key_fully_masked(self):
        assert (
            mask_anthropic_api_key("abc")
            == "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
        )

    def test_empty_string(self):
        assert (
            mask_anthropic_api_key("")
            == "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
        )


class TestResolveAnthropicApiKey:
    async def test_project_key_wins_over_org(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()
        project = ProjectFactory.build(organization_id=org.id)
        db_session.add(project)
        await db_session.flush()
        # Eagerly load the relationship
        project.organization = org

        set_anthropic_api_key(org, "sk-ant-org-key", _TEST_ENCRYPTION_KEY)
        set_anthropic_api_key(project, "sk-ant-proj-key", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        result = resolve_anthropic_api_key(project, _TEST_ENCRYPTION_KEY)
        assert result == "sk-ant-proj-key"

    async def test_falls_back_to_org_key(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()
        project = ProjectFactory.build(organization_id=org.id)
        db_session.add(project)
        await db_session.flush()
        project.organization = org

        set_anthropic_api_key(org, "sk-ant-org-key", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        result = resolve_anthropic_api_key(project, _TEST_ENCRYPTION_KEY)
        assert result == "sk-ant-org-key"

    async def test_raises_when_neither_set(self, db_session):
        org = OrganizationFactory.build()
        db_session.add(org)
        await db_session.flush()
        project = ProjectFactory.build(organization_id=org.id)
        db_session.add(project)
        await db_session.flush()
        project.organization = org

        with pytest.raises(AnthropicKeyNotConfiguredError):
            resolve_anthropic_api_key(project, _TEST_ENCRYPTION_KEY)
