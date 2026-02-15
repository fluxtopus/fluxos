"""Unit tests for inkPass client"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.clients.inkpass_client import InkPassClient, InkPassConfig, AuthenticationError, InkPassError
import httpx


@pytest.mark.unit
@pytest.mark.asyncio
async def test_client_initialization():
    """Test client initialization with default config"""
    client = InkPassClient()
    assert client.config.base_url == "http://localhost:8002"
    assert client.config.timeout == 5.0
    assert client.config.max_retries == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_client_initialization_with_custom_config():
    """Test client initialization with custom config"""
    config = InkPassConfig(
        base_url="http://inkpass:8000",
        api_key="test-api-key",
        timeout=10.0,
    )
    client = InkPassClient(config)
    assert client.config.base_url == "http://inkpass:8000"
    assert client.config.api_key == "test-api-key"
    assert client.config.timeout == 10.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation"""
    client = InkPassClient()

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "user-123",
        "email": "test@example.com",
        "organization_id": "org-123",
    }

    with patch.object(httpx.AsyncClient, "get", return_value=mock_response) as mock_get:
        result = await client.validate_token("test-token")

        assert result is not None
        assert result["id"] == "user-123"
        assert result["email"] == "test@example.com"
        mock_get.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_token_invalid():
    """Test token validation with invalid token"""
    client = InkPassClient()

    # Mock 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
        result = await client.validate_token("invalid-token")
        assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_permission_success():
    """Test successful permission check"""
    client = InkPassClient()

    # Mock successful response with permission granted
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"has_permission": True}

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("test-token", "workflows", "create")
        assert has_perm is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_permission_denied():
    """Test permission check when permission is denied"""
    client = InkPassClient()

    # Mock successful response with permission denied
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"has_permission": False}

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("test-token", "workflows", "delete")
        assert has_perm is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_permission_invalid_token():
    """Test permission check with invalid token"""
    client = InkPassClient()

    # Mock 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        has_perm = await client.check_permission("invalid-token", "workflows", "create")
        # Should default to deny access
        assert has_perm is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_login_success():
    """Test successful login"""
    client = InkPassClient()

    # Mock successful login response
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

        assert result["access_token"] == "access-token-123"
        assert result["refresh_token"] == "refresh-token-123"
        assert result["token_type"] == "bearer"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """Test login with invalid credentials"""
    client = InkPassClient()

    # Mock 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            await client.login("test@example.com", "wrong-password")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_user_success():
    """Test successful user registration"""
    client = InkPassClient()

    # Mock successful registration response
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "user_id": "user-123",
        "email": "test@example.com",
        "organization_id": "org-123",
    }

    with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
        result = await client.register_user("test@example.com", "password123", "Test Org")

        assert result["user_id"] == "user-123"
        assert result["email"] == "test@example.com"
        assert result["organization_id"] == "org-123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_manager():
    """Test client as async context manager"""
    config = InkPassConfig(base_url="http://inkpass:8000")

    async with InkPassClient(config) as client:
        assert client._client is not None

    # After context exit, client should be closed (implementation detail)


@pytest.mark.unit
def test_get_headers_with_token():
    """Test headers generation with token"""
    client = InkPassClient()
    headers = client._get_headers(token="test-token")

    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.unit
def test_get_headers_with_api_key():
    """Test headers generation with API key"""
    config = InkPassConfig(api_key="test-api-key")
    client = InkPassClient(config)
    headers = client._get_headers()

    assert headers["X-API-Key"] == "test-api-key"
    assert headers["Content-Type"] == "application/json"
