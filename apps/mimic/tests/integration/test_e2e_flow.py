"""End-to-end integration tests"""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from src.api.routes.auth import hash_api_key
from src.services.key_encryption import KeyEncryptionService
from src.database.models import User, APIKey, ProviderKey, DeliveryLog


@pytest.mark.integration
@pytest.mark.skip(reason="Requires running InkPass service for full authentication flow")
def test_complete_notification_flow(client, db_session):
    """Test complete flow: register -> create API key -> add provider -> send notification"""
    # 1. Register user
    register_response = client.post(
        "/api/v1/register",
        json={
            "email": "e2e@example.com",
            "password": "password123"
        }
    )
    assert register_response.status_code == 200
    user_data = register_response.json()
    user_id = user_data["id"]
    
    # 2. Login
    login_response = client.post(
        "/api/v1/login",
        json={
            "email": "e2e@example.com",
            "password": "password123"
        }
    )
    assert login_response.status_code == 200
    token = login_response.json()["api_key"]
    
    # 3. Create API key
    api_key_response = client.post(
        "/api/v1/api-keys",
        json={"name": "E2E API Key"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert api_key_response.status_code == 200
    api_key_value = api_key_response.json()["key"]
    
    # 4. Upgrade to annual (for BYOK)
    user = db_session.query(User).filter(User.id == user_id).first()
    user.subscription_tier = "annual"
    user.subscription_expires_at = datetime.utcnow() + timedelta(days=365)
    db_session.commit()
    
    # 5. Add provider key
    provider_response = client.post(
        "/api/v1/provider-keys",
        json={
            "provider_type": "email",
            "api_key": "SG.test-key-123",
            "from_email": "test@example.com"
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    assert provider_response.status_code == 200
    
    # 6. Send notification (mocked Tentackl)
    with patch('src.clients.tentackl_client.TentacklClient.send_notification') as mock_send:
        mock_send.return_value = AsyncMock(return_value="workflow-123")
        
        send_response = client.post(
            "/api/v1/send",
            json={
                "recipient": "user@example.com",
                "content": "E2E test notification",
                "provider": "email"
            },
            headers={"Authorization": f"Bearer {api_key_value}"}
        )
        assert send_response.status_code == 200
        delivery_data = send_response.json()
        assert "delivery_id" in delivery_data


@pytest.mark.integration
@pytest.mark.skip(reason="Requires running InkPass service for full authentication flow")
def test_workflow_creation_and_trigger(client, test_user_annual, db_session):
    """Test creating and triggering a workflow"""
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    
    # Create API key
    api_key_value = "workflow-test-key"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Workflow Test Key",
    )
    db_session.add(api_key)
    db_session.commit()
    
    # Create workflow
    workflow_response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Test Workflow",
            "definition_json": {
                "nodes": [
                    {"id": "1", "type": "trigger", "data": {"label": "Start"}},
                    {"id": "2", "type": "action", "data": {"provider": "email"}}
                ],
                "edges": [{"source": "1", "target": "2"}]
            }
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    assert workflow_response.status_code == 200
    workflow_data = workflow_response.json()
    workflow_id = workflow_data["id"]
    
    # Trigger workflow
    with patch('src.clients.tentackl_client.TentacklClient.trigger_workflow') as mock_trigger:
        mock_trigger.return_value = AsyncMock(return_value="workflow-run-123")
        
        trigger_response = client.post(
            f"/api/v1/workflows/{workflow_id}/trigger",
            json={"parameters": {"recipient": "user@example.com"}},
            headers={"Authorization": f"Bearer {api_key_value}"}
        )
        assert trigger_response.status_code == 200

