"""E2E tests for health check and basic connectivity."""

import os
import pytest

from fluxos_stripe import StripeClient


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("STRIPE_TEST_API_KEY"),
        reason="STRIPE_TEST_API_KEY not set",
    ),
]


class TestHealthCheckE2E:
    """E2E tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_passes(self, live_client: StripeClient):
        """Test that health check passes with valid API key."""
        is_healthy = await live_client.health_check()
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_list_prices(self, live_client: StripeClient):
        """Test listing prices from Stripe."""
        prices = await live_client.list_prices()
        # Should return a list (may be empty if no products configured)
        assert isinstance(prices, list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_price(self, live_client: StripeClient):
        """Test getting a non-existent price."""
        price = await live_client.get_price("price_nonexistent123")
        assert price is None
