"""Unit tests for authentication routes"""

import pytest
from fastapi.testclient import TestClient
from src.api.routes.auth import hash_api_key, get_password_hash, verify_password
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


@pytest.mark.unit
def test_hash_api_key():
    """Test API key hashing"""
    key = "test-api-key-123"
    hashed = hash_api_key(key)
    
    assert hashed != key
    assert len(hashed) == 64  # SHA256 hex digest length
    assert hash_api_key(key) == hashed  # Deterministic


@pytest.mark.unit
def test_password_hashing():
    """Test password hashing and verification"""
    password = "testpassword123"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


@pytest.mark.unit
def test_register_user(client, db_session):
    """Test user registration"""
    response = client.post(
        "/api/v1/register",
        json={
            "email": "newuser@example.com",
            "password": "securepassword123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["email"] == "newuser@example.com"


@pytest.mark.unit
def test_register_duplicate_email(client, test_user):
    """Test registering with duplicate email"""
    response = client.post(
        "/api/v1/register",
        json={
            "email": test_user.email,
            "password": "password123"
        }
    )
    
    assert response.status_code == 400


@pytest.mark.unit
def test_login_success(client, test_user):
    """Test successful login"""
    response = client.post(
        "/api/v1/login",
        json={
            "email": test_user.email,
            "password": "testpassword123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "api_key" in data
    assert "user_id" in data


@pytest.mark.unit
def test_login_invalid_credentials(client, test_user):
    """Test login with invalid credentials"""
    response = client.post(
        "/api/v1/login",
        json={
            "email": test_user.email,
            "password": "wrongpassword"
        }
    )
    
    assert response.status_code == 401


@pytest.mark.unit
def test_create_api_key(client, test_user, test_api_key):
    """Test creating API key"""
    # First login to get token
    login_response = client.post(
        "/api/v1/login",
        json={
            "email": test_user.email,
            "password": "testpassword123"
        }
    )
    api_key = login_response.json()["api_key"]

    response = client.post(
        "/api/v1/api-keys",
        json={"name": "New API Key"},
        headers={"Authorization": f"Bearer {api_key}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "key" in data
    assert "name" in data


@pytest.mark.unit
def test_get_current_user_with_api_key(client, test_api_key):
    """Test getting current user with API key"""
    api_key_value = test_api_key[1]
    
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {api_key_value}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"


@pytest.mark.unit
def test_get_current_user_invalid_key(client):
    """Test getting current user with invalid API key"""
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer invalid-key"}
    )
    
    assert response.status_code == 401

