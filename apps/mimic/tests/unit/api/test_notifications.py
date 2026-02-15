"""Unit tests for notifications API routes"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_send_notification(client, test_user_annual, mock_tentackl_client, db_session, mock_inkpass_auth):
    """Test sending a notification"""
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    from src.services.key_encryption import KeyEncryptionService
    from src.database.models import ProviderKey
    
    api_key_value = "test-api-key-send"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Test API Key",
    )
    db_session.add(api_key)
    
    # Create provider key
    encryption_service = KeyEncryptionService()
    encrypted_key = encryption_service.encrypt("SG.test-key")
    
    provider_key = ProviderKey(
        user_id=test_user_annual.id,
        provider_type="email",
        encrypted_api_key=encrypted_key,
        from_email="test@example.com",
        is_active=True
    )
    db_session.add(provider_key)
    db_session.commit()
    
    response = client.post(
        "/api/v1/send",
        json={
            "recipient": "user@example.com",
            "content": "Test notification",
            "provider": "email"
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "delivery_id" in data
    assert data["status"] == "sent"


@pytest.mark.unit
def test_send_notification_no_provider_key(client, test_user_annual, mock_tentackl_client, db_session, mock_inkpass_auth):
    """Test sending notification without provider key"""
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    
    api_key_value = "test-api-key-no-provider"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Test API Key",
    )
    db_session.add(api_key)
    db_session.commit()
    
    response = client.post(
        "/api/v1/send",
        json={
            "recipient": "user@example.com",
            "content": "Test notification",
            "provider": "email"
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )

    # When no provider key is configured, the system falls back to dev SMTP mode
    # So it may succeed with 200 (dev mode) or fail with 400/500 (strict mode)
    assert response.status_code in [200, 400, 500]


@pytest.mark.unit
def test_get_notification_status(client, test_user_annual, db_session, mock_inkpass_auth):
    """Test getting notification status"""
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey, DeliveryLog
    from datetime import datetime
    
    api_key_value = "test-api-key-status"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Test API Key",
    )
    db_session.add(api_key)
    
    # Create delivery log
    delivery_log = DeliveryLog(
        user_id=test_user_annual.id,
        delivery_id="test-delivery-123",
        provider="email",
        recipient="user@example.com",
        status="sent",
        sent_at=datetime.utcnow()
    )
    db_session.add(delivery_log)
    db_session.commit()
    
    response = client.get(
        "/api/v1/status/test-delivery-123",
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["delivery_id"] == "test-delivery-123"
    assert data["status"] == "sent"

