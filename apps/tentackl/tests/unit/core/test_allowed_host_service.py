"""Unit tests for allowed host service."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

from src.infrastructure.allowed_hosts.allowed_host_service import AllowedHostService, DENYLISTED_HOSTS
from src.database.allowed_host_models import AllowedHost, Environment
from src.interfaces.database import Database


@pytest.fixture
def mock_database():
    """Create a mock database."""
    db = MagicMock(spec=Database)
    db.get_session = MagicMock()
    return db


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_is_host_allowed_https_required(mock_database, mock_session):
    """Test that only HTTPS URLs are allowed."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    service = AllowedHostService(database=mock_database)
    is_allowed, error = await service.is_host_allowed("http://example.com", "development")
    
    assert not is_allowed
    assert "HTTPS" in error or "https" in error.lower()


@pytest.mark.asyncio
async def test_is_host_allowed_denylist_check(mock_database, mock_session):
    """Test that denylisted hosts are rejected."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    service = AllowedHostService(database=mock_database)
    
    # Test with localhost (in denylist)
    is_allowed, error = await service.is_host_allowed("https://localhost/api", "development")
    
    assert not is_allowed
    assert "denylist" in error.lower() or "not allowed" in error.lower()


@pytest.mark.asyncio
async def test_is_host_allowed_ip_literal_rejected(mock_database, mock_session):
    """Test that IP literal addresses are rejected."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    service = AllowedHostService(database=mock_database)
    
    is_allowed, error = await service.is_host_allowed("https://192.168.1.1/api", "development")
    
    assert not is_allowed
    assert "IP literal" in error or "hostname" in error.lower()


@pytest.mark.asyncio
async def test_is_host_allowed_not_in_allowlist(mock_database, mock_session):
    """Test that hosts not in allowlist are rejected."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return None (host not found)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    is_allowed, error = await service.is_host_allowed("https://example.com/api", "development")
    
    assert not is_allowed
    assert "not in the allowlist" in error.lower()


@pytest.mark.asyncio
async def test_is_host_allowed_success(mock_database, mock_session):
    """Test that allowed hosts pass validation."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return an allowed host
    allowed_host = AllowedHost(
        host="example.com",
        environment=Environment.DEVELOPMENT,
        enabled=True
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = allowed_host
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    # Mock DNS resolution to return a public IP
    with patch('socket.gethostbyname', return_value='93.184.216.34'):  # example.com IP
        is_allowed, error = await service.is_host_allowed("https://example.com/api", "development")
    
    assert is_allowed
    assert error is None


@pytest.mark.asyncio
async def test_add_allowed_host_denylisted(mock_database):
    """Test that denylisted hosts cannot be added."""
    service = AllowedHostService(database=mock_database)
    
    with pytest.raises(ValueError, match="denylist"):
        await service.add_allowed_host("localhost", "development")


@pytest.mark.asyncio
async def test_add_allowed_host_invalid_format(mock_database):
    """Test that invalid host formats are rejected."""
    service = AllowedHostService(database=mock_database)
    
    with pytest.raises(ValueError, match="hostname only"):
        await service.add_allowed_host("https://example.com/path", "development")


@pytest.mark.asyncio
async def test_add_allowed_host_success(mock_database, mock_session):
    """Test successfully adding an allowed host."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return None (host doesn't exist yet)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    # Mock the refresh to set an ID
    def mock_refresh(obj):
        obj.id = "test-id"
    mock_session.refresh.side_effect = mock_refresh
    
    result = await service.add_allowed_host("example.com", "development", created_by="test-user")
    
    assert result.host == "example.com"
    assert result.environment == Environment.DEVELOPMENT
    assert result.enabled is True
    assert result.created_by == "test-user"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_remove_allowed_host_not_found(mock_database, mock_session):
    """Test removing a host that doesn't exist."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return None (host not found)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    result = await service.remove_allowed_host("example.com", "development")
    
    assert result is False


@pytest.mark.asyncio
async def test_remove_allowed_host_success(mock_database, mock_session):
    """Test successfully removing an allowed host."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return an existing host
    allowed_host = AllowedHost(
        host="example.com",
        environment=Environment.DEVELOPMENT,
        enabled=True
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = allowed_host
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    result = await service.remove_allowed_host("example.com", "development")
    
    assert result is True
    assert allowed_host.enabled is False
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_allowed_hosts(mock_database, mock_session):
    """Test getting list of allowed hosts."""
    mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
    
    # Mock session to return a list of hosts
    host1 = AllowedHost(host="example.com", environment=Environment.DEVELOPMENT, enabled=True)
    host2 = AllowedHost(host="api.example.com", environment=Environment.PRODUCTION, enabled=True)
    
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [host1, host2]
    mock_session.execute.return_value = result_mock
    
    service = AllowedHostService(database=mock_database)
    
    hosts = await service.get_allowed_hosts()
    
    assert len(hosts) == 2
    assert hosts[0].host == "example.com"
    assert hosts[1].host == "api.example.com"


def test_is_ip_literal():
    """Test IP literal detection."""
    service = AllowedHostService()
    
    assert service._is_ip_literal("192.168.1.1") is True
    assert service._is_ip_literal("2001:db8::1") is True
    assert service._is_ip_literal("example.com") is False
    assert service._is_ip_literal("api.example.com") is False


def test_is_private_ip():
    """Test private IP detection."""
    service = AllowedHostService()
    
    assert service._is_private_ip("10.0.0.1") is True
    assert service._is_private_ip("172.16.0.1") is True
    assert service._is_private_ip("192.168.1.1") is True
    assert service._is_private_ip("127.0.0.1") is True
    assert service._is_private_ip("169.254.1.1") is True
    assert service._is_private_ip("8.8.8.8") is False
    assert service._is_private_ip("93.184.216.34") is False  # example.com

