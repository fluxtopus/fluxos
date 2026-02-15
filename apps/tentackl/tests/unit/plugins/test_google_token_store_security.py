"""Security tests for GoogleTokenStore encryption and OAuth nonce replay protection."""

import base64
import os

import pytest
from unittest.mock import AsyncMock

from src.plugins.google.token_store import GoogleTokenStore


@pytest.mark.asyncio
async def test_store_and_get_tokens_uses_encryption(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)

    store = GoogleTokenStore(redis_url="redis://unused")

    db = {}

    async def _hset(redis_key, mapping):
        db[redis_key] = dict(mapping)

    async def _hgetall(redis_key):
        return dict(db.get(redis_key, {}))

    mock_redis = AsyncMock()
    mock_redis.hset.side_effect = _hset
    mock_redis.hgetall.side_effect = _hgetall
    mock_redis.expire = AsyncMock(return_value=True)

    store._get_redis = AsyncMock(return_value=mock_redis)

    await store.store_tokens(
        user_id="user-1",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
    )

    raw = db["google_oauth:user-1"]
    assert raw["access_token"].startswith("enc:")
    assert raw["refresh_token"].startswith("enc:")

    tokens = await store.get_tokens("user-1")
    assert tokens["access_token"] == "access-token"
    assert tokens["refresh_token"] == "refresh-token"


@pytest.mark.asyncio
async def test_oauth_nonce_is_single_use(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", key)

    store = GoogleTokenStore(redis_url="redis://unused")

    nonce_store = {}

    async def _setex(redis_key, ttl, value):
        nonce_store[redis_key] = value

    async def _get(redis_key):
        return nonce_store.get(redis_key)

    async def _delete(redis_key):
        nonce_store.pop(redis_key, None)

    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = _setex
    mock_redis.get.side_effect = _get
    mock_redis.delete.side_effect = _delete

    store._get_redis = AsyncMock(return_value=mock_redis)

    await store.store_oauth_state_nonce("nonce-1", "user-1", ttl_seconds=600)

    first = await store.consume_oauth_state_nonce("nonce-1", "user-1")
    second = await store.consume_oauth_state_nonce("nonce-1", "user-1")

    assert first is True
    assert second is False
