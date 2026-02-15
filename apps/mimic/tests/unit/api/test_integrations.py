"""
Unit tests for Integration CRUD API routes (INT-005), Credential Management (INT-006),
and Inbound Config (INT-007).

Tests all integration management endpoints:
- POST /api/v1/integrations - Create integration
- GET /api/v1/integrations - List integrations
- GET /api/v1/integrations/{id} - Get integration details
- PUT /api/v1/integrations/{id} - Update integration
- DELETE /api/v1/integrations/{id} - Soft delete integration

Credential management (INT-006):
- POST /api/v1/integrations/{id}/credentials - Add credential
- PUT /api/v1/integrations/{id}/credentials/{cred_id} - Update credential
- DELETE /api/v1/integrations/{id}/credentials/{cred_id} - Remove credential
- POST /api/v1/integrations/{id}/credentials/{cred_id}/test - Test credential

Inbound config management (INT-007):
- PUT /api/v1/integrations/{id}/inbound - Set inbound config
- GET /api/v1/integrations/{id}/inbound - Get inbound config
- DELETE /api/v1/integrations/{id}/inbound - Delete inbound config
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.database.models import (
    Integration,
    IntegrationCredential,
    IntegrationInboundConfig,
    IntegrationOutboundConfig,
    IntegrationProvider,
    IntegrationDirection,
    IntegrationStatus,
    CredentialType,
    InboundAuthMethod,
    DestinationService,
    OutboundActionType,
)
from src.api.auth import AuthContext


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_auth_context():
    """Create a mock auth context for testing."""
    return AuthContext(
        user_id="test-user-123",
        email="test@example.com",
        organization_id="test-org-456",
        auth_type="jwt",
        token="mock-jwt-token",
    )


@pytest.fixture
def mock_inkpass_permission_check():
    """Mock InkPass permission check to always allow."""
    with patch("src.api.auth.InkPassClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_token = AsyncMock(
            return_value={
                "id": "test-user-123",
                "email": "test@example.com",
                "organization_id": "test-org-456",
            }
        )
        mock_client.check_permission = AsyncMock(return_value=True)
        yield mock_client


@pytest.fixture
def test_integration(db_session):
    """Create a test integration."""
    integration = Integration(
        id="test-integration-001",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Discord Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.bidirectional,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_configs(db_session):
    """Create a test integration with credentials and configs."""
    integration = Integration(
        id="test-integration-002",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Full Discord Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.bidirectional,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add credential
    credential = IntegrationCredential(
        id="test-cred-001",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value="encrypted_webhook_url",
        credential_metadata={"channel_name": "#general"},
        expires_at=None,
    )
    db_session.add(credential)

    # Add inbound config
    inbound_config = IntegrationInboundConfig(
        id="test-inbound-001",
        integration_id=integration.id,
        webhook_path="discord-webhook-abc123",
        auth_method=InboundAuthMethod.signature,
        destination_service=DestinationService.tentackl,
        destination_config={"task_template_id": "template-123"},
        is_active=True,
    )
    db_session.add(inbound_config)

    # Add outbound config
    outbound_config = IntegrationOutboundConfig(
        id="test-outbound-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        default_template={"content": "Default message"},
        rate_limit_requests=100,
        rate_limit_window_seconds=60,
        is_active=True,
    )
    db_session.add(outbound_config)

    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def deleted_integration(db_session):
    """Create a soft-deleted integration."""
    integration = Integration(
        id="test-integration-deleted",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Deleted Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
        deleted_at=datetime.utcnow(),
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def other_org_integration(db_session):
    """Create an integration belonging to a different organization."""
    integration = Integration(
        id="test-integration-other-org",
        organization_id="other-org-789",
        user_id="other-user-456",
        name="Other Org Integration",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


# =============================================================================
# Create Integration Tests
# =============================================================================


@pytest.mark.unit
def test_create_integration_success(client, mock_inkpass_permission_check):
    """Test successful integration creation."""
    response = client.post(
        "/api/v1/integrations",
        json={
            "name": "My Discord Bot",
            "provider": "discord",
            "direction": "bidirectional",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Discord Bot"
    assert data["provider"] == "discord"
    assert data["direction"] == "bidirectional"
    assert data["status"] == "active"
    assert "id" in data
    assert "organization_id" in data
    assert "created_at" in data


@pytest.mark.unit
def test_create_integration_minimal(client, mock_inkpass_permission_check):
    """Test creating integration with minimal fields (only required)."""
    response = client.post(
        "/api/v1/integrations",
        json={
            "name": "Minimal Integration",
            "provider": "slack",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Minimal Integration"
    assert data["provider"] == "slack"
    assert data["direction"] == "bidirectional"  # Default


@pytest.mark.unit
def test_create_integration_all_providers(client, mock_inkpass_permission_check):
    """Test creating integrations with all supported providers."""
    providers = ["discord", "slack", "github", "stripe", "custom_webhook"]

    for provider in providers:
        response = client.post(
            "/api/v1/integrations",
            json={
                "name": f"{provider.title()} Integration",
                "provider": provider,
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert response.status_code == 201
        assert response.json()["provider"] == provider


@pytest.mark.unit
def test_create_integration_invalid_provider(client, mock_inkpass_permission_check):
    """Test creating integration with invalid provider."""
    response = client.post(
        "/api/v1/integrations",
        json={
            "name": "Invalid Provider",
            "provider": "invalid_provider",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_create_integration_empty_name(client, mock_inkpass_permission_check):
    """Test creating integration with empty name."""
    response = client.post(
        "/api/v1/integrations",
        json={
            "name": "",
            "provider": "discord",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_create_integration_unauthorized(client):
    """Test creating integration without authentication."""
    response = client.post(
        "/api/v1/integrations",
        json={
            "name": "Unauthorized Integration",
            "provider": "discord",
        },
    )

    assert response.status_code == 401


# =============================================================================
# List Integrations Tests
# =============================================================================


@pytest.mark.unit
def test_list_integrations_empty(client, mock_inkpass_permission_check):
    """Test listing integrations when none exist."""
    response = client.get(
        "/api/v1/integrations",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.unit
def test_list_integrations_with_data(
    client, mock_inkpass_permission_check, test_integration
):
    """Test listing integrations with existing data."""
    response = client.get(
        "/api/v1/integrations",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Test Discord Integration"


@pytest.mark.unit
def test_list_integrations_excludes_deleted(
    client, mock_inkpass_permission_check, test_integration, deleted_integration
):
    """Test that soft-deleted integrations are excluded from listing."""
    response = client.get(
        "/api/v1/integrations",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == test_integration.id


@pytest.mark.unit
def test_list_integrations_excludes_other_org(
    client, mock_inkpass_permission_check, test_integration, other_org_integration
):
    """Test that integrations from other organizations are excluded."""
    response = client.get(
        "/api/v1/integrations",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["organization_id"] == "test-org-456"


@pytest.mark.unit
def test_list_integrations_filter_by_provider(
    client, mock_inkpass_permission_check, db_session
):
    """Test filtering integrations by provider."""
    # Create integrations with different providers
    for provider in [IntegrationProvider.discord, IntegrationProvider.slack]:
        integration = Integration(
            organization_id="test-org-456",
            user_id="test-user-123",
            name=f"{provider.value} Integration",
            provider=provider,
            direction=IntegrationDirection.bidirectional,
            status=IntegrationStatus.active,
        )
        db_session.add(integration)
    db_session.commit()

    response = client.get(
        "/api/v1/integrations?provider=discord",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["provider"] == "discord"


@pytest.mark.unit
def test_list_integrations_filter_by_status(
    client, mock_inkpass_permission_check, db_session
):
    """Test filtering integrations by status."""
    # Create integrations with different statuses
    for status in [IntegrationStatus.active, IntegrationStatus.paused, IntegrationStatus.error]:
        integration = Integration(
            organization_id="test-org-456",
            user_id="test-user-123",
            name=f"{status.value} Integration",
            provider=IntegrationProvider.discord,
            direction=IntegrationDirection.bidirectional,
            status=status,
        )
        db_session.add(integration)
    db_session.commit()

    response = client.get(
        "/api/v1/integrations?status=active",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "active"


@pytest.mark.unit
def test_list_integrations_pagination(client, mock_inkpass_permission_check, db_session):
    """Test pagination of integrations listing."""
    # Create 5 integrations
    for i in range(5):
        integration = Integration(
            organization_id="test-org-456",
            user_id="test-user-123",
            name=f"Integration {i}",
            provider=IntegrationProvider.discord,
            direction=IntegrationDirection.bidirectional,
            status=IntegrationStatus.active,
        )
        db_session.add(integration)
    db_session.commit()

    # Get first page
    response = client.get(
        "/api/v1/integrations?limit=2&offset=0",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5

    # Get second page
    response = client.get(
        "/api/v1/integrations?limit=2&offset=2",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2


# =============================================================================
# Get Integration Tests
# =============================================================================


@pytest.mark.unit
def test_get_integration_success(
    client, mock_inkpass_permission_check, test_integration
):
    """Test getting integration details."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_integration.id
    assert data["name"] == "Test Discord Integration"
    assert data["provider"] == "discord"
    assert "credentials" in data
    assert "inbound_config" in data
    assert "outbound_config" in data


