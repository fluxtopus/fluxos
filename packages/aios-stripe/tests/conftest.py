"""Shared test fixtures."""

import os
import pytest

from aios_stripe import StripeClient, StripeConfig
from aios_stripe.mock import MockStripeClient


@pytest.fixture
def mock_client() -> MockStripeClient:
    """Create a mock Stripe client for unit tests."""
    return MockStripeClient()


@pytest.fixture
def test_config() -> StripeConfig:
    """Create a test config with fake API key."""
    return StripeConfig(
        api_key="sk_test_fake123456789",
        webhook_secret="whsec_test123456789",
    )


@pytest.fixture
def live_config() -> StripeConfig | None:
    """Create a config for E2E tests with real Stripe.

    Returns None if STRIPE_TEST_API_KEY is not set.
    """
    api_key = os.environ.get("STRIPE_TEST_API_KEY")
    if not api_key:
        return None

    return StripeConfig(
        api_key=api_key,
        webhook_secret=os.environ.get("STRIPE_TEST_WEBHOOK_SECRET"),
    )


@pytest.fixture
def live_client(live_config: StripeConfig | None) -> StripeClient | None:
    """Create a real Stripe client for E2E tests.

    Returns None if STRIPE_TEST_API_KEY is not set.
    """
    if not live_config:
        return None
    return StripeClient(live_config)


@pytest.fixture
def test_price_id() -> str | None:
    """Get a test price ID for checkout tests.

    Returns None if STRIPE_TEST_PRICE_ID is not set.
    """
    return os.environ.get("STRIPE_TEST_PRICE_ID")
