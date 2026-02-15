"""Security tests for Google OAuth signed state validation."""

from urllib.parse import urlparse, parse_qs

import pytest

from src.plugins.google.oauth import (
    google_oauth_start_handler,
    google_oauth_callback_handler,
)
from src.plugins.google.exceptions import GoogleOAuthError


class _FakeStore:
    def __init__(self, consume_result=True):
        self.consume_result = consume_result
        self.saved_nonce = None

    async def store_oauth_state_nonce(self, nonce: str, user_id: str, ttl_seconds: int = 600):
        self.saved_nonce = (nonce, user_id, ttl_seconds)

    async def consume_oauth_state_nonce(self, nonce: str, user_id: str):
        return self.consume_result


@pytest.mark.asyncio
async def test_callback_rejects_tampered_state(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_STATE_SECRET", "state-secret")

    store = _FakeStore(consume_result=True)
    monkeypatch.setattr("src.plugins.google.oauth.get_token_store", lambda: store)

    start = await google_oauth_start_handler({"user_id": "user-1"})
    state = parse_qs(urlparse(start["authorization_url"]).query)["state"][0]

    # Tamper signature
    tampered = state[:-1] + ("0" if state[-1] != "0" else "1")

    with pytest.raises(GoogleOAuthError):
        await google_oauth_callback_handler({"code": "authcode", "state": tampered})


@pytest.mark.asyncio
async def test_callback_rejects_replayed_state_nonce(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_STATE_SECRET", "state-secret")

    store = _FakeStore(consume_result=False)
    monkeypatch.setattr("src.plugins.google.oauth.get_token_store", lambda: store)

    start = await google_oauth_start_handler({"user_id": "user-1"})
    state = parse_qs(urlparse(start["authorization_url"]).query)["state"][0]

    with pytest.raises(GoogleOAuthError, match="already used"):
        await google_oauth_callback_handler({"code": "authcode", "state": state})
