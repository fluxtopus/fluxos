"""Integration tests for allowed hosts service layer.

These tests verify the AllowedHostService works correctly with a real database.
They test the service layer directly rather than going through HTTP routes
to avoid authentication complexity in tests.
"""

import pytest
import pytest_asyncio
from src.infrastructure.allowed_hosts.allowed_host_service import AllowedHostService, DENYLISTED_HOSTS
from src.database.allowed_host_models import AllowedHost, Environment
from src.interfaces.database import Database
# Import to ensure the model is registered with Base.metadata
from src.database.allowed_host_models import AllowedHost  # noqa: F401


@pytest.mark.asyncio
async def test_list_allowed_hosts_empty(test_db):
    """Test listing allowed hosts when none exist."""
    service = AllowedHostService(database=test_db)
    hosts = await service.get_allowed_hosts()

    assert hosts == []


@pytest.mark.asyncio
async def test_create_allowed_host(test_db):
    """Test creating an allowed host."""
    service = AllowedHostService(database=test_db)

    allowed_host = await service.add_allowed_host(
        host="api.example.com",
        environment="development",
        created_by="test-user",
        notes="Test host"
    )

    assert allowed_host.host == "api.example.com"
    assert allowed_host.environment == Environment.DEVELOPMENT
    assert allowed_host.enabled is True
    assert allowed_host.notes == "Test host"
    assert allowed_host.created_by == "test-user"


@pytest.mark.asyncio
async def test_create_allowed_host_denylisted(test_db):
    """Test that denylisted hosts cannot be created."""
    service = AllowedHostService(database=test_db)

    with pytest.raises(ValueError) as exc_info:
        await service.add_allowed_host("localhost", "development")

    assert "denylist" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_create_allowed_host_invalid_format(test_db):
    """Test that invalid host formats are rejected."""
    service = AllowedHostService(database=test_db)

    with pytest.raises(ValueError) as exc_info:
        await service.add_allowed_host("https://example.com/path", "development")

    assert "hostname only" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_list_allowed_hosts_with_data(test_db):
    """Test listing allowed hosts after creating some."""
    service = AllowedHostService(database=test_db)

    # Create a host
    await service.add_allowed_host(
        host="api.example.com",
        environment="development"
    )

    # List hosts
    hosts = await service.get_allowed_hosts()

    assert len(hosts) >= 1
    assert any(h.host == "api.example.com" for h in hosts)


@pytest.mark.asyncio
async def test_delete_allowed_host(test_db):
    """Test deleting (disabling) an allowed host."""
    service = AllowedHostService(database=test_db)

    # Create a host first
    await service.add_allowed_host(
        host="api.example.com",
        environment="development"
    )

    # Remove it (soft delete)
    success = await service.remove_allowed_host("api.example.com", "development")

    assert success is True

    # Verify it's disabled
    hosts = await service.get_allowed_hosts(environment="development")
    matching_hosts = [h for h in hosts if h.host == "api.example.com"]
    # After soft delete, the host should either not appear or be disabled
    assert len(matching_hosts) == 0 or not matching_hosts[0].enabled


@pytest.mark.asyncio
async def test_check_host_allowed(test_db):
    """Test checking if a host is allowed."""
    service = AllowedHostService(database=test_db)

    # Create a host first
    await service.add_allowed_host(
        host="api.example.com",
        environment="development"
    )

    # Check if it's allowed
    is_allowed, error = await service.is_host_allowed(
        url="https://api.example.com/api",
        environment="development"
    )

    assert is_allowed is True
    assert error is None


@pytest.mark.asyncio
async def test_check_host_not_allowed(test_db):
    """Test checking a host that's not allowed."""
    service = AllowedHostService(database=test_db)

    # Check a host that doesn't exist in allowlist
    is_allowed, error = await service.is_host_allowed(
        url="https://unknown.example.com/api",
        environment="development"
    )

    assert is_allowed is False
    assert "not in the allowlist" in error.lower()


@pytest.mark.asyncio
async def test_check_host_denylisted(test_db):
    """Test checking a denylisted host."""
    service = AllowedHostService(database=test_db)

    # Check a denylisted host
    is_allowed, error = await service.is_host_allowed(
        url="https://localhost/api",
        environment="development"
    )

    assert is_allowed is False
    assert "denylist" in error.lower()
