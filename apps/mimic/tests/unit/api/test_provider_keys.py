"""Unit tests for provider keys API routes"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_create_provider_key_requires_subscription(client, test_user, test_api_key, mock_inkpass_auth):
    """Test that creating provider key requires annual subscription"""
    api_key_value = test_api_key[1]
    
    response = client.post(
        "/api/v1/provider-keys",
        json={
            "provider_type": "email",
            "api_key": "SG.test-key",
            "from_email": "test@example.com"
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    # Free tier user should get 403
    assert response.status_code == 403


@pytest.mark.unit
def test_create_provider_key_annual(client, test_user_annual, db_session, mock_inkpass_auth):
    """Test creating provider key with annual subscription"""
    # Create API key for annual user
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    
    api_key_value = "annual-api-key-123"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Annual API Key",
    )
    db_session.add(api_key)
    db_session.commit()
    
    response = client.post(
        "/api/v1/provider-keys",
        json={
            "provider_type": "email",
            "api_key": "SG.test-key-123",
            "from_email": "test@example.com"
        },
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["provider_type"] == "email"


@pytest.mark.unit
def test_list_provider_keys(client, test_user_annual, test_provider_key, db_session, mock_inkpass_auth):
    """Test listing provider keys"""
    # Create API key for annual user
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    
    api_key_value = "annual-api-key-456"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Annual API Key",
    )
    db_session.add(api_key)
    db_session.commit()
    
    response = client.get(
        "/api/v1/provider-keys",
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.unit
def test_test_provider_connection(client, test_user_annual, test_provider_key, db_session, mock_inkpass_auth):
    """Test testing provider connection"""
    # Similar setup as above
    from src.api.routes.auth import hash_api_key
    from src.database.models import APIKey
    
    api_key_value = "annual-api-key-789"
    key_hash = hash_api_key(api_key_value)
    
    api_key = APIKey(
        user_id=test_user_annual.id,
        key_hash=key_hash,
        name="Annual API Key",
    )
    db_session.add(api_key)
    db_session.commit()
    
    response = client.post(
        "/api/v1/provider-keys/email/test",
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "message" in data

