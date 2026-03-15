"""Tests for oopsie.session — Redis-backed session management."""

import uuid

import pytest
from oopsie.session import (
    SESSION_TTL_SECONDS,
    create_session,
    delete_session,
    extend_session,
    get_session_org_slug,
    get_session_user_id,
)


@pytest.mark.asyncio
async def test_create_session_returns_token(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    assert isinstance(token, str)
    assert len(token) > 0


@pytest.mark.asyncio
async def test_create_session_stores_user_id_in_redis(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    stored = await fake_redis.hget(f"session:{token}", "user_id")
    assert stored is not None
    assert stored.decode() == str(user_id)


@pytest.mark.asyncio
async def test_create_session_stores_org_slug(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id, org_slug="my-org")

    stored = await fake_redis.hget(f"session:{token}", "org_slug")
    assert stored == b"my-org"


@pytest.mark.asyncio
async def test_create_session_sets_ttl(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    ttl = await fake_redis.ttl(f"session:{token}")
    # TTL should be close to SESSION_TTL_SECONDS (allow small delta for test execution)
    assert SESSION_TTL_SECONDS - 5 <= ttl <= SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_create_session_unique_tokens(fake_redis):
    user_id = uuid.uuid4()
    token1 = await create_session(user_id)
    token2 = await create_session(user_id)

    assert token1 != token2


@pytest.mark.asyncio
async def test_get_session_user_id_valid(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    result = await get_session_user_id(token)
    assert result == user_id
    assert isinstance(result, uuid.UUID)


@pytest.mark.asyncio
async def test_get_session_user_id_missing_token(fake_redis):
    result = await get_session_user_id("nonexistent-token")
    assert result is None


@pytest.mark.asyncio
async def test_get_session_user_id_after_delete(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)
    await delete_session(token)

    result = await get_session_user_id(token)
    assert result is None


@pytest.mark.asyncio
async def test_get_session_org_slug_returns_slug(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id, org_slug="my-org")

    result = await get_session_org_slug(token)
    assert result == "my-org"


@pytest.mark.asyncio
async def test_get_session_org_slug_missing(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    result = await get_session_org_slug(token)
    assert result is None


@pytest.mark.asyncio
async def test_extend_session_resets_ttl(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    # Simulate time passing by manually reducing the TTL
    await fake_redis.expire(f"session:{token}", 100)
    ttl_before = await fake_redis.ttl(f"session:{token}")
    assert ttl_before <= 100

    await extend_session(token)

    ttl_after = await fake_redis.ttl(f"session:{token}")
    assert SESSION_TTL_SECONDS - 5 <= ttl_after <= SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_extend_session_nonexistent_token(fake_redis):
    # Should not raise — EXPIRE on a missing key is a no-op returning 0
    await extend_session("nonexistent-token")


@pytest.mark.asyncio
async def test_delete_session_removes_key(fake_redis):
    user_id = uuid.uuid4()
    token = await create_session(user_id)

    await delete_session(token)

    exists = await fake_redis.exists(f"session:{token}")
    assert exists == 0


@pytest.mark.asyncio
async def test_delete_session_nonexistent_token(fake_redis):
    # Should not raise — DEL on a missing key is a no-op
    await delete_session("nonexistent-token")


@pytest.mark.asyncio
async def test_get_session_user_id_evicts_pre_hash_string_key(fake_redis):
    """Pre-hash-migration string key is evicted and returns None."""
    await fake_redis.set("session:old-token", str(uuid.uuid4()))

    result = await get_session_user_id("old-token")
    assert result is None

    # Key should have been deleted
    assert await fake_redis.exists("session:old-token") == 0


@pytest.mark.asyncio
async def test_get_session_org_slug_evicts_pre_hash_string_key(fake_redis):
    """Pre-hash-migration string key is evicted and returns None."""
    await fake_redis.set("session:old-token", str(uuid.uuid4()))

    result = await get_session_org_slug("old-token")
    assert result is None

    assert await fake_redis.exists("session:old-token") == 0


@pytest.mark.asyncio
async def test_get_session_user_id_reraises_non_wrongtype_error(
    fake_redis, monkeypatch
):
    """Non-WRONGTYPE ResponseError is re-raised, not swallowed."""
    import redis.exceptions

    async def _boom(*args, **kwargs):
        raise redis.exceptions.ResponseError("OOM command not allowed")

    monkeypatch.setattr(fake_redis, "hget", _boom)

    with pytest.raises(redis.exceptions.ResponseError, match="OOM"):
        await get_session_user_id("any-token")


@pytest.mark.asyncio
async def test_get_session_org_slug_reraises_non_wrongtype_error(
    fake_redis, monkeypatch
):
    """Non-WRONGTYPE ResponseError is re-raised, not swallowed."""
    import redis.exceptions

    async def _boom(*args, **kwargs):
        raise redis.exceptions.ResponseError("OOM command not allowed")

    monkeypatch.setattr(fake_redis, "hget", _boom)

    with pytest.raises(redis.exceptions.ResponseError, match="OOM"):
        await get_session_org_slug("any-token")
