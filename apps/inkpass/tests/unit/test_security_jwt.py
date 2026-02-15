"""Unit tests for JWT security"""

import pytest
from datetime import timedelta
from src.security.jwt import create_access_token, create_refresh_token, decode_token


@pytest.mark.unit
def test_create_access_token():
    """Test access token creation"""
    data = {"sub": "user123", "email": "test@example.com"}
    token = create_access_token(data)
    
    assert token is not None
    assert len(token) > 0
    assert isinstance(token, str)


@pytest.mark.unit
def test_create_refresh_token():
    """Test refresh token creation"""
    data = {"sub": "user123", "email": "test@example.com"}
    token = create_refresh_token(data)
    
    assert token is not None
    assert len(token) > 0
    assert isinstance(token, str)


@pytest.mark.unit
def test_decode_token_valid():
    """Test decoding a valid token"""
    data = {"sub": "user123", "email": "test@example.com"}
    token = create_access_token(data)
    decoded = decode_token(token)
    
    assert decoded is not None
    assert decoded["sub"] == "user123"
    assert decoded["email"] == "test@example.com"


@pytest.mark.unit
def test_decode_token_invalid():
    """Test decoding an invalid token"""
    invalid_token = "invalid.token.here"
    decoded = decode_token(invalid_token)
    
    assert decoded is None


@pytest.mark.unit
def test_refresh_token_has_type():
    """Test that refresh token has type field"""
    data = {"sub": "user123"}
    token = create_refresh_token(data)
    decoded = decode_token(token)
    
    assert decoded is not None
    assert decoded.get("type") == "refresh"


