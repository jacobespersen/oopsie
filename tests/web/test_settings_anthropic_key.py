"""Tests for Anthropic API key management on org settings page."""

from oopsie.services.anthropic_key_service import (
    get_anthropic_api_key,
    set_anthropic_api_key,
)
from sqlalchemy.ext.asyncio import AsyncSession

_TEST_ENCRYPTION_KEY = "sH0fafIOlcxd9fb7s-lXn4sKh3Kh_sddG68RK6meO6U="


class TestOrgSettingsAnthropicKey:
    async def test_settings_page_shows_no_key_by_default(
        self, authenticated_client, organization
    ):
        resp = await authenticated_client.get(f"/orgs/{organization.slug}/settings")
        assert resp.status_code == 200
        assert "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" not in resp.text

    async def test_settings_page_shows_masked_key(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        set_anthropic_api_key(organization, "sk-ant-org-key-1234", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        resp = await authenticated_client.get(f"/orgs/{organization.slug}/settings")
        assert resp.status_code == 200
        assert "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u20221234" in resp.text

    async def test_post_sets_key(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/settings/anthropic-key",
            data={"anthropic_api_key": "sk-ant-new-org-key-abcd"},
        )
        assert resp.status_code in (303, 302)

        await db_session.refresh(organization)
        key = get_anthropic_api_key(organization, _TEST_ENCRYPTION_KEY)
        assert key == "sk-ant-new-org-key-abcd"

    async def test_post_clear_removes_key(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        set_anthropic_api_key(organization, "sk-ant-to-clear", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/settings/anthropic-key",
            data={"anthropic_api_key": "", "clear": "1"},
        )
        assert resp.status_code in (303, 302)

        await db_session.refresh(organization)
        assert get_anthropic_api_key(organization, _TEST_ENCRYPTION_KEY) is None

    async def test_post_empty_preserves_existing(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        set_anthropic_api_key(organization, "sk-ant-keep-me", _TEST_ENCRYPTION_KEY)
        await db_session.flush()

        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/settings/anthropic-key",
            data={"anthropic_api_key": ""},
        )
        assert resp.status_code in (303, 302)

        await db_session.refresh(organization)
        key = get_anthropic_api_key(organization, _TEST_ENCRYPTION_KEY)
        assert key == "sk-ant-keep-me"
