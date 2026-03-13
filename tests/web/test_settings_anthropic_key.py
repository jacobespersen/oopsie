"""Tests for Anthropic API key management on org settings page."""

import httpx
from oopsie.auth import create_access_token
from oopsie.deps import get_session
from oopsie.main import app
from oopsie.models.membership import MemberRole
from oopsie.services.anthropic_key_service import (
    get_anthropic_api_key,
    set_anthropic_api_key,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_ENCRYPTION_KEY
from tests.factories import MembershipFactory, UserFactory


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
        set_anthropic_api_key(organization, "sk-ant-org-key-1234", TEST_ENCRYPTION_KEY)
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
        key = get_anthropic_api_key(organization, TEST_ENCRYPTION_KEY)
        assert key == "sk-ant-new-org-key-abcd"

    async def test_post_clear_removes_key(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        set_anthropic_api_key(organization, "sk-ant-to-clear", TEST_ENCRYPTION_KEY)
        await db_session.flush()

        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/settings/anthropic-key",
            data={"anthropic_api_key": "", "clear": "1"},
        )
        assert resp.status_code in (303, 302)

        await db_session.refresh(organization)
        assert get_anthropic_api_key(organization, TEST_ENCRYPTION_KEY) is None

    async def test_post_empty_preserves_existing(
        self, authenticated_client, organization, db_session: AsyncSession
    ):
        set_anthropic_api_key(organization, "sk-ant-keep-me", TEST_ENCRYPTION_KEY)
        await db_session.flush()

        resp = await authenticated_client.post(
            f"/orgs/{organization.slug}/settings/anthropic-key",
            data={"anthropic_api_key": ""},
        )
        assert resp.status_code in (303, 302)

        await db_session.refresh(organization)
        key = get_anthropic_api_key(organization, TEST_ENCRYPTION_KEY)
        assert key == "sk-ant-keep-me"

    async def test_member_cannot_set_org_key(
        self, organization, db_session: AsyncSession
    ):
        """Regular members are rejected from the anthropic-key endpoint."""
        member_user = UserFactory.build()
        db_session.add(member_user)
        await db_session.flush()
        membership = MembershipFactory.build(
            user_id=member_user.id,
            organization_id=organization.id,
            role=MemberRole.member,
        )
        db_session.add(membership)
        await db_session.flush()

        token = create_access_token(member_user.id, member_user.email)

        async def override_get_session():
            yield db_session

        app.dependency_overrides[get_session] = override_get_session
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                cookies={"access_token": token},
            ) as client:
                resp = await client.post(
                    f"/orgs/{organization.slug}/settings/anthropic-key",
                    data={"anthropic_api_key": "sk-ant-should-fail"},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert resp.status_code == 403
