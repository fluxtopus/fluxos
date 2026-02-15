"""Unit tests for key encryption service"""

import pytest
from src.services.key_encryption import KeyEncryptionService


@pytest.fixture
def encryption_service():
    """Create encryption service instance"""
    return KeyEncryptionService()


@pytest.mark.unit
def test_encrypt_decrypt(encryption_service):
    """Test encryption and decryption round-trip"""
    original = "test-api-key-12345"
    
    encrypted = encryption_service.encrypt(original)
    assert encrypted != original
    assert len(encrypted) > 0
    
    decrypted = encryption_service.decrypt(encrypted)
    assert decrypted == original


@pytest.mark.unit
def test_encrypt_different_keys(encryption_service):
    """Test that different keys encrypt to different values"""
    key1 = "key-1"
    key2 = "key-2"
    
    encrypted1 = encryption_service.encrypt(key1)
    encrypted2 = encryption_service.encrypt(key2)
    
    assert encrypted1 != encrypted2


@pytest.mark.unit
def test_encrypt_same_key_different(encryption_service):
    """Test that same key encrypts differently each time (IV)"""
    key = "same-key"
    
    encrypted1 = encryption_service.encrypt(key)
    encrypted2 = encryption_service.encrypt(key)
    
    # Should be different due to random IV
    assert encrypted1 != encrypted2
    
    # But both should decrypt to same value
    assert encryption_service.decrypt(encrypted1) == key
    assert encryption_service.decrypt(encrypted2) == key


@pytest.mark.unit
def test_decrypt_invalid(encryption_service):
    """Test decrypting invalid data"""
    with pytest.raises(Exception):
        encryption_service.decrypt("invalid-encrypted-data")


@pytest.mark.unit
def test_encrypt_empty_string(encryption_service):
    """Test encrypting empty string"""
    encrypted = encryption_service.encrypt("")
    decrypted = encryption_service.decrypt(encrypted)
    assert decrypted == ""


@pytest.mark.unit
def test_encrypt_long_string(encryption_service):
    """Test encrypting long string"""
    long_string = "a" * 1000
    encrypted = encryption_service.encrypt(long_string)
    decrypted = encryption_service.decrypt(encrypted)
    assert decrypted == long_string

