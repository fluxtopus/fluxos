"""Tests for StripeConfig."""

import pytest

from fluxos_stripe import StripeConfig
from fluxos_stripe.exceptions import StripeConfigError


class TestStripeConfig:
    """Tests for StripeConfig validation."""

    def test_valid_test_key(self):
        """Test with valid test mode API key."""
        config = StripeConfig(api_key="sk_test_123456789")
        assert config.is_test_mode is True
        assert config.is_live_mode is False

    def test_valid_live_key(self):
        """Test with valid live mode API key."""
        config = StripeConfig(api_key="sk_live_123456789")
        assert config.is_test_mode is False
        assert config.is_live_mode is True

    def test_valid_restricted_key(self):
        """Test with valid restricted API key."""
        config = StripeConfig(api_key="rk_test_123456789")
        assert config.is_test_mode is True

    def test_empty_api_key_raises(self):
        """Test that empty API key raises error."""
        with pytest.raises(StripeConfigError, match="api_key is required"):
            StripeConfig(api_key="")

    def test_invalid_api_key_raises(self):
        """Test that invalid API key format raises error."""
        with pytest.raises(StripeConfigError, match="must be a valid Stripe"):
            StripeConfig(api_key="invalid_key_123")

    def test_negative_timeout_raises(self):
        """Test that negative timeout raises error."""
        with pytest.raises(StripeConfigError, match="timeout must be positive"):
            StripeConfig(api_key="sk_test_123", timeout=-1)

    def test_negative_retries_raises(self):
        """Test that negative retries raises error."""
        with pytest.raises(StripeConfigError, match="max_retries must be non-negative"):
            StripeConfig(api_key="sk_test_123", max_retries=-1)

    def test_webhook_secret_optional(self):
        """Test that webhook secret is optional."""
        config = StripeConfig(api_key="sk_test_123")
        assert config.webhook_secret is None

    def test_custom_timeout(self):
        """Test custom timeout value."""
        config = StripeConfig(api_key="sk_test_123", timeout=60.0)
        assert config.timeout == 60.0
