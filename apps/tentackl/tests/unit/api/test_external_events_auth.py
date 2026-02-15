"""Tests for external_events router admin authentication (SEC-002).

Verifies that register_event_source and list_event_sources endpoints
use InkPass-based authentication instead of hardcoded admin-secret-key.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routers import external_events


@pytest.fixture(autouse=True)
def disable_dev_auth_bypass(monkeypatch):
    """Ensure dev auth bypass is disabled for auth-related tests."""
    monkeypatch.setenv("DEV_AUTH_BYPASS", "false")
    monkeypatch.delenv("DEV_AUTH_BYPASS_TOKEN", raising=False)


@pytest.fixture
def app():
    """Create a test FastAPI app with external_events router."""
    test_app = FastAPI()
    test_app.include_router(external_events.router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state between tests."""
    old_gateway = external_events.event_gateway
    old_bus = external_events.event_bus
    old_db = external_events.database
    yield
    external_events.event_gateway = old_gateway
    external_events.event_bus = old_bus
    external_events.database = old_db


def _mock_inkpass_user():
    """Create a mock InkPass user object."""
    user = MagicMock()
    user.id = "user-123"
    user.email = "admin@fluxtopus.com"
    user.first_name = "Admin"
    user.last_name = "User"
    user.organization_id = "org-1"
    user.two_fa_enabled = False
    user.status = "active"
    return user


class TestRegisterSourceAuth:
    """Test that register_event_source requires InkPass admin auth."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.post(
            "/api/events/sources/register",
            json={
                "name": "test-source",
                "source_type": "webhook",
            },
        )
        assert response.status_code == 401

    def test_rejects_old_hardcoded_admin_key(self, client):
        """The old hardcoded 'admin-secret-key' must no longer grant access."""
        response = client.post(
            "/api/events/sources/register",
            json={
                "name": "test-source",
                "source_type": "webhook",
            },
            headers={"Authorization": "Bearer admin-secret-key"},
        )
        # Should be 401 (invalid token) not 200 or 403
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_accepts_valid_inkpass_token(
        self, mock_validate, mock_check_perm, client
    ):
        """Valid InkPass token with events:admin permission should succeed."""
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = True

        # Mock gateway and database
        mock_gateway = MagicMock()
        mock_gateway.register_source = AsyncMock(return_value=True)
        mock_gateway._initialized = True
        external_events.event_gateway = mock_gateway

        mock_db = MagicMock()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db.get_session.return_value = mock_cm
        external_events.database = mock_db

        response = client.post(
            "/api/events/sources/register",
            json={
                "name": "test-source",
                "source_type": "webhook",
            },
            headers={"Authorization": "Bearer valid-inkpass-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "source_id" in data
        assert "api_key" in data

        # Verify inkPass was called with correct resource/action
        mock_check_perm.assert_called_once()
        call_kwargs = mock_check_perm.call_args
        assert call_kwargs.kwargs["resource"] == "events"
        assert call_kwargs.kwargs["action"] == "admin"

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_valid_token_without_permission(
        self, mock_validate, mock_check_perm, client
    ):
        """Valid token but without events:admin permission should return 403."""
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = False  # Permission denied

        response = client.post(
            "/api/events/sources/register",
            json={
                "name": "test-source",
                "source_type": "webhook",
            },
            headers={"Authorization": "Bearer valid-but-no-perm"},
        )

        assert response.status_code == 403


class TestListSourcesAuth:
    """Test that list_event_sources requires InkPass admin auth."""

    def test_rejects_request_without_auth(self, client):
        """Request without any auth should return 401."""
        response = client.get("/api/events/sources")
        assert response.status_code == 401

    def test_rejects_old_hardcoded_admin_key(self, client):
        """The old hardcoded 'admin-secret-key' must no longer grant access."""
        response = client.get(
            "/api/events/sources",
            headers={"Authorization": "Bearer admin-secret-key"},
        )
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_accepts_valid_inkpass_token(
        self, mock_validate, mock_check_perm, client
    ):
        """Valid InkPass token with events:admin permission should succeed."""
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = True

        response = client.get(
            "/api/events/sources",
            headers={"Authorization": "Bearer valid-inkpass-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert "total" in data

        mock_check_perm.assert_called_once()
        call_kwargs = mock_check_perm.call_args
        assert call_kwargs.kwargs["resource"] == "events"
        assert call_kwargs.kwargs["action"] == "admin"

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_rejects_valid_token_without_permission(
        self, mock_validate, mock_check_perm, client
    ):
        """Valid token but without events:admin permission should return 403."""
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = False

        response = client.get(
            "/api/events/sources",
            headers={"Authorization": "Bearer valid-but-no-perm"},
        )

        assert response.status_code == 403


class TestNoHardcodedSecrets:
    """Verify no hardcoded secrets remain in the module."""

    def test_no_admin_secret_key_in_source(self):
        """The string 'admin-secret-key' must not appear in external_events.py."""
        import inspect
        source = inspect.getsource(external_events)
        assert "admin-secret-key" not in source


class TestBatchAndReplayAuth:
    """Test auth enforcement for batch publish and replay endpoints."""

    def test_batch_rejects_without_auth(self, client):
        response = client.post(
            "/api/events/publish/batch",
            json=[{"event_type": "t", "data": {}}],
        )
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_batch_rejects_without_publish_permission(self, mock_validate, mock_check_perm, client):
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = False

        response = client.post(
            "/api/events/publish/batch",
            json=[{"event_type": "t", "data": {}}],
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_batch_accepts_with_publish_permission(self, mock_validate, mock_check_perm, client):
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = True

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(return_value=True)
        external_events.event_bus = mock_bus

        response = client.post(
            "/api/events/publish/batch",
            json=[{"event_type": "t", "data": {}}],
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        assert response.json()["successful"] == 1

    def test_replay_rejects_without_auth(self, client):
        response = client.get("/api/events/replay")
        assert response.status_code == 401

    @patch("src.api.auth_middleware.inkpass_check_permission", new_callable=AsyncMock)
    @patch("src.api.auth_middleware.inkpass_validate_token", new_callable=AsyncMock)
    def test_replay_rejects_without_view_permission(self, mock_validate, mock_check_perm, client):
        mock_validate.return_value = _mock_inkpass_user()
        mock_check_perm.return_value = False

        response = client.get(
            "/api/events/replay",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403
