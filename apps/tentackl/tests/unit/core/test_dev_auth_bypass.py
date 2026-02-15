"""Tests for SEC-010: DEV_AUTH_BYPASS hardening.

Validates that:
1. Production environments force DEV_AUTH_BYPASS off
2. DEV_AUTH_BYPASS_TOKEN is required as a second factor
3. Startup validation logs appropriate warnings
4. is_dev_auth_bypass_allowed() enforces all three guards
5. auth_middleware uses is_dev_auth_bypass_allowed() for bypass decisions
"""

import os
import logging
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# is_dev_auth_bypass_allowed() tests
# ---------------------------------------------------------------------------


class TestIsDevAuthBypassAllowed:
    """Tests for is_dev_auth_bypass_allowed() request-time check."""

    def test_returns_false_when_bypass_not_enabled(self, monkeypatch):
        """DEV_AUTH_BYPASS not set or false -> bypass not allowed."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "false")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "some-token")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            assert is_dev_auth_bypass_allowed() is False

    def test_returns_false_in_production(self, monkeypatch):
        """APP_ENV != 'development' -> bypass not allowed even with token."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "some-token")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "production"
            assert is_dev_auth_bypass_allowed() is False

    def test_returns_false_in_staging(self, monkeypatch):
        """APP_ENV='staging' -> bypass not allowed."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "some-token")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "staging"
            assert is_dev_auth_bypass_allowed() is False

    def test_returns_false_without_token(self, monkeypatch):
        """DEV_AUTH_BYPASS=true but no token -> bypass not allowed."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.delenv("DEV_AUTH_BYPASS_TOKEN", raising=False)

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            assert is_dev_auth_bypass_allowed() is False

    def test_returns_false_with_empty_token(self, monkeypatch):
        """DEV_AUTH_BYPASS=true but empty token -> bypass not allowed."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            assert is_dev_auth_bypass_allowed() is False

    def test_returns_true_when_all_conditions_met(self, monkeypatch):
        """All three conditions met -> bypass allowed."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "dev-token-123")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            assert is_dev_auth_bypass_allowed() is True

    def test_bypass_case_insensitive(self, monkeypatch):
        """DEV_AUTH_BYPASS=TRUE (uppercase) should still work."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "TRUE")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "dev-token-123")

        from src.core.config import is_dev_auth_bypass_allowed

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            assert is_dev_auth_bypass_allowed() is True


# ---------------------------------------------------------------------------
# validate_dev_auth_bypass() tests
# ---------------------------------------------------------------------------


class TestValidateDevAuthBypass:
    """Tests for validate_dev_auth_bypass() startup validation."""

    def test_no_warning_when_bypass_disabled(self, monkeypatch, caplog):
        """No warning logged when DEV_AUTH_BYPASS is not enabled."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "false")

        from src.core.config import validate_dev_auth_bypass

        with caplog.at_level(logging.WARNING):
            validate_dev_auth_bypass()

        assert "SEC-010" not in caplog.text

    def test_production_forces_bypass_off(self, monkeypatch, caplog):
        """In production, bypass is forced off and warning logged."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "some-token")

        from src.core.config import validate_dev_auth_bypass

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "production"
            with caplog.at_level(logging.WARNING):
                validate_dev_auth_bypass()

        assert "ignored" in caplog.text.lower()
        assert "production" in caplog.text.lower() or "APP_ENV=production" in caplog.text

    def test_missing_token_warns(self, monkeypatch, caplog):
        """In development with bypass but no token, warns that bypass is inactive."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.delenv("DEV_AUTH_BYPASS_TOKEN", raising=False)

        from src.core.config import validate_dev_auth_bypass

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            with caplog.at_level(logging.WARNING):
                validate_dev_auth_bypass()

        assert "INACTIVE" in caplog.text
        assert "DEV_AUTH_BYPASS_TOKEN" in caplog.text

    def test_active_bypass_warns(self, monkeypatch, caplog):
        """When all guards pass, logs a prominent 'ACTIVE' warning."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "dev-token-123")

        from src.core.config import validate_dev_auth_bypass

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            with caplog.at_level(logging.WARNING):
                validate_dev_auth_bypass()

        assert "ACTIVE" in caplog.text
        assert "bypassed" in caplog.text.lower() or "bypass" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Integration: auth_middleware uses is_dev_auth_bypass_allowed
# ---------------------------------------------------------------------------


class TestAuthMiddlewareBypassIntegration:
    """Verify auth_middleware.require_auth() uses is_dev_auth_bypass_allowed()."""

    def test_source_uses_is_dev_auth_bypass_allowed(self):
        """auth_middleware.py must call is_dev_auth_bypass_allowed, not inline logic."""
        import inspect
        from src.api import auth_middleware as mod

        source = inspect.getsource(mod)
        assert "is_dev_auth_bypass_allowed" in source, (
            "auth_middleware.py should import and use is_dev_auth_bypass_allowed()"
        )

    def test_source_does_not_have_inline_bypass_logic(self):
        """auth_middleware.py must NOT contain the old inline DEV_AUTH_BYPASS check."""
        import inspect
        from src.api import auth_middleware as mod

        source = inspect.getsource(mod)
        # The old pattern was: _os.getenv("DEV_AUTH_BYPASS", "false")
        assert '_os.getenv("DEV_AUTH_BYPASS"' not in source, (
            "auth_middleware.py should not contain inline DEV_AUTH_BYPASS env check"
        )

    @pytest.mark.asyncio
    async def test_require_auth_rejects_without_token(self, monkeypatch):
        """When DEV_AUTH_BYPASS_TOKEN is missing, require_auth returns 401."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.delenv("DEV_AUTH_BYPASS_TOKEN", raising=False)

        from src.api.auth_middleware import AuthMiddleware
        from fastapi import HTTPException

        middleware = AuthMiddleware()
        auth_dep = middleware.require_auth()

        # Create a mock request with no auth headers
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state = MagicMock()

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            # Mock authenticate to return no user
            with patch.object(middleware, "authenticate", return_value=(None, "none")):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_dep(mock_request)
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_injects_dev_user_with_token(self, monkeypatch):
        """When all guards pass, require_auth injects dev user."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "test-token")

        from src.api.auth_middleware import AuthMiddleware
        from src.core.config import is_dev_auth_bypass_allowed

        middleware = AuthMiddleware()
        auth_dep = middleware.require_auth()

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state = MagicMock()

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "development"
            with patch.object(middleware, "authenticate", return_value=(None, "none")):
                user = await auth_dep(mock_request)
                assert user.id == "dev"
                assert user.metadata.get("auto_dev_user") is True

    @pytest.mark.asyncio
    async def test_require_auth_rejects_in_production(self, monkeypatch):
        """In production, bypass is never active even with all env vars set."""
        monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
        monkeypatch.setenv("DEV_AUTH_BYPASS_TOKEN", "test-token")

        from src.api.auth_middleware import AuthMiddleware
        from fastapi import HTTPException

        middleware = AuthMiddleware()
        auth_dep = middleware.require_auth()

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state = MagicMock()

        with patch("src.core.config.settings") as mock_settings:
            mock_settings.APP_ENV = "production"
            with patch.object(middleware, "authenticate", return_value=(None, "none")):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_dep(mock_request)
                assert exc_info.value.status_code == 401
