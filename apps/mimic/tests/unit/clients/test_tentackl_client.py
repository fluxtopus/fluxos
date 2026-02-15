"""Unit tests for Tentackl client"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.clients.tentackl_client import TentacklClient
from src.database.models import ProviderKey
from src.services.key_encryption import KeyEncryptionService


@pytest.fixture
def tentackl_client():
    """Create Tentackl client instance"""
    with patch('src.clients.tentackl_client.settings') as mock_settings:
        mock_settings.TENTACKL_URL = "http://localhost:8000"
        mock_settings.TENTACKL_API_KEY = "test-api-key"
        mock_settings.TENTACKL_TIMEOUT_SECONDS = 30
        yield TentacklClient()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_success(tentackl_client, db_session, test_user_annual):
    """Test successful notification send"""
    # Create provider key
    encryption_service = KeyEncryptionService()
    encrypted_key = encryption_service.encrypt("SG.test-key")

    provider_key = ProviderKey(
        user_id=test_user_annual.id,
        provider_type="email",
        encrypted_api_key=encrypted_key,
        from_email="test@example.com",
        is_active=True,
    )
    db_session.add(provider_key)
    db_session.commit()

    with patch('src.clients.tentackl_client.SessionLocal', return_value=db_session), \
         patch('httpx.AsyncClient') as mock_client:
        # Mock both the spec lookup and the run request
        mock_spec_response = MagicMock()
        mock_spec_response.status_code = 200
        mock_spec_response.json.return_value = {"id": "spec-123"}
        mock_spec_response.raise_for_status = MagicMock()

        mock_run_response = MagicMock()
        mock_run_response.status_code = 200
        mock_run_response.json.return_value = {"ok": True, "run_id": "workflow-123"}
        mock_run_response.raise_for_status = MagicMock()

        mock_http = mock_client.return_value.__aenter__.return_value
        mock_http.get.return_value = mock_spec_response
        mock_http.post.return_value = mock_run_response

        result = await tentackl_client.send_notification(
            user_id=test_user_annual.id,
            recipient="user@example.com",
            content="Test notification",
            provider="email",
        )

        assert result == "workflow-123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_no_provider_key(tentackl_client, db_session, test_user_annual):
    """Test notification send without provider key"""
    with patch('src.clients.tentackl_client.SessionLocal', return_value=db_session), \
         pytest.raises(ValueError, match="No active provider key found"):
        await tentackl_client.send_notification(
            user_id=test_user_annual.id,
            recipient="user@example.com",
            content="Test notification",
            provider="email",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_workflow_status(tentackl_client):
    """Test getting workflow status"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_id": "workflow-123",
            "status": "completed"
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_http

        result = await tentackl_client.get_workflow_status("workflow-123")

        assert result["workflow_id"] == "workflow-123"
        assert result["status"] == "completed"


@pytest.mark.unit
def test_get_provider_credentials(tentackl_client, test_provider_key):
    """Test getting decrypted provider credentials"""
    encryption_service = KeyEncryptionService()
    original_key = "SG.test-key-123"
    encrypted_key = encryption_service.encrypt(original_key)
    test_provider_key.encrypted_api_key = encrypted_key
    test_provider_key.from_email = "test@example.com"
    
    credentials = tentackl_client._get_provider_credentials(test_provider_key)
    
    assert credentials["api_key"] == original_key
    assert credentials["from_email"] == "test@example.com"

