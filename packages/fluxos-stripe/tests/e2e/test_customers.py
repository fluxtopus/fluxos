"""E2E tests for customer operations with real Stripe API."""

import os
import time
import pytest
import stripe

from fluxos_stripe import StripeClient


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("STRIPE_TEST_API_KEY"),
        reason="STRIPE_TEST_API_KEY not set",
    ),
]


class TestCustomerOperationsE2E:
    """E2E tests for customer CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_customer(self, live_client: StripeClient):
        """Test creating a real Stripe customer."""
        email = f"test-{int(time.time())}@fluxtopus.com"

        customer = await live_client.create_customer(
            email=email,
            name="E2E Test Customer",
            metadata={"test": "true", "source": "fluxos-stripe-e2e"},
        )

        try:
            assert customer.id.startswith("cus_")
            assert customer.email == email
            assert customer.name == "E2E Test Customer"
            assert customer.metadata.get("test") == "true"
        finally:
            # Cleanup
            stripe.Customer.delete(customer.id)

    @pytest.mark.asyncio
    async def test_get_customer(self, live_client: StripeClient):
        """Test retrieving a customer by ID."""
        email = f"test-get-{int(time.time())}@fluxtopus.com"

        # Create
        customer = await live_client.create_customer(email=email)

        try:
            # Retrieve
            fetched = await live_client.get_customer(customer.id)
            assert fetched is not None
            assert fetched.id == customer.id
            assert fetched.email == email
        finally:
            stripe.Customer.delete(customer.id)

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, live_client: StripeClient):
        """Test retrieving a non-existent customer."""
        fetched = await live_client.get_customer("cus_nonexistent123456")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_customer_by_email(self, live_client: StripeClient):
        """Test searching for a customer by email."""
        email = f"test-search-{int(time.time())}@fluxtopus.com"

        customer = await live_client.create_customer(email=email)

        try:
            # Search
            found = await live_client.get_customer_by_email(email)
            assert found is not None
            assert found.id == customer.id
            assert found.email == email
        finally:
            stripe.Customer.delete(customer.id)

    @pytest.mark.asyncio
    async def test_get_customer_by_email_not_found(self, live_client: StripeClient):
        """Test searching for a non-existent customer email."""
        found = await live_client.get_customer_by_email("nonexistent@fluxtopus.com")
        assert found is None

    @pytest.mark.asyncio
    async def test_customer_with_metadata(self, live_client: StripeClient):
        """Test customer metadata is properly stored and retrieved."""
        email = f"test-meta-{int(time.time())}@fluxtopus.com"

        customer = await live_client.create_customer(
            email=email,
            metadata={
                "organization_id": "org_123",
                "plan": "starter",
                "source": "api",
            },
        )

        try:
            fetched = await live_client.get_customer(customer.id)
            assert fetched is not None
            assert fetched.metadata["organization_id"] == "org_123"
            assert fetched.metadata["plan"] == "starter"
        finally:
            stripe.Customer.delete(customer.id)
