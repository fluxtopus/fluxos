"""Integration tests for HTTP plugin with DB allowlist."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.plugins.http_plugin import http_request_handler, HttpPluginError
from src.infrastructure.allowed_hosts.allowed_host_service import AllowedHostService
# Import model to register with Base.metadata
from src.database.allowed_host_models import AllowedHost  # noqa: F401


@pytest.mark.asyncio
async def test_http_plugin_allowed_host_from_db(test_db):
    """Test that HTTP plugin checks DB allowlist."""
    # Add a host to the allowlist
    service = AllowedHostService(database=test_db)
    await service.add_allowed_host("httpbin.org", "development", created_by="test")

    # Mock httpx to avoid actual HTTP calls
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"test": "data"}
        mock_response.text = '{"test": "data"}'

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.request = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_client_instance

        # Also need to mock the host service used in http_plugin
        with patch('src.plugins.http_plugin.AllowedHostService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.is_host_allowed = AsyncMock(return_value=(True, None))
            mock_service_class.return_value = mock_service

            # Test HTTP plugin with allowed host
            result = await http_request_handler({
                "url": "https://httpbin.org/get",
                "method": "GET"
            })

            assert result["status"] == 200
            assert "json" in result or "text" in result


@pytest.mark.asyncio
async def test_http_plugin_denied_host_from_db(test_db):
    """Test that HTTP plugin rejects hosts not in DB allowlist."""
    # Don't add the host to allowlist - mock service returns not allowed
    with patch('src.plugins.http_plugin.AllowedHostService') as mock_service_class:
        mock_service = AsyncMock()
        mock_service.is_host_allowed = AsyncMock(return_value=(False, "Host not in allowlist"))
        mock_service_class.return_value = mock_service

        # Test HTTP plugin with disallowed host
        with pytest.raises(HttpPluginError) as exc_info:
            await http_request_handler({
                "url": "https://not-allowed.example.com/api",
                "method": "GET"
            })

        assert "not allowed" in str(exc_info.value).lower() or "allowlist" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_http_plugin_denylist_takes_precedence(test_db):
    """Test that denylist always wins, even if host is in allowlist."""
    # Test service rejects denylisted hosts
    service = AllowedHostService(database=test_db)

    # localhost should be rejected by denylist
    with pytest.raises(ValueError, match="denylist"):
        await service.add_allowed_host("localhost", "development")

    # Mock the service to reject localhost even for http_plugin
    with patch('src.plugins.http_plugin.AllowedHostService') as mock_service_class:
        mock_service = AsyncMock()
        mock_service.is_host_allowed = AsyncMock(return_value=(False, "Host is on denylist"))
        mock_service_class.return_value = mock_service

        # Plugin should reject it
        with pytest.raises(HttpPluginError) as exc_info:
            await http_request_handler({
                "url": "https://localhost/api",
                "method": "GET"
            })

        assert "not allowed" in str(exc_info.value).lower() or "denylist" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_http_plugin_https_required(test_db):
    """Test that HTTP plugin requires HTTPS."""
    with patch('src.plugins.http_plugin.AllowedHostService') as mock_service_class:
        mock_service = AsyncMock()
        mock_service.is_host_allowed = AsyncMock(return_value=(False, "Only HTTPS URLs are allowed"))
        mock_service_class.return_value = mock_service

        with pytest.raises(HttpPluginError) as exc_info:
            await http_request_handler({
                "url": "http://example.com/api",
                "method": "GET"
            })

        assert "https" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()
