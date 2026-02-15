"""Tests for InkPassClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from inkpass_sdk import (
    InkPassClient,
    InkPassConfig,
    AuthenticationError,
    ServiceUnavailableError,
    TokenResponse,
    UserResponse,
    RegistrationResponse,
)
import httpx


@pytest.mark.asyncio
async def test_client_initialization():
    """Test client initialization with default config."""
    client = InkPassClient()
    assert client.config.base_url == "http://localhost:8002"
    assert client.config.timeout == 5.0


@pytest.mark.asyncio
async def test_client_initialization_with_custom_config():
    """Test client initialization with custom config."""
    config = InkPassConfig(
        base_url="http://inkpass:8000",
        api_key="test-api-key",
        timeout=10.0,
    )
    client = InkPassClient(config)
    assert client.config.base_url == "http://inkpass:8000"
    assert client.config.api_key == "test-api-key"
    assert client.config.timeout == 10.0


@pytest.mark.asyncio
async def test_register_success():
    """Test successful user registration."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "user_id": "user-123",
        "email": "test@example.com",
        "organization_id": "org-123",
    }

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        result = await client.register("test@example.com", "password123", "Test Org")

        assert isinstance(result, RegistrationResponse)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"
        assert result.organization_id == "org-123"


@pytest.mark.asyncio
async def test_login_success():
    """Test successful login."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "access-token-123",
        "refresh_token": "refresh-token-123",
        "token_type": "bearer",
        "expires_in": 1800,
    }

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        result = await client.login("test@example.com", "password123")

        assert isinstance(result, TokenResponse)
        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-123"
        assert result.token_type == "bearer"
        assert result.expires_in == 1800


@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """Test login with invalid credentials."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"detail": "Invalid credentials"}

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await client.login("test@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "user-123",
        "email": "test@example.com",
        "organization_id": "org-123",
        "status": "active",
        "two_fa_enabled": False,
    }

    with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
        result = await client.validate_token("test-token")

        assert isinstance(result, UserResponse)
        assert result.id == "user-123"
        assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_validate_token_invalid():
    """Test token validation with invalid token."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
        result = await client.validate_token("invalid-token")
        assert result is None


@pytest.mark.asyncio
async def test_check_permission_success():
    """Test successful permission check."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "has_permission": True,
        "resource": "workflows",
        "action": "create",
    }

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("test-token", "workflows", "create")
        assert has_perm is True


@pytest.mark.asyncio
async def test_check_permission_denied():
    """Test permission check when permission is denied."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "has_permission": False,
        "resource": "workflows",
        "action": "delete",
    }

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("test-token", "workflows", "delete")
        assert has_perm is False


@pytest.mark.asyncio
async def test_check_permission_invalid_token():
    """Test permission check with invalid token returns False (fail-safe)."""
    client = InkPassClient()

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("invalid-token", "workflows", "create")
        assert has_perm is False


@pytest.mark.asyncio
async def test_context_manager():
    """Test client as async context manager."""
    config = InkPassConfig(base_url="http://inkpass:8000")

    async with InkPassClient(config) as client:
        assert client._client is not None

    # After context exit, client should be closed


def test_get_headers_with_token():
    """Test headers generation with token."""
    client = InkPassClient()
    headers = client._get_headers(token="test-token")

    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"


def test_get_headers_with_api_key():
    """Test headers generation with API key."""
    config = InkPassConfig(api_key="test-api-key")
    client = InkPassClient(config)
    headers = client._get_headers()

    assert headers["X-API-Key"] == "test-api-key"
    assert headers["Content-Type"] == "application/json"
