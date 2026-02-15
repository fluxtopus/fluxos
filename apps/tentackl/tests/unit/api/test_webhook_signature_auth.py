"""Tests for webhook HMAC signature validation in auth_middleware (SEC-005).

Verifies that the webhook auth path in AuthMiddleware.authenticate() now
properly validates the X-Webhook-Signature header using HMAC-SHA256 instead
of blindly trusting any request that provides the header pair.
"""

import hashlib
import hmac
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.auth_middleware import AuthMiddleware, AuthType, AuthUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_signature(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest matching verify_webhook_signature."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _make_request(headers: dict, body: bytes = b"{}") -> MagicMock:
    """Build a mock Request with the given headers and body."""
    request = MagicMock()
    request.headers = headers
    request.body = AsyncMock(return_value=body)
    return request


# ---------------------------------------------------------------------------
# Unit tests for verify_webhook_signature
# ---------------------------------------------------------------------------

class TestVerifyWebhookSignature:
    """Direct tests for the HMAC verification helper."""

    def test_valid_signature_returns_true(self):
        mw = AuthMiddleware()
        secret = "my-secret"
        payload = b'{"event": "test"}'
        sig = _compute_signature(payload, secret)
        assert mw.verify_webhook_signature(payload, sig, secret) is True

    def test_wrong_signature_returns_false(self):
        mw = AuthMiddleware()
        secret = "my-secret"
        payload = b'{"event": "test"}'
        assert mw.verify_webhook_signature(payload, "bad-sig", secret) is False

    def test_wrong_secret_returns_false(self):
        mw = AuthMiddleware()
        payload = b'{"event": "test"}'
        sig = _compute_signature(payload, "correct-secret")
        assert mw.verify_webhook_signature(payload, sig, "wrong-secret") is False

    def test_empty_payload(self):
        mw = AuthMiddleware()
        secret = "my-secret"
        payload = b""
        sig = _compute_signature(payload, secret)
        assert mw.verify_webhook_signature(payload, sig, secret) is True


# ---------------------------------------------------------------------------
# Unit tests for _get_webhook_secret
# ---------------------------------------------------------------------------

class TestGetWebhookSecret:
    """Tests for the secret lookup chain: Redis → per-source env → global env."""

    @pytest.mark.asyncio
    async def test_returns_secret_from_redis(self):
        mw = AuthMiddleware()
        auth_config = json.dumps({"type": "hmac", "secret": "redis-secret"})
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=auth_config)
        mock_redis.aclose = AsyncMock()
        mw._new_redis = AsyncMock(return_value=mock_redis)

        result = await mw._get_webhook_secret("my-source")
        assert result == "redis-secret"
        mock_redis.hget.assert_awaited_once_with(
            "tentackl:gateway:source:my-source", "authentication"
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_per_source_env_var(self, monkeypatch):
        mw = AuthMiddleware()
        # Redis returns nothing
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()
        mw._new_redis = AsyncMock(return_value=mock_redis)

        monkeypatch.setenv("WEBHOOK_SECRET_MY_SOURCE", "env-per-source-secret")
        result = await mw._get_webhook_secret("my-source")
        assert result == "env-per-source-secret"

    @pytest.mark.asyncio
    async def test_falls_back_to_global_env_var(self, monkeypatch):
        mw = AuthMiddleware()
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()
        mw._new_redis = AsyncMock(return_value=mock_redis)

        monkeypatch.delenv("WEBHOOK_SECRET_MY_SOURCE", raising=False)
        monkeypatch.setenv("WEBHOOK_SECRET", "global-secret")
        result = await mw._get_webhook_secret("my-source")
        assert result == "global-secret"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_secret_found(self, monkeypatch):
        mw = AuthMiddleware()
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()
        mw._new_redis = AsyncMock(return_value=mock_redis)

        monkeypatch.delenv("WEBHOOK_SECRET_MY_SOURCE", raising=False)
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        result = await mw._get_webhook_secret("my-source")
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_env(self, monkeypatch):
        mw = AuthMiddleware()
        mw._new_redis = AsyncMock(side_effect=ConnectionError("Redis down"))

        monkeypatch.setenv("WEBHOOK_SECRET_MY_SOURCE", "fallback-secret")
        result = await mw._get_webhook_secret("my-source")
        assert result == "fallback-secret"

    @pytest.mark.asyncio
    async def test_hyphenated_source_name_env_lookup(self, monkeypatch):
        """Source name hyphens are replaced with underscores for env var lookup."""
        mw = AuthMiddleware()
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()
        mw._new_redis = AsyncMock(return_value=mock_redis)

        monkeypatch.setenv("WEBHOOK_SECRET_GITHUB_EVENTS", "gh-secret")
        result = await mw._get_webhook_secret("github-events")
        assert result == "gh-secret"


# ---------------------------------------------------------------------------
# Integration tests for authenticate() webhook path
# ---------------------------------------------------------------------------

class TestAuthenticateWebhookPath:
    """Tests for the webhook code path inside AuthMiddleware.authenticate()."""

    @pytest.mark.asyncio
    async def test_valid_signature_authenticates(self):
        """Valid HMAC signature creates an authenticated webhook user."""
        mw = AuthMiddleware()
        secret = "test-webhook-secret"
        body = b'{"event": "order.created"}'
        signature = _compute_signature(body, secret)

        mw._get_webhook_secret = AsyncMock(return_value=secret)
        request = _make_request(
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Source": "github",
            },
            body=body,
        )

        user, auth_type = await mw.authenticate(request)
        assert user is not None
        assert auth_type == AuthType.WEBHOOK
        assert user.id == "webhook_github"
        assert user.service_name == "github"
        assert user.metadata.get("signature_verified") is True
        assert "webhook:publish" in user.scopes

    @pytest.mark.asyncio
    async def test_invalid_signature_rejects(self):
        """Invalid HMAC signature returns (None, NONE)."""
        mw = AuthMiddleware()
        secret = "test-webhook-secret"
        body = b'{"event": "order.created"}'

        mw._get_webhook_secret = AsyncMock(return_value=secret)
        request = _make_request(
            headers={
                "X-Webhook-Signature": "invalid-signature",
                "X-Webhook-Source": "github",
            },
            body=body,
        )

        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE

    @pytest.mark.asyncio
    async def test_missing_secret_rejects(self):
        """When no secret is configured for the source, reject the request."""
        mw = AuthMiddleware()
        mw._get_webhook_secret = AsyncMock(return_value=None)

        request = _make_request(
            headers={
                "X-Webhook-Signature": "some-sig",
                "X-Webhook-Source": "unknown-source",
            },
        )

        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE

    @pytest.mark.asyncio
    async def test_secret_lookup_failure_rejects(self):
        """If the secret lookup raises an exception, reject the request."""
        mw = AuthMiddleware()
        mw._get_webhook_secret = AsyncMock(side_effect=RuntimeError("boom"))

        request = _make_request(
            headers={
                "X-Webhook-Signature": "some-sig",
                "X-Webhook-Source": "broken-source",
            },
        )

        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE

    @pytest.mark.asyncio
    async def test_signature_from_different_body_rejected(self):
        """Signature computed over different body must be rejected."""
        mw = AuthMiddleware()
        secret = "shared-secret"
        original_body = b'{"event": "order.created"}'
        tampered_body = b'{"event": "order.deleted"}'
        signature = _compute_signature(original_body, secret)

        mw._get_webhook_secret = AsyncMock(return_value=secret)
        request = _make_request(
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Source": "shop",
            },
            body=tampered_body,
        )

        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE

    @pytest.mark.asyncio
    async def test_missing_signature_header_skips_webhook_path(self):
        """Without X-Webhook-Signature the webhook path is not entered."""
        mw = AuthMiddleware()
        request = _make_request(
            headers={"X-Webhook-Source": "github"},
        )
        # authenticate should fall through to "no authentication"
        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE

    @pytest.mark.asyncio
    async def test_missing_source_header_skips_webhook_path(self):
        """Without X-Webhook-Source the webhook path is not entered."""
        mw = AuthMiddleware()
        request = _make_request(
            headers={"X-Webhook-Signature": "some-sig"},
        )
        user, auth_type = await mw.authenticate(request)
        assert user is None
        assert auth_type == AuthType.NONE


# ---------------------------------------------------------------------------
# Source code verification — the old vulnerability must be gone
# ---------------------------------------------------------------------------

class TestNoUnauthenticatedWebhookUser:
    """Verify the old bypass code pattern is gone from the source."""

    def test_no_bare_webhook_user_creation_without_verification(self):
        """The old pattern that created a webhook user without signature
        verification must not exist in the source code."""
        import inspect
        source = inspect.getsource(AuthMiddleware.authenticate)
        # The old code had a comment "For now, return a webhook user"
        assert "For now, return a webhook user" not in source
        # The old code did not call verify_webhook_signature
        assert "verify_webhook_signature" in source
        # The new code adds signature_verified to metadata
        assert "signature_verified" in source
