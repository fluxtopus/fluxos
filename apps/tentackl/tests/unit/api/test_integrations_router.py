"""Unit tests for integrations router (INT-018 Mimic migration).

Tests the /api/integrations endpoints that proxy to Mimic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from src.api.routers.integrations import (
    CreateIntegrationRequest,
    UpdateIntegrationRequest,
    IntegrationResponse,
    IntegrationListResponse,
    handle_mimic_error,
    get_bearer_token,
)
from mimic import (
    IntegrationProvider,
    IntegrationDirection,
    IntegrationStatus,
    MimicError,
    AuthenticationError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


class TestGetBearerToken:
    """Tests for bearer token extraction."""

    def test_missing_authorization_header(self):
        """Should raise 401 when Authorization header is missing."""
        from fastapi import HTTPException, Request

        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc:
            get_bearer_token(mock_request)

        assert exc.value.status_code == 401
        assert "Missing Authorization header" in str(exc.value.detail)

    def test_invalid_scheme(self):
        """Should raise 401 when scheme is not Bearer."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Basic abc123"}

        with pytest.raises(HTTPException) as exc:
            get_bearer_token(mock_request)

        assert exc.value.status_code == 401
        assert "Invalid authorization scheme" in str(exc.value.detail)

    def test_valid_bearer_token(self):
        """Should extract token correctly."""
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token-123"}

        token = get_bearer_token(mock_request)

        assert token == "test-token-123"


class TestHandleMimicError:
    """Tests for Mimic error handling."""

    def test_authentication_error(self):
        """Should convert to 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(AuthenticationError("Invalid token"))

        assert exc.value.status_code == 401

    def test_permission_denied_error(self):
        """Should convert to 403."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(PermissionDeniedError("Access denied"))

        assert exc.value.status_code == 403

    def test_not_found_error(self):
        """Should convert to 404."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(ResourceNotFoundError("Not found"))

        assert exc.value.status_code == 404

    def test_validation_error(self):
        """Should convert to 400."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(ValidationError("Invalid input"))

        assert exc.value.status_code == 400

    def test_service_unavailable_error(self):
        """Should convert to 503."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(ServiceUnavailableError("Service down"))

        assert exc.value.status_code == 503

    def test_generic_mimic_error(self):
        """Should convert to 500."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            handle_mimic_error(MimicError("Something went wrong"))

        assert exc.value.status_code == 500


class TestIntegrationModels:
    """Tests for request/response models."""

    def test_create_integration_request_defaults(self):
        """Should have proper defaults."""
        request = CreateIntegrationRequest(
            name="test-integration",
            provider="discord",
        )

        assert request.name == "test-integration"
        assert request.provider == "discord"
        assert request.direction == "bidirectional"

    def test_update_integration_request_optional_fields(self):
        """Should allow partial updates."""
        request = UpdateIntegrationRequest(name="new-name")

        assert request.name == "new-name"
        assert request.status is None

    def test_integration_response(self):
        """Should serialize correctly."""
        response = IntegrationResponse(
            id="test-id",
            name="test-integration",
            provider="discord",
            direction="bidirectional",
            status="active",
            webhook_url="https://mimic.example.com/gateway/test-id",
            created_at=datetime.utcnow(),
        )

        assert response.id == "test-id"
        assert response.provider == "discord"


@pytest.mark.asyncio
class TestListIntegrations:
    """Tests for list_integrations endpoint."""

    @patch("src.api.routers.integrations._get_integration_use_cases")
    @patch("src.api.routers.integrations.auth_middleware")
    async def test_list_integrations_success(self, mock_auth, mock_use_cases):
        """Should return list of integrations."""
        from src.api.routers.integrations import list_integrations

        # Mock auth
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_auth.require_permission.return_value = lambda: mock_user

        # Mock Mimic response
        mock_integration = MagicMock()
        mock_integration.id = "int-123"
        mock_integration.name = "test-integration"
        mock_integration.provider = IntegrationProvider.discord
        mock_integration.direction = IntegrationDirection.bidirectional
        mock_integration.status = IntegrationStatus.active
        mock_integration.created_at = datetime.utcnow()
        mock_integration.updated_at = None

        mock_use_cases.return_value.list_integrations = AsyncMock(return_value=MagicMock(
            items=[mock_integration],
            total=1,
        ))
        mock_use_cases.return_value.get_integration = AsyncMock(return_value=MagicMock(
            outbound_config=None,
            inbound_config=None,
        ))

        # Mock request
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        result = await list_integrations(
            http_request=mock_request,
            user=mock_user,
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].id == "int-123"


@pytest.mark.asyncio
class TestCreateIntegration:
    """Tests for create_integration endpoint."""

    @patch("src.api.routers.integrations._get_integration_use_cases")
    @patch("src.api.routers.integrations.auth_middleware")
    async def test_create_integration_success(self, mock_auth, mock_use_cases):
        """Should create integration via Mimic."""
        from src.api.routers.integrations import create_integration

        # Mock auth
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_auth.require_permission.return_value = lambda: mock_user

        # Mock Mimic response
        mock_result = MagicMock()
        mock_result.id = "int-new"
        mock_result.name = "discord-bot"
        mock_result.provider = IntegrationProvider.discord
        mock_result.direction = IntegrationDirection.bidirectional
        mock_result.status = IntegrationStatus.active
        mock_result.created_at = datetime.utcnow()
        mock_result.updated_at = None

        mock_use_cases.return_value.create_integration = AsyncMock(return_value=mock_result)
        mock_use_cases.return_value.set_outbound_config = AsyncMock(return_value={})
        mock_use_cases.return_value.set_inbound_config = AsyncMock(return_value={})

        # Mock request
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        request_data = CreateIntegrationRequest(
            name="discord-bot",
            provider="discord",
            direction="bidirectional",
        )

        result = await create_integration(
            request=request_data,
            http_request=mock_request,
            user=mock_user,
        )

        assert result.id == "int-new"
        assert result.name == "discord-bot"
        assert result.provider == "discord"
