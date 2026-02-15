"""Tests for Google OAuth router authentication (SEC-004).

Verifies that all Google OAuth endpoints (except /callback) require
authentication and that user_id must match the authenticated user.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routers.oauth import google


@pytest.fixture(autouse=True)
def disable_dev_auth_bypass(monkeypatch):
    """Disable DEV_AUTH_BYPASS so unauthenticated requests get 401, not a dev user."""
    monkeypatch.setenv("DEV_AUTH_BYPASS", "false")


@pytest.fixture
def app():
    """Create a test FastAPI app with google oauth router."""
    test_app = FastAPI()
    test_app.include_router(google.router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_inkpass_user(user_id="user-123"):
    """Create a mock InkPass user object."""
    user = MagicMock()
    user.id = user_id
    user.email = "admin@fluxtopus.com"
    user.first_name = "Admin"
    user.last_name = "User"
    user.organization_id = "org-1"
    user.two_fa_enabled = False
    user.status = "active"
    return user


# =============================================================================
# /start endpoint tests
# =============================================================================


class TestStartOAuthAuth:
    """Test that /start requires authentication and user_id verification."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.get("/api/v1/oauth/google/start?user_id=user-123")
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_mismatched_user_id(self, mock_validate, client):
        """Authenticated user requesting OAuth for a different user_id should get 403."""
        mock_validate.return_value = _mock_inkpass_user("user-123")

        response = client.get(
            "/api/v1/oauth/google/start?user_id=victim-456",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403
        assert "different user" in response.json()["detail"]

    @patch("src.plugins.registry.registry.execute", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_accepts_matching_user_id(self, mock_validate, mock_execute, client):
        """Authenticated user requesting OAuth for their own user_id should succeed."""
        mock_validate.return_value = _mock_inkpass_user("user-123")
        mock_execute.return_value = {
            "success": True,
            "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
            "user_id": "user-123",
        }

        response = client.get(
            "/api/v1/oauth/google/start?user_id=user-123",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user_id"] == "user-123"
        assert "authorization_url" in data


# =============================================================================
# /callback endpoint tests (should remain unauthenticated)
# =============================================================================


class TestCallbackNoAuth:
    """Test that /callback does NOT require authentication."""

    @patch("src.plugins.registry.registry.execute", new_callable=AsyncMock)
    def test_callback_works_without_auth(self, mock_execute, client):
        """The callback endpoint should work without authentication (Google redirect)."""
        mock_execute.return_value = {
            "success": True,
            "user_id": "user-123",
            "email": "user@example.com",
            "name": "Test User",
        }

        response = client.get(
            "/api/v1/oauth/google/callback?code=authcode123&state=statetoken123"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email"] == "user@example.com"


# =============================================================================
# /status/{user_id} endpoint tests
# =============================================================================


class TestStatusAuth:
    """Test that /status/{user_id} requires authentication and user_id verification."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.get("/api/v1/oauth/google/status/user-123")
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_mismatched_user_id(self, mock_validate, client):
        """Authenticated user checking status for a different user_id should get 403."""
        mock_validate.return_value = _mock_inkpass_user("user-123")

        response = client.get(
            "/api/v1/oauth/google/status/victim-456",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403

    @patch("src.plugins.registry.registry.execute", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_accepts_matching_user_id(self, mock_validate, mock_execute, client):
        """Authenticated user checking their own status should succeed."""
        mock_validate.return_value = _mock_inkpass_user("user-123")
        mock_execute.return_value = {
            "connected": True,
            "user_id": "user-123",
            "token_expired": False,
            "has_refresh_token": True,
        }

        response = client.get(
            "/api/v1/oauth/google/status/user-123",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["user_id"] == "user-123"


# =============================================================================
# /enable-assistant endpoint tests
# =============================================================================


class TestEnableAssistantAuth:
    """Test that /enable-assistant requires authentication and user_id verification."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.post(
            "/api/v1/oauth/google/enable-assistant?user_id=user-123"
        )
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_mismatched_user_id(self, mock_validate, client):
        """Authenticated user enabling assistant for a different user should get 403."""
        mock_validate.return_value = _mock_inkpass_user("user-123")

        response = client.post(
            "/api/v1/oauth/google/enable-assistant?user_id=victim-456",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403


# =============================================================================
# /disable-assistant endpoint tests
# =============================================================================


class TestDisableAssistantAuth:
    """Test that /disable-assistant requires authentication and user_id verification."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.post(
            "/api/v1/oauth/google/disable-assistant?user_id=user-123"
        )
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_mismatched_user_id(self, mock_validate, client):
        """Authenticated user disabling assistant for a different user should get 403."""
        mock_validate.return_value = _mock_inkpass_user("user-123")

        response = client.post(
            "/api/v1/oauth/google/disable-assistant?user_id=victim-456",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403


# =============================================================================
# Source code verification
# =============================================================================


class TestSourceCodeVerification:
    """Verify authentication is properly applied in source code."""

    def test_callback_has_no_auth_dependency(self):
        """The /callback endpoint should NOT have auth dependencies."""
        import inspect
        source = inspect.getsource(google.oauth_callback)
        assert "require_auth" not in source
        assert "Depends" not in source

    def test_start_has_auth_dependency(self):
        """The /start endpoint should require authentication."""
        import inspect
        source = inspect.getsource(google.start_oauth_flow)
        assert "require_auth" in source
        assert "_verify_user_id" in source

    def test_status_has_auth_dependency(self):
        """The /status endpoint should require authentication."""
        import inspect
        source = inspect.getsource(google.get_oauth_status)
        assert "require_auth" in source
        assert "_verify_user_id" in source

    def test_enable_assistant_has_auth_dependency(self):
        """The /enable-assistant endpoint should require authentication."""
        import inspect
        source = inspect.getsource(google.enable_calendar_assistant)
        assert "require_auth" in source
        assert "_verify_user_id" in source

    def test_disable_assistant_has_auth_dependency(self):
        """The /disable-assistant endpoint should require authentication."""
        import inspect
        source = inspect.getsource(google.disable_calendar_assistant)
        assert "require_auth" in source
        assert "_verify_user_id" in source