@pytest.mark.unit
def test_get_integration_with_configs(
    client, mock_inkpass_permission_check, test_integration_with_configs
):
    """Test getting integration with all related configurations."""
    response = client.get(
        f"/api/v1/integrations/{test_integration_with_configs.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check credentials (should not contain sensitive data)
    assert len(data["credentials"]) == 1
    assert data["credentials"][0]["credential_type"] == "webhook_url"
    assert "encrypted_value" not in data["credentials"][0]

    # Check inbound config
    assert data["inbound_config"] is not None
    assert data["inbound_config"]["webhook_path"] == "discord-webhook-abc123"
    assert "webhook_url" in data["inbound_config"]

    # Check outbound config
    assert data["outbound_config"] is not None
    assert data["outbound_config"]["action_type"] == "send_message"
    assert data["outbound_config"]["has_rate_limit"] is True


@pytest.mark.unit
def test_get_integration_not_found(client, mock_inkpass_permission_check):
    """Test getting non-existent integration."""
    response = client.get(
        "/api/v1/integrations/non-existent-id",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_get_integration_deleted(
    client, mock_inkpass_permission_check, deleted_integration
):
    """Test that deleted integrations return 404."""
    response = client.get(
        f"/api/v1/integrations/{deleted_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_get_integration_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that integrations from other organizations return 404."""
    response = client.get(
        f"/api/v1/integrations/{other_org_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Update Integration Tests
# =============================================================================


@pytest.mark.unit
def test_update_integration_name(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating integration name."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={"name": "Updated Integration Name"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Integration Name"


@pytest.mark.unit
def test_update_integration_status(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating integration status."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={"status": "paused"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paused"


@pytest.mark.unit
def test_update_integration_direction(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating integration direction."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={"direction": "outbound"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["direction"] == "outbound"


@pytest.mark.unit
def test_update_integration_multiple_fields(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating multiple fields at once."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={
            "name": "Fully Updated",
            "status": "error",
            "direction": "inbound",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Fully Updated"
    assert data["status"] == "error"
    assert data["direction"] == "inbound"


@pytest.mark.unit
def test_update_integration_not_found(client, mock_inkpass_permission_check):
    """Test updating non-existent integration."""
    response = client.put(
        "/api/v1/integrations/non-existent-id",
        json={"name": "Updated"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_update_integration_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that updating integration from other org returns 404."""
    response = client.put(
        f"/api/v1/integrations/{other_org_integration.id}",
        json={"name": "Hacked Name"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_update_integration_invalid_status(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating with invalid status value."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={"status": "invalid_status"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422


# =============================================================================
# Delete Integration Tests
# =============================================================================


@pytest.mark.unit
def test_delete_integration_success(
    client, mock_inkpass_permission_check, test_integration, db_session
):
    """Test soft deleting an integration."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 204

    # Verify soft delete
    db_session.refresh(test_integration)
    assert test_integration.deleted_at is not None


@pytest.mark.unit
def test_delete_integration_not_found(client, mock_inkpass_permission_check):
    """Test deleting non-existent integration."""
    response = client.delete(
        "/api/v1/integrations/non-existent-id",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_integration_already_deleted(
    client, mock_inkpass_permission_check, deleted_integration
):
    """Test deleting already deleted integration returns 404."""
    response = client.delete(
        f"/api/v1/integrations/{deleted_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_integration_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that deleting integration from other org returns 404."""
    response = client.delete(
        f"/api/v1/integrations/{other_org_integration.id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_integration_cascades_configs(
    client, mock_inkpass_permission_check, test_integration_with_configs, db_session
):
    """Test that deleting integration marks it as deleted (configs remain for audit)."""
    integration_id = test_integration_with_configs.id

    response = client.delete(
        f"/api/v1/integrations/{integration_id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 204

    # Integration should be soft-deleted
    integration = db_session.query(Integration).filter(
        Integration.id == integration_id
    ).first()
    assert integration is not None
    assert integration.deleted_at is not None


# =============================================================================
# Authorization Tests
# =============================================================================


@pytest.mark.unit
def test_list_integrations_unauthorized(client):
    """Test listing integrations without authentication."""
    response = client.get("/api/v1/integrations")
    assert response.status_code == 401


@pytest.mark.unit
def test_get_integration_unauthorized(client, test_integration):
    """Test getting integration without authentication."""
    response = client.get(f"/api/v1/integrations/{test_integration.id}")
    assert response.status_code == 401


@pytest.mark.unit
def test_update_integration_unauthorized(client, test_integration):
    """Test updating integration without authentication."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_delete_integration_unauthorized(client, test_integration):
    """Test deleting integration without authentication."""
    response = client.delete(f"/api/v1/integrations/{test_integration.id}")
    assert response.status_code == 401


# =============================================================================
# Credential Management Tests (INT-006)
# =============================================================================


@pytest.fixture
def mock_encryption_service():
    """Mock encryption service."""
    with patch("src.api.routes.integrations.encryption_service") as mock:
        mock.encrypt.return_value = "encrypted_value_mock"
        mock.decrypt.return_value = "decrypted_value_mock"
        yield mock


@pytest.fixture
def mock_validator_service():
    """Mock provider validator service."""
    with patch("src.api.routes.integrations.validator_service") as mock:
        mock._validate_discord = AsyncMock(return_value=True)
        mock._validate_slack = AsyncMock(return_value=True)
        mock._validate_webhook = AsyncMock(return_value=True)
        yield mock


@pytest.fixture
def test_credential(db_session, test_integration):
    """Create a test credential."""
    credential = IntegrationCredential(
        id="test-cred-standalone",
        integration_id=test_integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value="encrypted_webhook_url_value",
        credential_metadata={"channel": "#general"},
        expires_at=None,
    )
    db_session.add(credential)
    db_session.commit()
    db_session.refresh(credential)
    return credential


@pytest.fixture
def expired_credential(db_session, test_integration):
    """Create an expired credential."""
    credential = IntegrationCredential(
        id="test-cred-expired",
        integration_id=test_integration.id,
        credential_type=CredentialType.oauth_token,
        encrypted_value="encrypted_oauth_token",
        credential_metadata={"scopes": ["read", "write"]},
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(credential)
    db_session.commit()
    db_session.refresh(credential)
    return credential


# =============================================================================
# Create Credential Tests
# =============================================================================


@pytest.mark.unit
def test_create_credential_success(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration
):
    """Test successful credential creation."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        json={
            "credential_type": "webhook_url",
            "value": "https://discord.com/api/webhooks/123/abc",
            "metadata": {"channel_name": "#alerts"},
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["credential_type"] == "webhook_url"
    assert data["has_value"] is True
    assert data["metadata"] == {"channel_name": "#alerts"}
    assert "id" in data
    assert "value" not in data  # Credentials never returned in plaintext
    assert "encrypted_value" not in data

    # Verify encryption was called
    mock_encryption_service.encrypt.assert_called_once_with(
        "https://discord.com/api/webhooks/123/abc"
    )


@pytest.mark.unit
def test_create_credential_with_expiration(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration
):
    """Test creating credential with expiration date."""
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()

    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        json={
            "credential_type": "oauth_token",
            "value": "oauth_access_token_123",
            "expires_at": expires_at,
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["credential_type"] == "oauth_token"
    assert data["has_expiration"] is True
    assert data["is_expired"] is False


@pytest.mark.unit
def test_create_credential_all_types(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration
):
    """Test creating credentials with all supported types."""
    types = ["api_key", "oauth_token", "webhook_url", "bot_token", "webhook_secret"]

    for cred_type in types:
        response = client.post(
            f"/api/v1/integrations/{test_integration.id}/credentials",
            json={
                "credential_type": cred_type,
                "value": f"test_value_for_{cred_type}",
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert response.status_code == 201
        assert response.json()["credential_type"] == cred_type


@pytest.mark.unit
def test_create_credential_invalid_type(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating credential with invalid type."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        json={
            "credential_type": "invalid_type",
            "value": "some_value",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_create_credential_empty_value(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating credential with empty value."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        json={
            "credential_type": "api_key",
            "value": "",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_create_credential_integration_not_found(
    client, mock_inkpass_permission_check
):
    """Test creating credential for non-existent integration."""
    response = client.post(
        "/api/v1/integrations/non-existent-id/credentials",
        json={
            "credential_type": "api_key",
            "value": "some_value",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_create_credential_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that creating credential for other org's integration returns 404."""
    response = client.post(
        f"/api/v1/integrations/{other_org_integration.id}/credentials",
        json={
            "credential_type": "api_key",
            "value": "some_value",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# List Credentials Tests
# =============================================================================


@pytest.mark.unit
def test_list_credentials_success(
    client, mock_inkpass_permission_check, test_integration, test_credential
):
    """Test listing credentials for an integration."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == test_credential.id
    assert data[0]["credential_type"] == "webhook_url"
    assert data[0]["has_value"] is True
    # Ensure no sensitive data
    assert "encrypted_value" not in data[0]
    assert "value" not in data[0]


@pytest.mark.unit
def test_list_credentials_empty(
    client, mock_inkpass_permission_check, test_integration
):
    """Test listing credentials when none exist."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.unit
def test_list_credentials_multiple(
    client, mock_inkpass_permission_check, db_session, test_integration
):
    """Test listing multiple credentials."""
    # Create multiple credentials
    for i, cred_type in enumerate([CredentialType.api_key, CredentialType.webhook_url]):
        credential = IntegrationCredential(
            id=f"multi-cred-{i}",
            integration_id=test_integration.id,
            credential_type=cred_type,
            encrypted_value=f"encrypted_value_{i}",
        )
        db_session.add(credential)
    db_session.commit()

    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.unit
def test_list_credentials_shows_expired(
    client, mock_inkpass_permission_check, test_integration, expired_credential
):
    """Test that expired credentials are listed with is_expired flag."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["is_expired"] is True


# =============================================================================
# Update Credential Tests
# =============================================================================


@pytest.mark.unit
def test_update_credential_value(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration, test_credential
):
    """Test updating credential value."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}",
        json={"value": "new_webhook_url"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_value"] is True
    mock_encryption_service.encrypt.assert_called_with("new_webhook_url")


@pytest.mark.unit
def test_update_credential_metadata(
    client, mock_inkpass_permission_check, test_integration, test_credential
):
    """Test updating credential metadata."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}",
        json={"metadata": {"channel": "#updated-channel", "new_field": "value"}},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == {"channel": "#updated-channel", "new_field": "value"}


@pytest.mark.unit
def test_update_credential_expiration(
    client, mock_inkpass_permission_check, test_integration, test_credential
):
    """Test updating credential expiration."""
    new_expiry = (datetime.utcnow() + timedelta(days=60)).isoformat()

    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}",
        json={"expires_at": new_expiry},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_expiration"] is True
    assert data["is_expired"] is False


@pytest.mark.unit
def test_update_credential_not_found(
    client, mock_inkpass_permission_check, test_integration
):
    """Test updating non-existent credential."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/credentials/non-existent",
        json={"metadata": {"key": "value"}},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_update_credential_wrong_integration(
    client, mock_inkpass_permission_check, db_session
):
    """Test updating credential from different integration."""
    # Create two integrations
    int1 = Integration(
        id="int-1",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Integration 1",
        provider=IntegrationProvider.discord,
    )
    int2 = Integration(
        id="int-2",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Integration 2",
        provider=IntegrationProvider.slack,
    )
    db_session.add(int1)
    db_session.add(int2)

    # Create credential for int1
    cred = IntegrationCredential(
        id="cred-in-int1",
        integration_id="int-1",
        credential_type=CredentialType.api_key,
        encrypted_value="encrypted",
    )
    db_session.add(cred)
    db_session.commit()

    # Try to update cred via int2
    response = client.put(
        f"/api/v1/integrations/int-2/credentials/cred-in-int1",
        json={"metadata": {"hack": "attempt"}},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Delete Credential Tests
# =============================================================================


@pytest.mark.unit
def test_delete_credential_success(
    client, mock_inkpass_permission_check, test_integration, test_credential, db_session
):
    """Test deleting a credential."""
    cred_id = test_credential.id

    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/credentials/{cred_id}",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 204

    # Verify hard delete
    deleted = db_session.query(IntegrationCredential).filter(
        IntegrationCredential.id == cred_id
    ).first()
    assert deleted is None


@pytest.mark.unit
def test_delete_credential_not_found(
    client, mock_inkpass_permission_check, test_integration
):
    """Test deleting non-existent credential."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/credentials/non-existent",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_credential_other_org(
    client, mock_inkpass_permission_check, other_org_integration, db_session
):
    """Test deleting credential from other org's integration."""
    # Create credential for other org's integration
    cred = IntegrationCredential(
        id="other-org-cred",
        integration_id=other_org_integration.id,
        credential_type=CredentialType.api_key,
        encrypted_value="encrypted",
    )
    db_session.add(cred)
    db_session.commit()

    response = client.delete(
        f"/api/v1/integrations/{other_org_integration.id}/credentials/other-org-cred",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Test Credential Tests
# =============================================================================


@pytest.mark.unit
def test_test_credential_webhook_success(
    client, mock_inkpass_permission_check, mock_encryption_service, mock_validator_service,
    test_integration, test_credential
):
    """Test successful webhook credential validation."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}/test",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "discord" in data["message"]  # Provider name in message


@pytest.mark.unit
def test_test_credential_webhook_failure(
    client, mock_inkpass_permission_check, mock_encryption_service,
    test_integration, test_credential
):
    """Test failed webhook credential validation."""
    with patch("src.api.routes.integrations.validator_service") as mock_validator:
        mock_validator._validate_discord = AsyncMock(return_value=False)

        response = client.post(
            f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}/test",
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


@pytest.mark.unit
def test_test_credential_api_key_github(
    client, mock_inkpass_permission_check, mock_encryption_service, db_session
):
    """Test GitHub API key validation."""
    # Create GitHub integration with API key
    integration = Integration(
        id="github-int",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="GitHub Integration",
        provider=IntegrationProvider.github,
    )
    db_session.add(integration)

    cred = IntegrationCredential(
        id="github-cred",
        integration_id="github-int",
        credential_type=CredentialType.api_key,
        encrypted_value="encrypted_github_token",
    )
    db_session.add(cred)
    db_session.commit()

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        response = client.post(
            "/api/v1/integrations/github-int/credentials/github-cred/test",
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.unit
def test_test_credential_bot_token_discord(
    client, mock_inkpass_permission_check, mock_encryption_service, db_session
):
    """Test Discord bot token validation."""
    # Create Discord integration with bot token
    integration = Integration(
        id="discord-bot-int",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Discord Bot Integration",
        provider=IntegrationProvider.discord,
    )
    db_session.add(integration)

    cred = IntegrationCredential(
        id="discord-bot-cred",
        integration_id="discord-bot-int",
        credential_type=CredentialType.bot_token,
        encrypted_value="encrypted_bot_token",
    )
    db_session.add(cred)
    db_session.commit()

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        response = client.post(
            "/api/v1/integrations/discord-bot-int/credentials/discord-bot-cred/test",
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.unit
def test_test_credential_oauth_not_expired(
    client, mock_inkpass_permission_check, mock_encryption_service, db_session
):
    """Test OAuth token validation (not expired)."""
    integration = Integration(
        id="oauth-int",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="OAuth Integration",
        provider=IntegrationProvider.github,
    )
    db_session.add(integration)

    cred = IntegrationCredential(
        id="oauth-cred",
        integration_id="oauth-int",
        credential_type=CredentialType.oauth_token,
        encrypted_value="encrypted_oauth_token",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db_session.add(cred)
    db_session.commit()

    response = client.post(
        "/api/v1/integrations/oauth-int/credentials/oauth-cred/test",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.unit
def test_test_credential_oauth_expired(
    client, mock_inkpass_permission_check, mock_encryption_service, db_session
):
    """Test OAuth token validation (expired)."""
    integration = Integration(
        id="oauth-expired-int",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="OAuth Expired Integration",
        provider=IntegrationProvider.github,
    )
    db_session.add(integration)

    cred = IntegrationCredential(
        id="oauth-expired-cred",
        integration_id="oauth-expired-int",
        credential_type=CredentialType.oauth_token,
        encrypted_value="encrypted_oauth_token",
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(cred)
    db_session.commit()

    response = client.post(
        "/api/v1/integrations/oauth-expired-int/credentials/oauth-expired-cred/test",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.unit
def test_test_credential_webhook_secret(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration, db_session
):
    """Test webhook secret validation (just checks existence)."""
    cred = IntegrationCredential(
        id="webhook-secret-cred",
        integration_id=test_integration.id,
        credential_type=CredentialType.webhook_secret,
        encrypted_value="encrypted_secret",
    )
    db_session.add(cred)
    db_session.commit()

    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials/webhook-secret-cred/test",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True  # Webhook secrets just need to exist


@pytest.mark.unit
def test_test_credential_not_found(
    client, mock_inkpass_permission_check, test_integration
):
    """Test testing non-existent credential."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials/non-existent/test",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_test_credential_decrypt_failure(
    client, mock_inkpass_permission_check, test_integration, test_credential
):
    """Test credential test when decryption fails."""
    with patch("src.api.routes.integrations.encryption_service") as mock_enc:
        mock_enc.decrypt.side_effect = Exception("Decryption failed")

        response = client.post(
            f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}/test",
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "decrypt" in data["message"].lower()


# =============================================================================
# Authorization Tests for Credentials
# =============================================================================


@pytest.mark.unit
def test_create_credential_unauthorized(client, test_integration):
    """Test creating credential without authentication."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials",
        json={"credential_type": "api_key", "value": "test"},
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_list_credentials_unauthorized(client, test_integration):
    """Test listing credentials without authentication."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/credentials",
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_update_credential_unauthorized(client, test_integration, test_credential):
    """Test updating credential without authentication."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}",
        json={"metadata": {"key": "value"}},
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_delete_credential_unauthorized(client, test_integration, test_credential):
    """Test deleting credential without authentication."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}",
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_test_credential_unauthorized(client, test_integration, test_credential):
    """Test testing credential without authentication."""
    response = client.post(
        f"/api/v1/integrations/{test_integration.id}/credentials/{test_credential.id}/test",
    )
    assert response.status_code == 401


# =============================================================================
# Inbound Config Tests (INT-007)
# =============================================================================


@pytest.fixture
def outbound_only_integration(db_session):
    """Create an outbound-only integration."""
    integration = Integration(
        id="test-outbound-only",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Outbound Only Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_inbound_config(db_session, test_integration):
    """Create a test inbound config."""
    config = IntegrationInboundConfig(
        id="test-inbound-standalone",
        integration_id=test_integration.id,
        webhook_path="wh-test-abc123",
        auth_method=InboundAuthMethod.signature,
        signature_secret="encrypted_secret_value",
        event_filters=["push", "pull_request"],
        transform_template="{{ payload | tojson }}",
        destination_service=DestinationService.tentackl,
        destination_config={"task_template_id": "template-123"},
        is_active=True,
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


# =============================================================================
# Set Inbound Config Tests (PUT)
# =============================================================================


@pytest.mark.unit
def test_set_inbound_config_create_success(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration
):
    """Test successful creation of inbound config."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={
            "webhook_path": "wh-my-webhook",
            "auth_method": "signature",
            "signature_secret": "my-hmac-secret",
            "event_filters": ["push", "release"],
            "destination_service": "tentackl",
            "destination_config": {"task_template_id": "tmpl-123"},
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["webhook_path"] == "wh-my-webhook"
    assert data["auth_method"] == "signature"
    assert data["has_signature_secret"] is True
    assert data["event_filters"] == ["push", "release"]
    assert data["destination_service"] == "tentackl"
    assert data["destination_config"] == {"task_template_id": "tmpl-123"}
    assert data["is_active"] is True
    assert "webhook_url" in data
    assert "wh-my-webhook" in data["webhook_url"]


@pytest.mark.unit
def test_set_inbound_config_auto_generate_path(
    client, mock_inkpass_permission_check, test_integration
):
    """Test that webhook_path is auto-generated when not provided."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={
            "auth_method": "none",
            "destination_service": "tentackl",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["webhook_path"].startswith("wh-")
    assert len(data["webhook_path"]) > 5  # wh- plus some random chars


@pytest.mark.unit
def test_set_inbound_config_update_existing(
    client, mock_inkpass_permission_check, mock_encryption_service, test_integration, test_inbound_config
):
    """Test updating existing inbound config."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={
            "webhook_path": "wh-updated-path",
            "auth_method": "api_key",
            "event_filters": ["updated_event"],
            "destination_service": "tentackl",
            "destination_config": {"task_template_id": "tmpl-123"},
            "is_active": False,
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["webhook_path"] == "wh-updated-path"
    assert data["auth_method"] == "api_key"
    assert data["event_filters"] == ["updated_event"]
    assert data["destination_service"] == "tentackl"
    assert data["is_active"] is False


@pytest.mark.unit
def test_set_inbound_config_minimal(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating inbound config with minimal fields (defaults)."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={},  # All defaults
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["auth_method"] == "none"  # Default
    assert data["destination_service"] == "tentackl"  # Default
    assert data["is_active"] is True  # Default
    assert data["webhook_path"].startswith("wh-")


@pytest.mark.unit
def test_set_inbound_config_all_auth_methods(
    client, mock_inkpass_permission_check, db_session
):
    """Test creating inbound config with all auth methods."""
    auth_methods = ["api_key", "signature", "bearer", "none"]

    for i, method in enumerate(auth_methods):
        integration = Integration(
            id=f"auth-method-int-{i}",
            organization_id="test-org-456",
            user_id="test-user-123",
            name=f"{method} Auth Integration",
            provider=IntegrationProvider.custom_webhook,
            direction=IntegrationDirection.inbound,
        )
        db_session.add(integration)
        db_session.commit()

        response = client.put(
            f"/api/v1/integrations/auth-method-int-{i}/inbound",
            json={"auth_method": method},
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        assert response.json()["auth_method"] == method


@pytest.mark.unit
def test_set_inbound_config_all_destinations(
    client, mock_inkpass_permission_check, db_session
):
    """Test creating inbound config with all destination services."""
    destinations = ["tentackl", "custom"]

    for i, dest in enumerate(destinations):
        integration = Integration(
            id=f"dest-int-{i}",
            organization_id="test-org-456",
            user_id="test-user-123",
            name=f"{dest} Destination Integration",
            provider=IntegrationProvider.github,
            direction=IntegrationDirection.inbound,
        )
        db_session.add(integration)
        db_session.commit()

        response = client.put(
            f"/api/v1/integrations/dest-int-{i}/inbound",
            json={"destination_service": dest},
            headers={"Authorization": "Bearer mock-token"},
        )

        assert response.status_code == 200
        assert response.json()["destination_service"] == dest


@pytest.mark.unit
def test_set_inbound_config_outbound_only_fails(
    client, mock_inkpass_permission_check, outbound_only_integration
):
    """Test that inbound config fails for outbound-only integration."""
    response = client.put(
        f"/api/v1/integrations/{outbound_only_integration.id}/inbound",
        json={"auth_method": "none"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    assert "outbound" in response.json()["detail"].lower()


@pytest.mark.unit
def test_set_inbound_config_duplicate_path_fails(
    client, mock_inkpass_permission_check, test_integration, test_inbound_config, db_session
):
    """Test that duplicate webhook_path returns conflict error."""
    # Create another integration
    other_integration = Integration(
        id="other-int-for-conflict",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Other Integration",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.bidirectional,
    )
    db_session.add(other_integration)
    db_session.commit()

    # Try to use the same webhook_path as test_inbound_config
    response = client.put(
        f"/api/v1/integrations/{other_integration.id}/inbound",
        json={"webhook_path": test_inbound_config.webhook_path},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 409
    assert "already in use" in response.json()["detail"]


@pytest.mark.unit
def test_set_inbound_config_same_integration_path_update(
    client, mock_inkpass_permission_check, test_integration, test_inbound_config
):
    """Test that same integration can keep its own webhook_path on update."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={
            "webhook_path": test_inbound_config.webhook_path,  # Same path
            "auth_method": "bearer",  # Changed
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    assert response.json()["webhook_path"] == test_inbound_config.webhook_path
    assert response.json()["auth_method"] == "bearer"


@pytest.mark.unit
def test_set_inbound_config_invalid_path_format(
    client, mock_inkpass_permission_check, test_integration
):
    """Test that invalid webhook_path format returns validation error."""
    # Path with invalid characters
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={"webhook_path": "INVALID-CAPS"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422

    # Path starting with hyphen
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={"webhook_path": "-invalid"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422

    # Path too short
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={"webhook_path": "ab"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422


@pytest.mark.unit
def test_set_inbound_config_not_found(client, mock_inkpass_permission_check):
    """Test setting inbound config for non-existent integration."""
    response = client.put(
        "/api/v1/integrations/non-existent-id/inbound",
        json={"auth_method": "none"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_set_inbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that setting inbound config for other org's integration returns 404."""
    response = client.put(
        f"/api/v1/integrations/{other_org_integration.id}/inbound",
        json={"auth_method": "none"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_set_inbound_config_with_transform_template(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating inbound config with Jinja2 transform template."""
    template = """
{
  "event_type": "{{ event.type }}",
  "timestamp": "{{ event.created_at }}",
  "source": "github",
  "data": {{ payload | tojson }}
}
"""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={
            "transform_template": template,
            "destination_service": "tentackl",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transform_template"] == template


# =============================================================================
# Get Inbound Config Tests (GET)
# =============================================================================


@pytest.mark.unit
def test_get_inbound_config_success(
    client, mock_inkpass_permission_check, test_integration, test_inbound_config
):
    """Test getting inbound config successfully."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_inbound_config.id
    assert data["webhook_path"] == test_inbound_config.webhook_path
    assert data["auth_method"] == "signature"
    assert data["event_filters"] == ["push", "pull_request"]
    assert data["destination_service"] == "tentackl"
    assert "webhook_url" in data
    assert test_inbound_config.webhook_path in data["webhook_url"]


@pytest.mark.unit
def test_get_inbound_config_includes_full_url(
    client, mock_inkpass_permission_check, test_integration, test_inbound_config
):
    """Test that response includes full webhook URL."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    # URL should contain the base gateway path and the webhook path
    assert "gateway/integrations/" in data["webhook_url"]
    assert test_inbound_config.webhook_path in data["webhook_url"]


@pytest.mark.unit
def test_get_inbound_config_not_configured(
    client, mock_inkpass_permission_check, test_integration
):
    """Test getting inbound config when none exists."""
    # test_integration without inbound config
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
def test_get_inbound_config_integration_not_found(client, mock_inkpass_permission_check):
    """Test getting inbound config for non-existent integration."""
    response = client.get(
        "/api/v1/integrations/non-existent-id/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_get_inbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that getting inbound config for other org's integration returns 404."""
    response = client.get(
        f"/api/v1/integrations/{other_org_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Delete Inbound Config Tests (DELETE)
# =============================================================================


@pytest.mark.unit
def test_delete_inbound_config_success(
    client, mock_inkpass_permission_check, test_integration, test_inbound_config, db_session
):
    """Test successful deletion of inbound config."""
    config_id = test_inbound_config.id

    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 204

    # Verify hard delete
    deleted = db_session.query(IntegrationInboundConfig).filter(
        IntegrationInboundConfig.id == config_id
    ).first()
    assert deleted is None


@pytest.mark.unit
def test_delete_inbound_config_not_configured(
    client, mock_inkpass_permission_check, test_integration
):
    """Test deleting inbound config when none exists."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_inbound_config_integration_not_found(client, mock_inkpass_permission_check):
    """Test deleting inbound config for non-existent integration."""
    response = client.delete(
        "/api/v1/integrations/non-existent-id/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_inbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that deleting inbound config for other org's integration returns 404."""
    response = client.delete(
        f"/api/v1/integrations/{other_org_integration.id}/inbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Authorization Tests for Inbound Config
# =============================================================================


@pytest.mark.unit
def test_set_inbound_config_unauthorized(client, test_integration):
    """Test setting inbound config without authentication."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/inbound",
        json={"auth_method": "none"},
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_get_inbound_config_unauthorized(client, test_integration):
    """Test getting inbound config without authentication."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/inbound",
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_delete_inbound_config_unauthorized(client, test_integration):
    """Test deleting inbound config without authentication."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/inbound",
    )
    assert response.status_code == 401


# =============================================================================
# Outbound Config Tests (INT-008)
# =============================================================================


@pytest.fixture
def inbound_only_integration(db_session):
    """Create an inbound-only integration."""
    integration = Integration(
        id="test-inbound-only",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Inbound Only Integration",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_outbound_config(db_session, test_integration):
    """Create a test outbound config."""
    config = IntegrationOutboundConfig(
        id="test-outbound-standalone",
        integration_id=test_integration.id,
        action_type=OutboundActionType.send_message,
        default_template={"content": "Hello, {{name}}!"},
        rate_limit_requests=100,
        rate_limit_window_seconds=60,
        is_active=True,
    )
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


# =============================================================================
# Set Outbound Config Tests (PUT)
# =============================================================================


@pytest.mark.unit
def test_set_outbound_config_create_success(
    client, mock_inkpass_permission_check, test_integration
):
    """Test successful creation of outbound config."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_message",
            "default_template": {"content": "Hello from Mimic!"},
            "rate_limit_requests": 100,
            "rate_limit_window_seconds": 60,
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "send_message"
    assert data["default_template"] == {"content": "Hello from Mimic!"}
    assert data["rate_limit_requests"] == 100
    assert data["rate_limit_window_seconds"] == 60
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.unit
def test_set_outbound_config_create_discord_embed(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating Discord embed outbound config."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_embed",
            "default_template": {
                "title": "Alert",
                "description": "Something happened",
                "color": 16711680,
            },
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "send_embed"
    assert data["default_template"]["title"] == "Alert"


@pytest.mark.unit
def test_set_outbound_config_update_existing(
    client, mock_inkpass_permission_check, test_integration, test_outbound_config
):
    """Test updating existing outbound config."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_embed",  # Changed from send_message
            "default_template": {"title": "Updated Template"},
            "rate_limit_requests": 200,
            "rate_limit_window_seconds": 120,
            "is_active": False,
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "send_embed"
    assert data["default_template"] == {"title": "Updated Template"}
    assert data["rate_limit_requests"] == 200
    assert data["rate_limit_window_seconds"] == 120
    assert data["is_active"] is False


@pytest.mark.unit
def test_set_outbound_config_minimal(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating outbound config with minimal fields (only required)."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_message",
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "send_message"
    assert data["default_template"] is None
    assert data["rate_limit_requests"] is None
    assert data["rate_limit_window_seconds"] is None
    assert data["is_active"] is True  # Default


@pytest.mark.unit
def test_set_outbound_config_inbound_only_fails(
    client, mock_inkpass_permission_check, inbound_only_integration
):
    """Test that outbound config fails for inbound-only integration."""
    response = client.put(
        f"/api/v1/integrations/{inbound_only_integration.id}/outbound",
        json={"action_type": "create_issue"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    assert "inbound-only" in response.json()["detail"].lower()


@pytest.mark.unit
def test_set_outbound_config_invalid_action_for_provider(
    client, mock_inkpass_permission_check, test_integration
):
    """Test that invalid action_type for provider returns error."""
    # Discord doesn't support create_issue
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={"action_type": "create_issue"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()
    assert "discord" in response.json()["detail"].lower()


@pytest.mark.unit
def test_set_outbound_config_slack_blocks(
    client, mock_inkpass_permission_check, db_session
):
    """Test creating Slack Block Kit outbound config."""
    integration = Integration(
        id="slack-int-for-blocks",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Slack Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
    )
    db_session.add(integration)
    db_session.commit()

    response = client.put(
        f"/api/v1/integrations/{integration.id}/outbound",
        json={
            "action_type": "send_blocks",
            "default_template": {
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}
                ]
            },
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    assert response.json()["action_type"] == "send_blocks"


@pytest.mark.unit
def test_set_outbound_config_github_create_issue(
    client, mock_inkpass_permission_check, db_session
):
    """Test creating GitHub create_issue outbound config."""
    integration = Integration(
        id="github-int-for-issue",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="GitHub Integration",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.outbound,
    )
    db_session.add(integration)
    db_session.commit()

    response = client.put(
        f"/api/v1/integrations/{integration.id}/outbound",
        json={
            "action_type": "create_issue",
            "default_template": {
                "title": "Bug Report: {{title}}",
                "body": "{{description}}",
                "labels": ["bug"],
            },
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    assert response.json()["action_type"] == "create_issue"


@pytest.mark.unit
def test_set_outbound_config_custom_webhook_post(
    client, mock_inkpass_permission_check, db_session
):
    """Test creating custom webhook POST outbound config."""
    integration = Integration(
        id="custom-webhook-int",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Custom Webhook Integration",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.bidirectional,
    )
    db_session.add(integration)
    db_session.commit()

    response = client.put(
        f"/api/v1/integrations/{integration.id}/outbound",
        json={
            "action_type": "post",
            "default_template": {"event": "notification", "data": "{{payload}}"},
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    assert response.json()["action_type"] == "post"


@pytest.mark.unit
def test_set_outbound_config_stripe_not_supported(
    client, mock_inkpass_permission_check, db_session
):
    """Test that Stripe provider doesn't support outbound actions."""
    integration = Integration(
        id="stripe-int-outbound",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Stripe Integration",
        provider=IntegrationProvider.stripe,
        direction=IntegrationDirection.bidirectional,
    )
    db_session.add(integration)
    db_session.commit()

    response = client.put(
        f"/api/v1/integrations/{integration.id}/outbound",
        json={"action_type": "send_message"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    assert "does not support outbound actions" in response.json()["detail"]


@pytest.mark.unit
def test_set_outbound_config_invalid_action_type(
    client, mock_inkpass_permission_check, test_integration
):
    """Test creating outbound config with invalid action type."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={"action_type": "invalid_action"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.unit
def test_set_outbound_config_not_found(client, mock_inkpass_permission_check):
    """Test setting outbound config for non-existent integration."""
    response = client.put(
        "/api/v1/integrations/non-existent-id/outbound",
        json={"action_type": "send_message"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_set_outbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that setting outbound config for other org's integration returns 404."""
    response = client.put(
        f"/api/v1/integrations/{other_org_integration.id}/outbound",
        json={"action_type": "create_issue"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_set_outbound_config_rate_limit_validation(
    client, mock_inkpass_permission_check, test_integration
):
    """Test rate limit validation bounds."""
    # rate_limit_requests too low
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_message",
            "rate_limit_requests": 0,
        },
        headers={"Authorization": "Bearer mock-token"},
    )
    assert response.status_code == 422

    # rate_limit_window_seconds too high
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={
            "action_type": "send_message",
            "rate_limit_window_seconds": 100000,  # > 86400 (24 hours)
        },
        headers={"Authorization": "Bearer mock-token"},
    )
    assert response.status_code == 422


# =============================================================================
# Get Outbound Config Tests (GET)
# =============================================================================


@pytest.mark.unit
def test_get_outbound_config_success(
    client, mock_inkpass_permission_check, test_integration, test_outbound_config
):
    """Test getting outbound config successfully."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_outbound_config.id
    assert data["action_type"] == "send_message"
    assert data["default_template"] == {"content": "Hello, {{name}}!"}
    assert data["rate_limit_requests"] == 100
    assert data["rate_limit_window_seconds"] == 60
    assert data["is_active"] is True


@pytest.mark.unit
def test_get_outbound_config_not_configured(
    client, mock_inkpass_permission_check, test_integration
):
    """Test getting outbound config when none exists."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
def test_get_outbound_config_integration_not_found(client, mock_inkpass_permission_check):
    """Test getting outbound config for non-existent integration."""
    response = client.get(
        "/api/v1/integrations/non-existent-id/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_get_outbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that getting outbound config for other org's integration returns 404."""
    response = client.get(
        f"/api/v1/integrations/{other_org_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Delete Outbound Config Tests (DELETE)
# =============================================================================


@pytest.mark.unit
def test_delete_outbound_config_success(
    client, mock_inkpass_permission_check, test_integration, test_outbound_config, db_session
):
    """Test successful deletion of outbound config."""
    config_id = test_outbound_config.id

    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 204

    # Verify hard delete
    deleted = db_session.query(IntegrationOutboundConfig).filter(
        IntegrationOutboundConfig.id == config_id
    ).first()
    assert deleted is None


@pytest.mark.unit
def test_delete_outbound_config_not_configured(
    client, mock_inkpass_permission_check, test_integration
):
    """Test deleting outbound config when none exists."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_outbound_config_integration_not_found(client, mock_inkpass_permission_check):
    """Test deleting outbound config for non-existent integration."""
    response = client.delete(
        "/api/v1/integrations/non-existent-id/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_delete_outbound_config_other_org(
    client, mock_inkpass_permission_check, other_org_integration
):
    """Test that deleting outbound config for other org's integration returns 404."""
    response = client.delete(
        f"/api/v1/integrations/{other_org_integration.id}/outbound",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


# =============================================================================
# Authorization Tests for Outbound Config
# =============================================================================


@pytest.mark.unit
def test_set_outbound_config_unauthorized(client, test_integration):
    """Test setting outbound config without authentication."""
    response = client.put(
        f"/api/v1/integrations/{test_integration.id}/outbound",
        json={"action_type": "send_message"},
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_get_outbound_config_unauthorized(client, test_integration):
    """Test getting outbound config without authentication."""
    response = client.get(
        f"/api/v1/integrations/{test_integration.id}/outbound",
    )
    assert response.status_code == 401


@pytest.mark.unit
def test_delete_outbound_config_unauthorized(client, test_integration):
    """Test deleting outbound config without authentication."""
    response = client.delete(
        f"/api/v1/integrations/{test_integration.id}/outbound",
    )
    assert response.status_code == 401


# =============================================================================
# Dynamic Integration Webhook Gateway Tests (INT-009)
# =============================================================================


@pytest.fixture
def test_integration_with_inbound_none_auth(db_session):
    """Create an integration with inbound config using no authentication."""
    integration = Integration(
        id="test-integration-inbound-none",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Webhook Integration (No Auth)",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-none-auth",
        integration_id=integration.id,
        webhook_path="webhook-test-none",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_inbound_api_key_auth(db_session):
    """Create an integration with inbound config using API key authentication."""
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    integration = Integration(
        id="test-integration-inbound-apikey",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Webhook Integration (API Key)",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add API key credential
    credential = IntegrationCredential(
        id="test-cred-apikey",
        integration_id=integration.id,
        credential_type=CredentialType.api_key,
        encrypted_value=encryption_service.encrypt("test-api-key-secret-123"),
    )
    db_session.add(credential)

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-apikey-auth",
        integration_id=integration.id,
        webhook_path="webhook-test-apikey",
        auth_method=InboundAuthMethod.api_key,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_inbound_signature_auth(db_session):
    """Create an integration with inbound config using HMAC signature authentication."""
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    integration = Integration(
        id="test-integration-inbound-sig",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Webhook Integration (Signature)",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-sig-auth",
        integration_id=integration.id,
        webhook_path="webhook-test-signature",
        auth_method=InboundAuthMethod.signature,
        signature_secret=encryption_service.encrypt("my-webhook-secret"),
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_inbound_bearer_auth(db_session):
    """Create an integration with inbound config using Bearer token authentication."""
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    integration = Integration(
        id="test-integration-inbound-bearer",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Webhook Integration (Bearer)",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add OAuth token credential
    credential = IntegrationCredential(
        id="test-cred-bearer",
        integration_id=integration.id,
        credential_type=CredentialType.oauth_token,
        encrypted_value=encryption_service.encrypt("bearer-token-secret-456"),
    )
    db_session.add(credential)

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-bearer-auth",
        integration_id=integration.id,
        webhook_path="webhook-test-bearer",
        auth_method=InboundAuthMethod.bearer,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_inactive(db_session):
    """Create an inactive integration with inbound config."""
    integration = Integration(
        id="test-integration-inactive",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Inactive Integration",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.paused,
    )
    db_session.add(integration)
    db_session.flush()

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-inactive",
        integration_id=integration.id,
        webhook_path="webhook-test-inactive",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_deleted(db_session):
    """Create a soft-deleted integration with inbound config."""
    integration = Integration(
        id="test-integration-soft-deleted",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Deleted Integration",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
        deleted_at=datetime.utcnow(),
    )
    db_session.add(integration)
    db_session.flush()

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-deleted",
        integration_id=integration.id,
        webhook_path="webhook-test-deleted",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_inbound_inactive(db_session):
    """Create an integration with inactive inbound config."""
    integration = Integration(
        id="test-integration-inbound-off",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Inbound Config Inactive",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-off",
        integration_id=integration.id,
        webhook_path="webhook-test-inbound-off",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        is_active=False,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


# =============================================================================
# Gateway Success Tests
# =============================================================================


@pytest.mark.unit
def test_gateway_webhook_no_auth_success(client, test_integration_with_inbound_none_auth):
    """Test successful webhook receipt with no authentication."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        json={"event": "test_event", "data": {"key": "value"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-test-none"
    assert data["integration_id"] == test_integration_with_inbound_none_auth.id
    assert data["provider"] == "custom_webhook"
    assert data["message"] == "Webhook received and routing triggered"


@pytest.mark.unit
def test_gateway_webhook_api_key_success(client, test_integration_with_inbound_api_key_auth):
    """Test successful webhook receipt with API key authentication."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-apikey",
        json={"event": "test_event"},
        headers={"X-API-Key": "test-api-key-secret-123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-test-apikey"


@pytest.mark.unit
def test_gateway_webhook_signature_success(client, test_integration_with_inbound_signature_auth):
    """Test successful webhook receipt with HMAC signature authentication."""
    import hashlib
    import hmac
    import json

    body = json.dumps({"event": "push", "repository": "test"}).encode("utf-8")
    secret = "my-webhook-secret"
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-signature",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-test-signature"


@pytest.mark.unit
def test_gateway_webhook_signature_github_format_success(
    client, test_integration_with_inbound_signature_auth
):
    """Test successful webhook receipt with GitHub-style sha256= prefix."""
    import hashlib
    import hmac
    import json

    body = json.dumps({"event": "push", "repository": "test"}).encode("utf-8")
    secret = "my-webhook-secret"
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-signature",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True


@pytest.mark.unit
def test_gateway_webhook_bearer_success(client, test_integration_with_inbound_bearer_auth):
    """Test successful webhook receipt with Bearer token authentication."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-bearer",
        json={"event": "test_event"},
        headers={"Authorization": "Bearer bearer-token-secret-456"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-test-bearer"


# =============================================================================
# Gateway 404 Tests
# =============================================================================


@pytest.mark.unit
def test_gateway_webhook_not_found(client):
    """Test 404 for non-existent webhook path."""
    response = client.post(
        "/api/v1/gateway/integrations/non-existent-webhook-path",
        json={"event": "test_event"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "NotFound"
    assert data["detail"]["message"] == "Webhook not found"


@pytest.mark.unit
def test_gateway_webhook_integration_inactive(client, test_integration_inactive):
    """Test 404 for paused/inactive integration."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-inactive",
        json={"event": "test_event"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "NotFound"


@pytest.mark.unit
def test_gateway_webhook_integration_deleted(client, test_integration_deleted):
    """Test 404 for soft-deleted integration."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-deleted",
        json={"event": "test_event"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "NotFound"


@pytest.mark.unit
def test_gateway_webhook_inbound_config_inactive(client, test_integration_inbound_inactive):
    """Test 404 for inactive inbound config."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-inbound-off",
        json={"event": "test_event"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "NotFound"


# =============================================================================
# Gateway 401 Tests
# =============================================================================


@pytest.mark.unit
def test_gateway_webhook_api_key_missing(client, test_integration_with_inbound_api_key_auth):
    """Test 401 when API key is missing."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-apikey",
        json={"event": "test_event"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_api_key_invalid(client, test_integration_with_inbound_api_key_auth):
    """Test 401 when API key is invalid."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-apikey",
        json={"event": "test_event"},
        headers={"X-API-Key": "wrong-api-key"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_signature_missing(client, test_integration_with_inbound_signature_auth):
    """Test 401 when signature header is missing."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-signature",
        json={"event": "test_event"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_signature_invalid(client, test_integration_with_inbound_signature_auth):
    """Test 401 when signature is invalid."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-signature",
        json={"event": "test_event"},
        headers={"X-Signature": "invalid-signature-that-doesnt-match"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_bearer_missing(client, test_integration_with_inbound_bearer_auth):
    """Test 401 when Bearer token is missing."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-bearer",
        json={"event": "test_event"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_bearer_invalid(client, test_integration_with_inbound_bearer_auth):
    """Test 401 when Bearer token is invalid."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-bearer",
        json={"event": "test_event"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


@pytest.mark.unit
def test_gateway_webhook_bearer_wrong_format(client, test_integration_with_inbound_bearer_auth):
    """Test 401 when Authorization header is not in Bearer format."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-bearer",
        json={"event": "test_event"},
        headers={"Authorization": "Basic some-token"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "AuthenticationFailed"


# =============================================================================
# Gateway Edge Cases
# =============================================================================


@pytest.mark.unit
def test_gateway_webhook_empty_body(client, test_integration_with_inbound_none_auth):
    """Test webhook receipt with empty body."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        content=b"",
        headers={"Content-Type": "application/json"},
    )

    # Should still succeed - the body might be empty for some webhooks
    assert response.status_code == 200


@pytest.mark.unit
def test_gateway_webhook_large_body(client, test_integration_with_inbound_none_auth):
    """Test webhook receipt with large body."""
    import json

    large_data = {"items": [{"id": i, "data": "x" * 100} for i in range(100)]}
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        json=large_data,
    )

    assert response.status_code == 200


@pytest.mark.unit
def test_gateway_webhook_non_json_body(client, test_integration_with_inbound_none_auth):
    """Test webhook receipt with non-JSON body (form data)."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        content=b"key=value&another=data",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200


# =============================================================================
# Payload Transformation Tests (INT-011)
# =============================================================================


@pytest.fixture
def test_integration_with_transform_template(db_session):
    """Create an integration with inbound config that has a transform template."""
    integration = Integration(
        id="test-integration-transform",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Integration with Transform",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Jinja2 template that transforms GitHub webhook payload
    transform_template = '''{
    "event_type": "{{ action }}",
    "data": {
        "repository": "{{ repository.full_name }}",
        "sender": "{{ sender.login }}",
        "action": "{{ action }}"
    }
}'''

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-transform",
        integration_id=integration.id,
        webhook_path="webhook-with-transform",
        auth_method=InboundAuthMethod.none,
        transform_template=transform_template,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_invalid_template(db_session):
    """Create an integration with an invalid Jinja2 template."""
    integration = Integration(
        id="test-integration-invalid-template",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Integration with Invalid Template",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Invalid Jinja2 template (unclosed braces)
    transform_template = '{"event_type": "{{ action }"}'

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-invalid-template",
        integration_id=integration.id,
        webhook_path="webhook-invalid-template",
        auth_method=InboundAuthMethod.none,
        transform_template=transform_template,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_undefined_var_template(db_session):
    """Create an integration with a template that references undefined variables."""
    integration = Integration(
        id="test-integration-undefined-var",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Integration with Undefined Var Template",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Template that references non-existent variable
    transform_template = '{"event_type": "{{ nonexistent_field.nested.value }}"}'

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-undefined-var",
        integration_id=integration.id,
        webhook_path="webhook-undefined-var",
        auth_method=InboundAuthMethod.none,
        transform_template=transform_template,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_non_json_output_template(db_session):
    """Create an integration with a template that outputs non-JSON."""
    integration = Integration(
        id="test-integration-non-json-output",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Integration with Non-JSON Output Template",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Template that outputs plain text, not JSON
    transform_template = "Event: {{ action }}"

    inbound_config = IntegrationInboundConfig(
        id="test-inbound-non-json-output",
        integration_id=integration.id,
        webhook_path="webhook-non-json-output",
        auth_method=InboundAuthMethod.none,
        transform_template=transform_template,
        destination_service=DestinationService.tentackl,
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.mark.unit
def test_gateway_webhook_no_template_returns_standard_format(client, test_integration_with_inbound_none_auth):
    """Test that webhooks without transform_template return standard format with raw data."""
    payload = {"event": "test_event", "data": {"key": "value"}}
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()

    # Standard fields
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-test-none"
    assert data["integration_id"] == test_integration_with_inbound_none_auth.id
    assert data["provider"] == "custom_webhook"

    # Transformed payload fields (INT-011)
    assert data["event_type"] == "webhook"  # Default when no template
    assert "timestamp" in data
    assert data["source"] == "webhook-test-none"
    assert data["data"] == payload  # Raw payload in data field


@pytest.mark.unit
def test_gateway_webhook_with_transform_template(client, test_integration_with_transform_template):
    """Test successful payload transformation with Jinja2 template."""
    # Simulate a GitHub webhook payload
    payload = {
        "action": "created",
        "repository": {
            "full_name": "octocat/Hello-World",
            "id": 12345
        },
        "sender": {
            "login": "octocat",
            "id": 1
        }
    }

    response = client.post(
        "/api/v1/gateway/integrations/webhook-with-transform",
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()

    # Standard response fields
    assert data["received"] is True
    assert data["webhook_path"] == "webhook-with-transform"
    assert data["provider"] == "github"

    # Transformed payload fields (INT-011)
    assert data["event_type"] == "created"  # Extracted from template
    assert "timestamp" in data
    assert data["source"] == "webhook-with-transform"
    assert data["data"]["repository"] == "octocat/Hello-World"
    assert data["data"]["sender"] == "octocat"
    assert data["data"]["action"] == "created"


@pytest.mark.unit
def test_gateway_webhook_transform_error_returns_raw_payload(client, test_integration_with_invalid_template):
    """Test that template syntax errors don't fail the request - returns raw payload."""
    payload = {"action": "test", "value": 123}

    response = client.post(
        "/api/v1/gateway/integrations/webhook-invalid-template",
        json=payload,
    )

    # Should succeed despite template error
    assert response.status_code == 200
    data = response.json()

    assert data["received"] is True
    assert data["event_type"] == "webhook"  # Default fallback
    assert data["data"] == payload  # Raw payload returned on error


@pytest.mark.unit
def test_gateway_webhook_undefined_var_returns_raw_payload(client, test_integration_with_undefined_var_template):
    """Test that undefined variable errors don't fail the request - returns raw payload."""
    payload = {"action": "test", "different_field": "value"}

    response = client.post(
        "/api/v1/gateway/integrations/webhook-undefined-var",
        json=payload,
    )

    # Should succeed despite undefined variable
    assert response.status_code == 200
    data = response.json()

    assert data["received"] is True
    assert data["event_type"] == "webhook"  # Default fallback
    assert data["data"] == payload  # Raw payload returned on error


@pytest.mark.unit
def test_gateway_webhook_non_json_output_returns_raw_payload(client, test_integration_with_non_json_output_template):
    """Test that templates outputting non-JSON don't fail - returns raw payload."""
    payload = {"action": "test"}

    response = client.post(
        "/api/v1/gateway/integrations/webhook-non-json-output",
        json=payload,
    )

    # Should succeed despite non-JSON output
    assert response.status_code == 200
    data = response.json()

    assert data["received"] is True
    assert data["event_type"] == "webhook"  # Default fallback
    assert data["data"] == payload  # Raw payload returned on error


@pytest.mark.unit
def test_gateway_webhook_empty_body_returns_empty_data(client, test_integration_with_inbound_none_auth):
    """Test webhook with empty body returns empty dict in data field."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        content=b"",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["received"] is True
    assert data["event_type"] == "webhook"
    assert data["data"] == {}  # Empty dict for empty body


@pytest.mark.unit
def test_gateway_webhook_timestamp_is_iso8601(client, test_integration_with_inbound_none_auth):
    """Test that timestamp in response is valid ISO8601 format."""
    from datetime import datetime

    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        json={"test": "data"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify timestamp is valid ISO8601
    timestamp = data["timestamp"]
    assert timestamp is not None
    # Should be parseable as ISO8601
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed is not None


@pytest.mark.unit
def test_gateway_webhook_source_matches_webhook_path(client, test_integration_with_inbound_none_auth):
    """Test that source field matches the webhook_path."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        json={"test": "data"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["source"] == "webhook-test-none"
    assert data["source"] == data["webhook_path"]


@pytest.mark.unit
def test_gateway_webhook_non_json_body_wrapped(client, test_integration_with_inbound_none_auth):
    """Test that non-JSON body is wrapped in a 'raw' field."""
    response = client.post(
        "/api/v1/gateway/integrations/webhook-test-none",
        content=b"plain text body",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["received"] is True
    assert data["event_type"] == "webhook"
    # Non-JSON body should be wrapped in 'raw' field
    assert data["data"]["raw"] == "plain text body"


# =============================================================================
# INT-012: Event Routing Tests
# =============================================================================


@pytest.fixture
def test_integration_with_tentackl_routing(db_session):
    """Create a test integration with Tentackl routing configured."""
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    integration = Integration(
        id="test-integration-tentackl",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Tentackl Routing",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()

    inbound_config = IntegrationInboundConfig(
        id="inbound-config-tentackl",
        integration_id=integration.id,
        webhook_path="webhook-tentackl-routing",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        destination_config={
            "task_template_id": "template-001",
            "agent_id": "agent-001",
        },
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_custom_routing(db_session):
    """Create a test integration with custom webhook routing configured."""
    integration = Integration(
        id="test-integration-custom",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Custom Routing",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()

    inbound_config = IntegrationInboundConfig(
        id="inbound-config-custom",
        integration_id=integration.id,
        webhook_path="webhook-custom-routing",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.custom,
        destination_config={
            "webhook_url": "https://example.com/webhook",
            "headers": {"X-Custom-Header": "test-value"},
        },
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.mark.unit
def test_gateway_webhook_creates_event_record(client, db_session, test_integration_with_tentackl_routing):
    """Test that receiving a webhook creates an IntegrationWebhookEvent record."""
    from src.database.models import IntegrationWebhookEvent
    from unittest.mock import MagicMock

    # Mock the Celery task to prevent actual async execution
    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-123")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"action": "test", "data": {"key": "value"}},
        )

    assert response.status_code == 200

    # Verify event was created
    event = db_session.query(IntegrationWebhookEvent).filter(
        IntegrationWebhookEvent.integration_id == "test-integration-tentackl"
    ).first()

    assert event is not None
    assert event.webhook_path == "webhook-tentackl-routing"
    assert event.provider == "custom_webhook"
    assert event.destination_service == "tentackl"
    assert event.raw_payload == {"action": "test", "data": {"key": "value"}}
    assert event.transformed_payload is not None


@pytest.mark.unit
def test_gateway_webhook_creates_delivery_record(client, db_session, test_integration_with_tentackl_routing):
    """Test that receiving a webhook creates an IntegrationWebhookDelivery record."""
    from src.database.models import IntegrationWebhookEvent, IntegrationWebhookDelivery
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-456")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"test": "data"},
        )

    assert response.status_code == 200

    # Verify delivery was created
    event = db_session.query(IntegrationWebhookEvent).filter(
        IntegrationWebhookEvent.integration_id == "test-integration-tentackl"
    ).first()

    delivery = db_session.query(IntegrationWebhookDelivery).filter(
        IntegrationWebhookDelivery.event_id == event.id
    ).first()

    assert delivery is not None
    assert delivery.destination_service == "tentackl"
    assert delivery.status == "pending"
    assert delivery.celery_task_id == "celery-task-456"


@pytest.mark.unit
def test_gateway_webhook_triggers_celery_task(client, test_integration_with_tentackl_routing):
    """Test that receiving a webhook triggers the Celery routing task."""
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-789")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"action": "trigger_test"},
        )

    assert response.status_code == 200

    # Verify Celery task was called
    mock_task.delay.assert_called_once()
    call_kwargs = mock_task.delay.call_args[1]

    assert call_kwargs["destination_service"] == "tentackl"
    assert call_kwargs["destination_config"] == {
        "task_template_id": "template-001",
        "agent_id": "agent-001",
    }
    assert call_kwargs["organization_id"] == "test-org-456"


@pytest.mark.unit
def test_gateway_webhook_custom_routing_destination(client, test_integration_with_custom_routing):
    """Test that webhook with custom destination triggers correct routing."""
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-custom")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-custom-routing",
            json={"event": "custom_test"},
        )

    assert response.status_code == 200

    mock_task.delay.assert_called_once()
    call_kwargs = mock_task.delay.call_args[1]

    assert call_kwargs["destination_service"] == "custom"
    assert call_kwargs["destination_config"]["webhook_url"] == "https://example.com/webhook"
    assert call_kwargs["destination_config"]["headers"] == {"X-Custom-Header": "test-value"}


@pytest.mark.unit
def test_gateway_webhook_event_status_is_received(client, db_session, test_integration_with_tentackl_routing):
    """Test that new webhook events have 'received' status."""
    from src.database.models import IntegrationWebhookEvent, IntegrationWebhookEventStatus
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-status")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"test": "status"},
        )

    assert response.status_code == 200

    event = db_session.query(IntegrationWebhookEvent).filter(
        IntegrationWebhookEvent.integration_id == "test-integration-tentackl"
    ).first()

    assert event.status == IntegrationWebhookEventStatus.received


@pytest.mark.unit
def test_gateway_webhook_transformed_payload_stored(client, db_session, test_integration_with_tentackl_routing):
    """Test that transformed payload is stored in the event record."""
    from src.database.models import IntegrationWebhookEvent
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-transformed")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"action": "transform_test", "value": 123},
        )

    assert response.status_code == 200

    event = db_session.query(IntegrationWebhookEvent).filter(
        IntegrationWebhookEvent.integration_id == "test-integration-tentackl"
    ).first()

    # Transformed payload should have standard format
    assert event.transformed_payload is not None
    assert "event_type" in event.transformed_payload
    assert "timestamp" in event.transformed_payload
    assert "source" in event.transformed_payload
    assert "provider" in event.transformed_payload
    assert "data" in event.transformed_payload
    assert event.transformed_payload["data"]["action"] == "transform_test"


@pytest.mark.unit
def test_gateway_webhook_response_message_indicates_routing(client, test_integration_with_tentackl_routing):
    """Test that response message indicates routing was triggered."""
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-msg")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"test": "message"},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "Webhook received and routing triggered"


@pytest.mark.unit
def test_gateway_webhook_organization_id_stored_in_event(client, db_session, test_integration_with_tentackl_routing):
    """Test that organization_id is stored in the event for querying."""
    from src.database.models import IntegrationWebhookEvent
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-org")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-tentackl-routing",
            json={"test": "org"},
        )

    assert response.status_code == 200

    event = db_session.query(IntegrationWebhookEvent).filter(
        IntegrationWebhookEvent.organization_id == "test-org-456"
    ).first()

    assert event is not None
    assert event.organization_id == "test-org-456"


@pytest.mark.unit
def test_gateway_webhook_null_destination_config_handled(client, db_session):
    """Test that null destination_config is handled gracefully."""
    from src.database.models import IntegrationWebhookEvent
    from unittest.mock import MagicMock

    # Create integration with null destination_config
    integration = Integration(
        id="test-integration-null-config",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Test Null Config",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()

    inbound_config = IntegrationInboundConfig(
        id="inbound-config-null",
        integration_id=integration.id,
        webhook_path="webhook-null-config",
        auth_method=InboundAuthMethod.none,
        destination_service=DestinationService.tentackl,
        destination_config=None,  # Null config
        is_active=True,
    )
    db_session.add(inbound_config)
    db_session.commit()

    with patch("src.api.routes.integrations.get_route_integration_event_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-task-null")

        response = client.post(
            "/api/v1/gateway/integrations/webhook-null-config",
            json={"test": "null_config"},
        )

    assert response.status_code == 200

    # Celery should be called with empty dict for destination_config
    call_kwargs = mock_task.delay.call_args[1]
    assert call_kwargs["destination_config"] == {}


# =============================================================================
# INT-013: Action Execution Endpoint Tests
# =============================================================================


@pytest.fixture
def test_integration_with_discord_outbound(db_session):
    """Create a test integration with Discord outbound config and webhook credential."""
    integration = Integration(
        id="test-integration-discord-outbound",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Discord Outbound Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add webhook_url credential
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-discord-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://discord.com/api/webhooks/test"),
        credential_metadata={"channel": "#test"},
    )
    db_session.add(credential)

    # Add outbound config for send_message
    outbound_config = IntegrationOutboundConfig(
        id="outbound-discord-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        default_template={"content": "Default message from template"},
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_github_outbound(db_session):
    """Create a test integration with GitHub outbound config and api_key credential."""
    integration = Integration(
        id="test-integration-github-outbound",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="GitHub Outbound Integration",
        provider=IntegrationProvider.github,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add api_key credential
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-github-api-key",
        integration_id=integration.id,
        credential_type=CredentialType.api_key,
        encrypted_value=encryption_service.encrypt("ghp_test_token_12345"),
    )
    db_session.add(credential)

    # Add outbound config for create_issue
    outbound_config = IntegrationOutboundConfig(
        id="outbound-github-001",
        integration_id=integration.id,
        action_type=OutboundActionType.create_issue,
        default_template={"repo": "owner/default-repo", "labels": ["automated"]},
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_with_inactive_outbound(db_session):
    """Create a test integration with inactive outbound config."""
    integration = Integration(
        id="test-integration-inactive-outbound",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Inactive Outbound Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    outbound_config = IntegrationOutboundConfig(
        id="outbound-inactive-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=False,  # Inactive!
    )
    db_session.add(outbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_no_outbound(db_session):
    """Create a test integration without outbound config."""
    integration = Integration(
        id="test-integration-no-outbound",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="No Outbound Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.inbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.mark.unit
def test_execute_action_success_sync(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test successful synchronous action execution."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock

    # Mock httpx.AsyncClient.post
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-outbound/actions/send_message",
            json={"content": "Hello from test!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["integration_id"] == "test-integration-discord-outbound"
    assert data["action_type"] == "send_message"
    assert data["message"] == "Action executed successfully"
    assert data["result"] is not None


@pytest.mark.unit
def test_execute_action_success_async(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test successful asynchronous action execution returns job_id."""
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_execute_integration_action_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-job-12345")

        response = client.post(
            "/api/v1/integrations/test-integration-discord-outbound/actions/send_message",
            json={"content": "Async message", "async_execution": True},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["job_id"] == "celery-job-12345"
    assert data["message"] == "Action queued for async execution"


@pytest.mark.unit
def test_execute_action_no_outbound_config_404(client, mock_inkpass_permission_check, test_integration_no_outbound):
    """Test action execution without outbound config returns 404."""
    response = client.post(
        "/api/v1/integrations/test-integration-no-outbound/actions/send_message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404
    data = response.json()
    assert "Outbound config not found" in data["detail"]


@pytest.mark.unit
def test_execute_action_inactive_outbound_400(client, mock_inkpass_permission_check, test_integration_with_inactive_outbound):
    """Test action execution with inactive outbound config returns 400."""
    response = client.post(
        "/api/v1/integrations/test-integration-inactive-outbound/actions/send_message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    data = response.json()
    assert "not active" in data["detail"]


@pytest.mark.unit
def test_execute_action_wrong_action_type_400(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test action execution with mismatched action type returns 400."""
    # Integration is configured for send_message, but we try send_embed
    response = client.post(
        "/api/v1/integrations/test-integration-discord-outbound/actions/send_embed",
        json={"title": "Test Embed"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    data = response.json()
    assert "does not match configured action type" in data["detail"]


@pytest.mark.unit
def test_execute_action_invalid_action_type_400(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test action execution with invalid action type returns 400."""
    response = client.post(
        "/api/v1/integrations/test-integration-discord-outbound/actions/invalid_action",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Invalid action_type" in data["detail"]


@pytest.mark.unit
def test_execute_action_integration_not_found_404(client, mock_inkpass_permission_check):
    """Test action execution with non-existent integration returns 404."""
    response = client.post(
        "/api/v1/integrations/nonexistent-integration/actions/send_message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_execute_action_merges_with_default_template(client, mock_inkpass_permission_check, test_integration_with_github_outbound):
    """Test that request params are merged with default_template."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": 123, "number": 45})

    captured_payload = None

    async def capture_post(*args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-github-outbound/actions/create_issue",
            json={
                "title": "Bug Report",  # Required, not in default template
                "body": "This is a bug",  # Override or add
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200

    # Verify merged payload contains default repo and labels from template
    # plus title and body from request
    assert captured_payload is not None
    assert captured_payload["title"] == "Bug Report"
    # labels from default_template should be present
    assert captured_payload.get("labels") == ["automated"]


@pytest.mark.unit
def test_execute_action_rate_limit_exceeded_429(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test that rate limiting returns 429 when exceeded."""
    with patch("src.api.routes.integrations._check_rate_limit") as mock_rate_limit:
        # Simulate rate limit exceeded
        mock_rate_limit.return_value = (False, 30)  # Not allowed, 30 seconds retry

        response = client.post(
            "/api/v1/integrations/test-integration-discord-outbound/actions/send_message",
            json={"content": "Hello"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 429
    data = response.json()
    assert data["detail"]["error"] == "RateLimitExceeded"
    assert data["detail"]["retry_after_seconds"] == 30


@pytest.mark.unit
def test_execute_action_rate_limit_not_configured_passes(client, mock_inkpass_permission_check, db_session):
    """Test that actions without rate limit configured always pass."""
    # Create integration without rate limiting
    integration = Integration(
        id="test-integration-no-rate-limit",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="No Rate Limit Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-no-rate",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://discord.com/api/webhooks/no-rate"),
    )
    db_session.add(credential)

    # Outbound config without rate limiting
    outbound_config = IntegrationOutboundConfig(
        id="outbound-no-rate-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        rate_limit_requests=None,  # No rate limit
        rate_limit_window_seconds=None,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    import httpx
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-no-rate-limit/actions/send_message",
            json={"content": "Hello without rate limit"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200


@pytest.mark.unit
def test_execute_action_custom_webhook_post(client, mock_inkpass_permission_check, db_session):
    """Test custom webhook POST action execution."""
    # Create custom webhook integration
    integration = Integration(
        id="test-integration-custom-post",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Custom Webhook POST",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-custom-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://example.com/webhook"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-custom-post-001",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    import httpx
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"success": True})

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-custom-post/actions/post",
            json={"payload": {"key": "value"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status_code"] == 200


@pytest.mark.unit
def test_execute_action_requires_authentication(client, db_session):
    """Test that action execution requires authentication."""
    # Don't use mock_inkpass_permission_check fixture
    response = client.post(
        "/api/v1/integrations/test-integration-discord-outbound/actions/send_message",
        json={"content": "Hello"},
    )

    # Should fail with 401/403 without auth
    assert response.status_code in [401, 403]


@pytest.mark.unit
def test_execute_action_other_org_integration_404(client, mock_inkpass_permission_check, other_org_integration):
    """Test that user cannot execute actions on other org's integration."""
    response = client.post(
        f"/api/v1/integrations/{other_org_integration.id}/actions/send_message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    # Should return 404 (scoped to user's org)
    assert response.status_code == 404


@pytest.mark.unit
def test_execute_action_deleted_integration_404(client, mock_inkpass_permission_check, deleted_integration):
    """Test that action execution on deleted integration returns 404."""
    response = client.post(
        f"/api/v1/integrations/{deleted_integration.id}/actions/send_message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_execute_action_celery_task_receives_correct_params(client, mock_inkpass_permission_check, test_integration_with_discord_outbound):
    """Test that async execution passes correct params to Celery task."""
    from unittest.mock import MagicMock

    with patch("src.api.routes.integrations.get_execute_integration_action_task") as mock_get_task:
        mock_task = MagicMock()
        mock_get_task.return_value = mock_task
        mock_task.delay.return_value = MagicMock(id="celery-job-params")

        response = client.post(
            "/api/v1/integrations/test-integration-discord-outbound/actions/send_message",
            json={"content": "Test message for Celery", "async_execution": True},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200

    mock_task.delay.assert_called_once()
    call_kwargs = mock_task.delay.call_args[1]

    assert call_kwargs["integration_id"] == "test-integration-discord-outbound"
    assert call_kwargs["organization_id"] == "test-org-456"
    assert call_kwargs["action_type"] == "send_message"
    assert call_kwargs["provider"] == "discord"
    assert "content" in call_kwargs["merged_params"]
    assert call_kwargs["merged_params"]["content"] == "Test message for Celery"
    assert call_kwargs["webhook_url"] is not None


@pytest.mark.unit
def test_execute_action_slack_send_message(client, mock_inkpass_permission_check, db_session):
    """Test Slack send_message action execution."""
    integration = Integration(
        id="test-integration-slack-msg",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Slack Message Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-slack-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://hooks.slack.com/services/test"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-slack-msg-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    import httpx
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
            json={"content": "Hello Slack!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status"] == "sent"


# =============================================================================
# INT-014: Discord Actions Tests
# =============================================================================


@pytest.fixture
def test_integration_discord_send_message(db_session):
    """Create a test Discord integration configured for send_message."""
    integration = Integration(
        id="test-integration-discord-msg",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Discord Message Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-discord-msg-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://discord.com/api/webhooks/123/abc"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-discord-msg-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.fixture
def test_integration_discord_send_embed(db_session):
    """Create a test Discord integration configured for send_embed."""
    integration = Integration(
        id="test-integration-discord-embed",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Discord Embed Integration",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-discord-embed-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://discord.com/api/webhooks/456/def"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-discord-embed-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_embed,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()
    db_session.refresh(integration)
    return integration


@pytest.mark.unit
def test_discord_send_message_success_with_message_id(client, mock_inkpass_permission_check, test_integration_discord_send_message):
    """Test Discord send_message returns message_id when using ?wait=true."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "id": "1234567890123456789",
        "channel_id": "9876543210987654321",
        "content": "Test message",
        "type": 0,
    })

    captured_url = None

    async def capture_post(url, **kwargs):
        nonlocal captured_url
        captured_url = url
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-msg/actions/send_message",
            json={"content": "Hello Discord!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status"] == "sent"
    assert data["result"]["message_id"] == "1234567890123456789"
    assert data["result"]["channel_id"] == "9876543210987654321"
    # Verify ?wait=true was added to URL
    assert "wait=true" in captured_url


@pytest.mark.unit
def test_discord_send_message_content_validation_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_message):
    """Test Discord send_message rejects content exceeding 2000 characters."""
    # Create content that exceeds 2000 character limit
    long_content = "x" * 2001

    response = client.post(
        "/api/v1/integrations/test-integration-discord-msg/actions/send_message",
        json={"content": long_content},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Discord limit of 2000 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_message_requires_content(client, mock_inkpass_permission_check, test_integration_discord_send_message):
    """Test Discord send_message requires content parameter."""
    response = client.post(
        "/api/v1/integrations/test-integration-discord-msg/actions/send_message",
        json={},  # No content
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "send_message requires 'content' parameter" in data["detail"]


@pytest.mark.unit
def test_discord_send_message_with_username_override(client, mock_inkpass_permission_check, test_integration_discord_send_message):
    """Test Discord send_message supports username override."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": "123", "channel_id": "456"})

    captured_payload = None

    async def capture_post(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-msg/actions/send_message",
            json={
                "content": "Hello!",
                "username": "Bot Override",
                "avatar_url": "https://example.com/avatar.png",
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    assert captured_payload["content"] == "Hello!"
    assert captured_payload["username"] == "Bot Override"
    assert captured_payload["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.unit
def test_discord_send_embed_success_with_message_id(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed returns message_id when successful."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "id": "9876543210987654321",
        "channel_id": "1234567890123456789",
    })

    captured_payload = None

    async def capture_post(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={
                "title": "Test Embed",
                "description": "This is a test embed",
                "color": "#FF5733",
                "fields": [
                    {"name": "Field 1", "value": "Value 1", "inline": True},
                    {"name": "Field 2", "value": "Value 2"},
                ],
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["message_id"] == "9876543210987654321"
    # Verify embed structure in payload
    assert "embeds" in captured_payload
    assert len(captured_payload["embeds"]) == 1
    embed = captured_payload["embeds"][0]
    assert embed["title"] == "Test Embed"
    assert embed["description"] == "This is a test embed"
    # Hex color should be converted to int
    assert embed["color"] == 0xFF5733


@pytest.mark.unit
def test_discord_send_embed_requires_title_or_description(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed requires at least title or description."""
    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "color": "#FF5733",  # Only color, no title or description
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "requires at least 'title' or 'description'" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_title_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects title exceeding 256 characters."""
    long_title = "x" * 257

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={"title": long_title},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Embed title exceeds Discord limit of 256 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_description_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects description exceeding 4096 characters."""
    long_description = "x" * 4097

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={"description": long_description},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Embed description exceeds Discord limit of 4096 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_field_name_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects field name exceeding 256 characters."""
    long_field_name = "x" * 257

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "title": "Test",
            "fields": [{"name": long_field_name, "value": "Test value"}],
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "field 0 name exceeds Discord limit of 256 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_field_value_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects field value exceeding 1024 characters."""
    long_field_value = "x" * 1025

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "title": "Test",
            "fields": [{"name": "Field Name", "value": long_field_value}],
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "field 0 value exceeds Discord limit of 1024 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_too_many_fields(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects more than 25 fields."""
    fields = [{"name": f"Field {i}", "value": f"Value {i}"} for i in range(26)]

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={"title": "Test", "fields": fields},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Discord limit of 25 fields" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_total_chars_exceeds_limit(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed rejects embed exceeding 6000 total characters."""
    # Create embed that's just over 6000 chars total
    # title (256) + description (4096) + 2 fields (256 + 1024 each) = 6656
    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "title": "x" * 256,
            "description": "y" * 4096,
            "fields": [
                {"name": "a" * 256, "value": "b" * 1024},
                {"name": "c" * 256, "value": "d" * 1024},
            ],
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Total embed content exceeds Discord limit of 6000 characters" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_field_requires_name_and_value(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed requires name and value for each field."""
    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "title": "Test",
            "fields": [{"name": "Only name"}],  # Missing value
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "field 0 requires a 'value'" in data["detail"]


@pytest.mark.unit
def test_discord_send_embed_with_all_optional_fields(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed with all optional fields (footer, author, thumbnail, image, timestamp)."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": "123", "channel_id": "456"})

    captured_payload = None

    async def capture_post(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={
                "title": "Full Embed Test",
                "description": "Testing all fields",
                "url": "https://example.com",
                "color": 0x00FF00,  # Decimal format
                "timestamp": "2026-01-25T12:00:00Z",
                "footer_text": "Footer text",
                "footer_icon_url": "https://example.com/footer.png",
                "author_name": "Author Name",
                "author_url": "https://example.com/author",
                "author_icon_url": "https://example.com/author.png",
                "thumbnail_url": "https://example.com/thumb.png",
                "image_url": "https://example.com/image.png",
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    embed = captured_payload["embeds"][0]
    assert embed["title"] == "Full Embed Test"
    assert embed["url"] == "https://example.com"
    assert embed["color"] == 0x00FF00
    assert embed["timestamp"] == "2026-01-25T12:00:00Z"
    assert embed["footer"]["text"] == "Footer text"
    assert embed["footer"]["icon_url"] == "https://example.com/footer.png"
    assert embed["author"]["name"] == "Author Name"
    assert embed["author"]["url"] == "https://example.com/author"
    assert embed["thumbnail"]["url"] == "https://example.com/thumb.png"
    assert embed["image"]["url"] == "https://example.com/image.png"


@pytest.mark.unit
def test_discord_send_embed_color_formats(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed accepts various color formats (#hex, 0x, decimal, string)."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": "123", "channel_id": "456"})

    captured_colors = []

    async def capture_post(url, **kwargs):
        captured_colors.append(kwargs.get("json")["embeds"][0].get("color"))
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        # Test #hex format
        client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={"title": "Test", "color": "#FF0000"},
            headers={"Authorization": "Bearer mock-token"},
        )

        # Test 0x format
        client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={"title": "Test", "color": "0x00FF00"},
            headers={"Authorization": "Bearer mock-token"},
        )

        # Test decimal integer
        client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={"title": "Test", "color": 255},  # 0x0000FF
            headers={"Authorization": "Bearer mock-token"},
        )

    assert captured_colors[0] == 0xFF0000  # #FF0000
    assert captured_colors[1] == 0x00FF00  # 0x00FF00
    assert captured_colors[2] == 255  # decimal


@pytest.mark.unit
def test_discord_send_embed_with_content(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed can include content alongside embed."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"id": "123", "channel_id": "456"})

    captured_payload = None

    async def capture_post(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json")
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=capture_post)
        mock_client_class.return_value = mock_client

        response = client.post(
            "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
            json={
                "title": "Embed Title",
                "description": "Embed description",
                "content": "Message text above the embed",
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    assert captured_payload["content"] == "Message text above the embed"
    assert captured_payload["embeds"][0]["title"] == "Embed Title"


@pytest.mark.unit
def test_discord_send_embed_content_also_validated(client, mock_inkpass_permission_check, test_integration_discord_send_embed):
    """Test Discord send_embed validates content length when included."""
    long_content = "x" * 2001

    response = client.post(
        "/api/v1/integrations/test-integration-discord-embed/actions/send_embed",
        json={
            "title": "Test",
            "content": long_content,  # Exceeds 2000 char limit
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Discord limit of 2000 characters" in data["detail"]


@pytest.mark.unit
def test_discord_action_no_webhook_url_credential(client, mock_inkpass_permission_check, db_session):
    """Test Discord action fails gracefully when no webhook_url credential exists."""
    integration = Integration(
        id="test-discord-no-webhook",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Discord No Webhook",
        provider=IntegrationProvider.discord,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # Add API key credential instead of webhook_url
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-discord-apikey",
        integration_id=integration.id,
        credential_type=CredentialType.api_key,  # Wrong type for Discord webhooks
        encrypted_value=encryption_service.encrypt("some-api-key"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-discord-no-webhook",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    response = client.post(
        "/api/v1/integrations/test-discord-no-webhook/actions/send_message",
        json={"content": "Test"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "require a webhook_url credential" in data["detail"]


# =============================================================================
# INT-015: Slack Actions Tests
# =============================================================================


@pytest.fixture
def test_integration_slack_send_message(db_session):
    """Create a test Slack integration configured for send_message."""
    integration = Integration(
        id="test-integration-slack-msg",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Slack Message Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-slack-msg-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXX"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-slack-msg-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    return integration


@pytest.fixture
def test_integration_slack_send_blocks(db_session):
    """Create a test Slack integration configured for send_blocks."""
    integration = Integration(
        id="test-integration-slack-blocks",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Slack Blocks Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-slack-blocks-webhook",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://hooks.slack.com/services/T11111111/B11111111/YYYYYYYY"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-slack-blocks-001",
        integration_id=integration.id,
        action_type=OutboundActionType.send_blocks,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    return integration


@pytest.mark.unit
def test_slack_send_message_success(client, mock_inkpass_permission_check, test_integration_slack_send_message):
    """Test Slack send_message returns success on 'ok' response."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "ok"

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
            json={"content": "Hello Slack!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status"] == "sent"
    assert data["result"]["message"] == "ok"


@pytest.mark.unit
def test_slack_send_message_with_timestamp(client, mock_inkpass_permission_check, test_integration_slack_send_message):
    """Test Slack send_message returns timestamp from API response."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = '{"ok": true, "ts": "1234567890.123456", "channel": "C12345678"}'
    mock_response.json = MagicMock(return_value={
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C12345678",
    })

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
            json={"content": "Hello with timestamp!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status"] == "sent"
    assert data["result"]["ts"] == "1234567890.123456"
    assert data["result"]["channel"] == "C12345678"


@pytest.mark.unit
def test_slack_send_message_requires_content(client, mock_inkpass_permission_check, test_integration_slack_send_message):
    """Test Slack send_message requires content parameter."""
    response = client.post(
        "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
        json={},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "requires 'content' parameter" in data["detail"]


@pytest.mark.unit
def test_slack_send_message_content_validation_exceeds_limit(client, mock_inkpass_permission_check, test_integration_slack_send_message):
    """Test Slack send_message validates content length."""
    # Slack limit is 40000 characters
    long_content = "a" * 40001

    response = client.post(
        "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
        json={"content": long_content},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 40000 characters" in data["detail"]


@pytest.mark.unit
def test_slack_send_message_with_optional_fields(client, mock_inkpass_permission_check, test_integration_slack_send_message):
    """Test Slack send_message with optional fields (username, icon_emoji, thread_ts)."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "ok"

    captured_payload = {}

    async def capture_post(url, json=None, **kwargs):
        captured_payload.update(json)
        return mock_response

    async_context_manager = AsyncMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=capture_post)
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-msg/actions/send_message",
            json={
                "content": "Hello thread!",
                "username": "CustomBot",
                "icon_emoji": ":robot_face:",
                "thread_ts": "1234567890.123456",
                "unfurl_links": False,
                "mrkdwn": True,
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    assert captured_payload["text"] == "Hello thread!"
    assert captured_payload["username"] == "CustomBot"
    assert captured_payload["icon_emoji"] == ":robot_face:"
    assert captured_payload["thread_ts"] == "1234567890.123456"
    assert captured_payload["unfurl_links"] is False
    assert captured_payload["mrkdwn"] is True


@pytest.mark.unit
def test_slack_send_blocks_success(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks returns success."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "ok"

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
            json={
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Hello *world*!"}
                    }
                ]
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status"] == "sent"


@pytest.mark.unit
def test_slack_send_blocks_with_timestamp(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks returns timestamp from API response."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = '{"ok": true, "ts": "1234567890.123456", "channel": "C12345678"}'
    mock_response.json = MagicMock(return_value={
        "ok": True,
        "ts": "1234567890.123456",
        "channel": "C12345678",
    })

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
            json={
                "blocks": [
                    {"type": "divider"}
                ]
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["ts"] == "1234567890.123456"
    assert data["result"]["channel"] == "C12345678"


@pytest.mark.unit
def test_slack_send_blocks_requires_blocks(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks requires blocks parameter."""
    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "requires 'blocks' parameter" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_too_many_blocks(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates max 50 blocks."""
    blocks = [{"type": "divider"} for _ in range(51)]

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={"blocks": blocks},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 50 blocks" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_section_text_exceeds_limit(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates section text length."""
    long_text = "a" * 3001

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": long_text}
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 3000 characters" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_header_text_exceeds_limit(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates header text length."""
    long_header = "a" * 151

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": long_header}
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 150 characters" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_section_too_many_fields(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates max 10 fields per section."""
    fields = [{"type": "mrkdwn", "text": f"Field {i}"} for i in range(11)]

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Main text"},
                    "fields": fields,
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 10 fields" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_context_too_many_elements(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates max 10 elements in context block."""
    elements = [{"type": "mrkdwn", "text": f"Element {i}"} for i in range(11)]

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "context",
                    "elements": elements,
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 10 elements" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_actions_too_many_elements(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates max 25 elements in actions block."""
    elements = [{"type": "button", "text": {"type": "plain_text", "text": f"B{i}"}, "action_id": f"action_{i}"} for i in range(26)]

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "actions",
                    "elements": elements,
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 25 elements" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_button_text_exceeds_limit(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates button text length."""
    long_button_text = "a" * 76

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": long_button_text},
                            "action_id": "button_action",
                        }
                    ],
                }
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 75 characters" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_with_fallback_text(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks includes fallback text when provided."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "ok"

    captured_payload = {}

    async def capture_post(url, json=None, **kwargs):
        captured_payload.update(json)
        return mock_response

    async_context_manager = AsyncMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=capture_post)
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
            json={
                "blocks": [{"type": "divider"}],
                "content": "Fallback text for notifications",
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    assert captured_payload["text"] == "Fallback text for notifications"
    assert captured_payload["blocks"] == [{"type": "divider"}]


@pytest.mark.unit
def test_slack_send_blocks_fallback_text_validated(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates fallback text length."""
    long_content = "a" * 40001

    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [{"type": "divider"}],
            "content": long_content,
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "exceeds Slack limit of 40000 characters" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_block_requires_type(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates that blocks have type field."""
    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": [
                {"text": "No type field"}
            ]
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "requires a 'type' field" in data["detail"]


@pytest.mark.unit
def test_slack_send_blocks_blocks_must_be_list(client, mock_inkpass_permission_check, test_integration_slack_send_blocks):
    """Test Slack send_blocks validates that blocks is a list."""
    response = client.post(
        "/api/v1/integrations/test-integration-slack-blocks/actions/send_blocks",
        json={
            "blocks": {"type": "divider"}  # Object instead of list - Pydantic validates this
        },
        headers={"Authorization": "Bearer mock-token"},
    )

    # Pydantic schema validation catches this before our code runs
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data  # Pydantic validation error


@pytest.mark.unit
def test_slack_action_no_webhook_url_credential(client, mock_inkpass_permission_check, db_session):
    """Test Slack action fails when integration has no webhook_url credential."""
    integration = Integration(
        id="test-slack-no-webhook",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Slack No Webhook Integration",
        provider=IntegrationProvider.slack,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-slack-apikey",
        integration_id=integration.id,
        credential_type=CredentialType.api_key,  # Wrong type for Slack webhooks
        encrypted_value=encryption_service.encrypt("some-api-key"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-slack-no-webhook",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    response = client.post(
        "/api/v1/integrations/test-slack-no-webhook/actions/send_message",
        json={"content": "Test"},
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "require a webhook_url credential" in data["detail"]


# =============================================================================
# INT-016: Generic Webhook Actions Tests
# =============================================================================


@pytest.fixture
def test_integration_custom_webhook_post(db_session):
    """Create a test custom_webhook integration configured for POST action."""
    integration = Integration(
        id="test-integration-webhook-post",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Custom Webhook POST Integration",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-post-001",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://httpbin.org/post"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-post-001",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    return integration


@pytest.fixture
def test_integration_custom_webhook_put(db_session):
    """Create a test custom_webhook integration configured for PUT action."""
    integration = Integration(
        id="test-integration-webhook-put",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Custom Webhook PUT Integration",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-put-001",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://httpbin.org/put"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-put-001",
        integration_id=integration.id,
        action_type=OutboundActionType.put,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    return integration


@pytest.fixture
def test_integration_custom_webhook_with_metadata_headers(db_session):
    """Create a test custom_webhook integration with headers in credential_metadata."""
    integration = Integration(
        id="test-integration-webhook-metadata",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Custom Webhook with Metadata Headers",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    # Credential with custom headers in metadata
    credential = IntegrationCredential(
        id="cred-webhook-metadata-001",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://httpbin.org/post"),
        credential_metadata={
            "headers": {
                "X-API-Key": "metadata-api-key-123",
                "X-Custom-Header": "metadata-value",
                "Content-Type": "application/json",
            }
        },
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-metadata-001",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    return integration


@pytest.mark.unit
def test_custom_webhook_post_success(client, mock_inkpass_permission_check, test_integration_custom_webhook_post):
    """Test custom_webhook POST action returns success with status and response body."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"status": "received", "id": "12345"})
    mock_response.text = '{"status": "received", "id": "12345"}'

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-post/actions/post",
            json={"payload": {"key": "value", "message": "Hello"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "post"
    assert data["result"]["status_code"] == 200
    assert data["result"]["response"]["status"] == "received"
    assert data["result"]["response"]["id"] == "12345"


@pytest.mark.unit
def test_custom_webhook_put_success(client, mock_inkpass_permission_check, test_integration_custom_webhook_put):
    """Test custom_webhook PUT action returns success with status and response body."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"updated": True, "record_id": "abc123"})
    mock_response.text = '{"updated": true, "record_id": "abc123"}'

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        put=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-put/actions/put",
            json={"payload": {"field": "updated_value"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "put"
    assert data["result"]["status_code"] == 200
    assert data["result"]["response"]["updated"] is True
    assert data["result"]["response"]["record_id"] == "abc123"


@pytest.mark.unit
def test_custom_webhook_post_with_custom_url(client, mock_inkpass_permission_check, test_integration_custom_webhook_post):
    """Test custom_webhook POST can use custom URL from params instead of credential."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"created": True})
    mock_response.text = '{"created": true}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-post/actions/post",
            json={
                "url": "https://custom-api.example.com/webhook",
                "payload": {"data": "test"}
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    # Verify the custom URL was used
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://custom-api.example.com/webhook"


@pytest.mark.unit
def test_custom_webhook_post_with_custom_headers_from_params(client, mock_inkpass_permission_check, test_integration_custom_webhook_post):
    """Test custom_webhook POST with custom headers from request params."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    custom_headers = {
        "X-Custom-Auth": "secret-token-123",
        "X-Request-ID": "req-456",
    }

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-post/actions/post",
            json={
                "payload": {"test": "data"},
                "headers": custom_headers
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    # Verify the custom headers were used
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[1]["headers"]["X-Custom-Auth"] == "secret-token-123"
    assert call_args[1]["headers"]["X-Request-ID"] == "req-456"


@pytest.mark.unit
def test_custom_webhook_post_with_headers_from_credential_metadata(
    client, mock_inkpass_permission_check, test_integration_custom_webhook_with_metadata_headers
):
    """Test custom_webhook POST uses headers from credential_metadata."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-metadata/actions/post",
            json={"payload": {"test": "data"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    # Verify the credential metadata headers were used
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[1]["headers"]["X-API-Key"] == "metadata-api-key-123"
    assert call_args[1]["headers"]["X-Custom-Header"] == "metadata-value"


@pytest.mark.unit
def test_custom_webhook_post_params_headers_override_metadata_headers(
    client, mock_inkpass_permission_check, test_integration_custom_webhook_with_metadata_headers
):
    """Test that request params headers take precedence over credential_metadata headers."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    # Params headers that override metadata headers
    override_headers = {
        "X-API-Key": "override-api-key-999",  # This should override the metadata value
        "X-New-Header": "new-value",
    }

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-metadata/actions/post",
            json={
                "payload": {"test": "data"},
                "headers": override_headers
            },
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    # Verify headers merging - params override metadata
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    # Override header should be from params
    assert call_args[1]["headers"]["X-API-Key"] == "override-api-key-999"
    # Metadata header not overridden should be preserved
    assert call_args[1]["headers"]["X-Custom-Header"] == "metadata-value"
    # New header from params should be present
    assert call_args[1]["headers"]["X-New-Header"] == "new-value"


@pytest.mark.unit
def test_custom_webhook_post_non_json_response(client, mock_inkpass_permission_check, test_integration_custom_webhook_post):
    """Test custom_webhook POST handles non-JSON response gracefully."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(side_effect=ValueError("Invalid JSON"))
    mock_response.text = "Plain text response from server"

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-post/actions/post",
            json={"payload": {"test": "data"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["status_code"] == 200
    # Non-JSON response should be wrapped in raw_response
    assert data["result"]["response"]["raw_response"] == "Plain text response from server"


@pytest.mark.unit
def test_custom_webhook_post_returns_status_code(client, mock_inkpass_permission_check, test_integration_custom_webhook_post):
    """Test custom_webhook POST returns the actual HTTP status code."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 202  # Accepted
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"queued": True})
    mock_response.text = '{"queued": true}'

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-post/actions/post",
            json={"payload": {"task": "async-job"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status_code"] == 202  # Actual response status code


@pytest.mark.unit
def test_custom_webhook_put_returns_status_code(client, mock_inkpass_permission_check, test_integration_custom_webhook_put):
    """Test custom_webhook PUT returns the actual HTTP status code."""
    from unittest.mock import AsyncMock, MagicMock

    mock_response = MagicMock()
    mock_response.status_code = 204  # No Content
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(side_effect=ValueError("No content"))
    mock_response.text = ""

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        put=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-integration-webhook-put/actions/put",
            json={"payload": {"update": "complete"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status_code"] == 204


@pytest.mark.unit
def test_custom_webhook_action_no_url_fails(client, mock_inkpass_permission_check, db_session):
    """Test custom_webhook action fails when no URL is provided and no webhook_url credential."""
    integration = Integration(
        id="test-webhook-no-url",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Webhook No URL",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    # No webhook_url credential - only api_key
    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-nourl",
        integration_id=integration.id,
        credential_type=CredentialType.api_key,  # Not webhook_url
        encrypted_value=encryption_service.encrypt("some-api-key"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-nourl",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    response = client.post(
        "/api/v1/integrations/test-webhook-no-url/actions/post",
        json={"payload": {"test": "data"}},  # No URL in params either
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "require 'url' parameter or webhook_url credential" in data["detail"]


@pytest.mark.unit
def test_custom_webhook_send_message_action(client, mock_inkpass_permission_check, db_session):
    """Test custom_webhook send_message action sends content as JSON body."""
    from unittest.mock import AsyncMock, MagicMock

    integration = Integration(
        id="test-webhook-send-msg",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Webhook Send Message",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-sendmsg",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://api.example.com/messages"),
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-sendmsg",
        integration_id=integration.id,
        action_type=OutboundActionType.send_message,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = mock_client
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-webhook-send-msg/actions/send_message",
            json={"content": "Hello from custom webhook!"},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    # Verify the payload format for send_message
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]
    assert payload["content"] == "Hello from custom webhook!"
    assert payload["message"] == "Hello from custom webhook!"


@pytest.mark.unit
def test_custom_webhook_with_empty_credential_metadata(client, mock_inkpass_permission_check, db_session):
    """Test custom_webhook works with empty/None credential_metadata."""
    from unittest.mock import AsyncMock, MagicMock

    integration = Integration(
        id="test-webhook-empty-meta",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Webhook Empty Metadata",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-emptymeta",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://api.example.com/webhook"),
        credential_metadata=None,  # Explicitly None
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-emptymeta",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-webhook-empty-meta/actions/post",
            json={"payload": {"test": "data"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.unit
def test_custom_webhook_with_invalid_metadata_headers_format(client, mock_inkpass_permission_check, db_session):
    """Test custom_webhook handles invalid credential_metadata headers format gracefully."""
    from unittest.mock import AsyncMock, MagicMock

    integration = Integration(
        id="test-webhook-bad-meta",
        organization_id="test-org-456",
        user_id="test-user-123",
        name="Webhook Bad Metadata",
        provider=IntegrationProvider.custom_webhook,
        direction=IntegrationDirection.outbound,
        status=IntegrationStatus.active,
    )
    db_session.add(integration)
    db_session.flush()

    from src.services.key_encryption import KeyEncryptionService
    encryption_service = KeyEncryptionService()

    credential = IntegrationCredential(
        id="cred-webhook-badmeta",
        integration_id=integration.id,
        credential_type=CredentialType.webhook_url,
        encrypted_value=encryption_service.encrypt("https://api.example.com/webhook"),
        credential_metadata={
            "headers": "not-a-dict",  # Invalid format - should be dict
            "other_field": "value",
        },
    )
    db_session.add(credential)

    outbound_config = IntegrationOutboundConfig(
        id="outbound-webhook-badmeta",
        integration_id=integration.id,
        action_type=OutboundActionType.post,
        is_active=True,
    )
    db_session.add(outbound_config)
    db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_response.text = '{"ok": true}'

    async_context_manager = AsyncMock()
    async_context_manager.__aenter__.return_value = MagicMock(
        post=AsyncMock(return_value=mock_response)
    )
    async_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=async_context_manager):
        response = client.post(
            "/api/v1/integrations/test-webhook-bad-meta/actions/post",
            json={"payload": {"test": "data"}},
            headers={"Authorization": "Bearer mock-token"},
        )

    # Should still work - invalid metadata headers are ignored
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
