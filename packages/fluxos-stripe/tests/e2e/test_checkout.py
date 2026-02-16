"""E2E tests for checkout operations with real Stripe API."""

import os
import time
import pytest

from fluxos_stripe import StripeClient


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("STRIPE_TEST_API_KEY"),
        reason="STRIPE_TEST_API_KEY not set",
    ),
    pytest.mark.skipif(
        not os.getenv("STRIPE_TEST_PRICE_ID"),
        reason="STRIPE_TEST_PRICE_ID not set",
    ),
]


class TestCheckoutOperationsE2E:
    """E2E tests for checkout session operations."""

    @pytest.mark.asyncio
    async def test_create_checkout_session(
        self, live_client: StripeClient, test_price_id: str
    ):
        """Test creating a real checkout session."""
        email = f"checkout-{int(time.time())}@fluxtopus.com"

        session = await live_client.create_checkout_session(
            price_id=test_price_id,
            customer_email=email,
            success_url="https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://example.com/cancel",
            metadata={"test": "true"},
        )

        assert session.id.startswith("cs_")
        assert session.url.startswith("https://checkout.stripe.com")
        assert session.status == "open"
        assert session.payment_status == "unpaid"

    @pytest.mark.asyncio
    async def test_get_checkout_session(
        self, live_client: StripeClient, test_price_id: str
    ):
        """Test retrieving a checkout session."""
        email = f"checkout-get-{int(time.time())}@fluxtopus.com"

        # Create session
        session = await live_client.create_checkout_session(
            price_id=test_price_id,
            customer_email=email,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )

        # Retrieve it
        fetched = await live_client.get_checkout_session(session.id)
        assert fetched is not None
        assert fetched.id == session.id
        assert fetched.status == "open"

    @pytest.mark.asyncio
    async def test_get_checkout_session_not_found(self, live_client: StripeClient):
        """Test retrieving a non-existent checkout session."""
        fetched = await live_client.get_checkout_session("cs_nonexistent123456")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_checkout_session_with_metadata(
        self, live_client: StripeClient, test_price_id: str
    ):
        """Test checkout session metadata is properly stored."""
        email = f"checkout-meta-{int(time.time())}@fluxtopus.com"

        session = await live_client.create_checkout_session(
            price_id=test_price_id,
            customer_email=email,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={
                "product_type": "starter",
                "source": "landing_page",
            },
        )

        assert session.metadata["product_type"] == "starter"
        assert session.metadata["source"] == "landing_page"
