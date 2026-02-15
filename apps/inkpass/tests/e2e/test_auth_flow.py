"""End-to-end tests for authentication flow"""

import pytest
from fastapi import status


@pytest.mark.e2e
def test_complete_auth_flow(client, db):
    """Test complete authentication flow: register -> login -> get user info"""
    # 1. Register
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "e2e@example.com",
            "password": "e2e_password_123",
            "organization_name": "E2E Test Org"
        }
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    
    # 2. Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "e2e@example.com",
            "password": "e2e_password_123"
        }
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]
    
    # 3. Get user info
    user_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert user_response.status_code == status.HTTP_200_OK
    user_data = user_response.json()
    assert user_data["email"] == "e2e@example.com"
    assert "organization_id" in user_data


