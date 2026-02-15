"""Tests for InkPassConfig."""

import pytest
from inkpass_sdk import InkPassConfig


def test_config_defaults():
    """Test default configuration values."""
    config = InkPassConfig()
    assert config.base_url == "http://localhost:8002"
    assert config.api_key is None
    assert config.timeout == 5.0
    assert config.max_retries == 3
    assert config.retry_min_wait == 1
    assert config.retry_max_wait == 10
    assert config.verify_ssl is True


def test_config_custom_values():
    """Test configuration with custom values."""
    config = InkPassConfig(
        base_url="http://inkpass:8000",
        api_key="test-key",
        timeout=10.0,
        max_retries=5,
    )
    assert config.base_url == "http://inkpass:8000"
    assert config.api_key == "test-key"
    assert config.timeout == 10.0
    assert config.max_retries == 5


def test_config_trailing_slash_removed():
    """Test that trailing slash is removed from base_url."""
    config = InkPassConfig(base_url="http://inkpass:8000/")
    assert config.base_url == "http://inkpass:8000"


def test_config_invalid_timeout():
    """Test that invalid timeout raises ValueError."""
    with pytest.raises(ValueError, match="timeout must be greater than 0"):
        InkPassConfig(timeout=0)


def test_config_invalid_max_retries():
    """Test that invalid max_retries raises ValueError."""
    with pytest.raises(ValueError, match="max_retries must be non-negative"):
        InkPassConfig(max_retries=-1)


def test_config_invalid_retry_wait():
    """Test that invalid retry wait times raise ValueError."""
    with pytest.raises(ValueError, match="retry_max_wait must be >= retry_min_wait"):
        InkPassConfig(retry_min_wait=10, retry_max_wait=5)
