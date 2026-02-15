"""Unit tests for password security"""

import pytest
from src.security.password import hash_password, verify_password


@pytest.mark.unit
def test_hash_password():
    """Test password hashing"""
    password = "test_password_123"
    hashed = hash_password(password)
    
    assert hashed != password
    assert len(hashed) > 0
    assert hashed.startswith("$2b$")  # bcrypt hash format


@pytest.mark.unit
def test_verify_password_correct():
    """Test password verification with correct password"""
    password = "test_password_123"
    hashed = hash_password(password)
    
    assert verify_password(password, hashed) is True


@pytest.mark.unit
def test_verify_password_incorrect():
    """Test password verification with incorrect password"""
    password = "test_password_123"
    hashed = hash_password(password)
    
    assert verify_password("wrong_password", hashed) is False


@pytest.mark.unit
def test_hash_password_different_hashes():
    """Test that same password produces different hashes (due to salt)"""
    password = "test_password_123"
    hashed1 = hash_password(password)
    hashed2 = hash_password(password)
    
    # Hashes should be different due to salt
    assert hashed1 != hashed2
    # But both should verify correctly
    assert verify_password(password, hashed1) is True
    assert verify_password(password, hashed2) is True


