"""Tests for MockStripeClient."""

import pytest

from fluxos_stripe.exceptions import (
    StripeCustomerError,
    StripeSubscriptionError,
    StripeWebhookError,
)
from fluxos_stripe.mock import (
    MockStripeClient,
    customer_factory,
    subscription_factory,
    checkout_session_factory,
    price_factory,
)
from fluxos_stripe.models import SubscriptionStatus


class TestFactories:
    """Tests for test data factories."""

    def test_customer_factory_defaults(self):
        """Test customer factory with defaults."""
        customer = customer_factory()
        assert customer.id.startswith("cus_")
        assert "@" in customer.email
        assert customer.name is None

    def test_customer_factory_custom(self):
        """Test customer factory with custom values."""
        customer = customer_factory(
            id="cus_custom123",
            email="custom@test.com",
            name="Custom User",
        )
        assert customer.id == "cus_custom123"
        assert customer.email == "custom@test.com"
        assert customer.name == "Custom User"

    def test_subscription_factory_defaults(self):
        """Test subscription factory with defaults."""
        sub = subscription_factory()
        assert sub.id.startswith("sub_")
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.cancel_at_period_end is False

    def test_checkout_session_factory(self):
        """Test checkout session factory."""
        session = checkout_session_factory(customer_email="test@example.com")
        assert session.id.startswith("cs_")
        assert "checkout.stripe.com" in session.url
        assert session.customer_email == "test@example.com"

    def test_price_factory(self):
        """Test price factory."""
        price = price_factory(unit_amount=9900)
        assert price.id.startswith("price_")
        assert price.unit_amount == 9900
        assert price.recurring_interval == "month"


class TestMockStripeClient:
    """Tests for MockStripeClient."""

    @pytest.mark.asyncio
    async def test_create_customer(self, mock_client: MockStripeClient):
        """Test creating a customer."""
        customer = await mock_client.create_customer(
            email="test@example.com",
            name="Test User",
        )
        assert customer.email == "test@example.com"
        assert customer.name == "Test User"
        assert customer.id.startswith("cus_")

    @pytest.mark.asyncio
    async def test_get_customer(self, mock_client: MockStripeClient):
        """Test getting a customer by ID."""
        # Create a customer
        customer = await mock_client.create_customer(email="test@example.com")

        # Retrieve it
        fetched = await mock_client.get_customer(customer.id)
        assert fetched is not None
        assert fetched.id == customer.id
        assert fetched.email == customer.email

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, mock_client: MockStripeClient):
        """Test getting a non-existent customer."""
        fetched = await mock_client.get_customer("cus_nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_customer_by_email(self, mock_client: MockStripeClient):
        """Test getting a customer by email."""
        customer = await mock_client.create_customer(email="find@example.com")

        found = await mock_client.get_customer_by_email("find@example.com")
        assert found is not None
        assert found.id == customer.id

    @pytest.mark.asyncio
    async def test_create_checkout_session(self, mock_client: MockStripeClient):
        """Test creating a checkout session."""
        session = await mock_client.create_checkout_session(
            price_id="price_123",
            customer_email="buyer@example.com",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        assert session.id.startswith("cs_")
        assert session.customer_email == "buyer@example.com"
        assert session.price_id == "price_123"
        assert session.status == "open"

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, mock_client: MockStripeClient):
        """Test canceling a subscription."""
        # Add a subscription
        sub = subscription_factory()
        mock_client.add_subscription(sub)

        # Cancel at period end
        cancelled = await mock_client.cancel_subscription(sub.id, at_period_end=True)
        assert cancelled.cancel_at_period_end is True
        assert cancelled.status == SubscriptionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_cancel_subscription_immediately(self, mock_client: MockStripeClient):
        """Test canceling a subscription immediately."""
        sub = subscription_factory()
        mock_client.add_subscription(sub)

        cancelled = await mock_client.cancel_subscription(sub.id, at_period_end=False)
        assert cancelled.status == SubscriptionStatus.CANCELED
        assert cancelled.canceled_at is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_subscription(self, mock_client: MockStripeClient):
        """Test canceling a non-existent subscription."""
        with pytest.raises(StripeSubscriptionError, match="not found"):
            await mock_client.cancel_subscription("sub_nonexistent")

    def test_verify_webhook_valid(self, mock_client: MockStripeClient):
        """Test webhook verification with valid signature."""
        payload = b'{"type": "checkout.session.completed", "data": {}}'
        event = mock_client.verify_webhook_signature(payload, "valid_signature")
        assert event.type == "checkout.session.completed"

    def test_verify_webhook_invalid_signature(self, mock_client: MockStripeClient):
        """Test webhook verification with invalid signature."""
        with pytest.raises(StripeWebhookError, match="Invalid webhook signature"):
            mock_client.verify_webhook_signature(b"{}", "invalid")

    def test_verify_webhook_invalid_payload(self, mock_client: MockStripeClient):
        """Test webhook verification with invalid JSON payload."""
        with pytest.raises(StripeWebhookError, match="Invalid webhook payload"):
            mock_client.verify_webhook_signature(b"not json", "valid")

    @pytest.mark.asyncio
    async def test_health_check(self, mock_client: MockStripeClient):
        """Test health check."""
        assert await mock_client.health_check() is True

        mock_client.set_healthy(False)
        assert await mock_client.health_check() is False

    @pytest.mark.asyncio
    async def test_failure_simulation(self, mock_client: MockStripeClient):
        """Test failure simulation."""
        mock_client.set_should_fail(True, "Simulated failure")

        with pytest.raises(StripeCustomerError, match="Simulated failure"):
            await mock_client.create_customer(email="test@example.com")

        # Should only fail once
        customer = await mock_client.create_customer(email="test@example.com")
        assert customer is not None

    def test_simulate_checkout_complete(self, mock_client: MockStripeClient):
        """Test simulating checkout completion."""
        # Create a checkout session
        session = checkout_session_factory(
            id="cs_test123",
            customer_email="buyer@example.com",
            price_id="price_123",
        )
        mock_client.add_checkout_session(session)

        # Simulate completion
        customer, subscription = mock_client.simulate_checkout_complete("cs_test123")

        assert customer.email == "buyer@example.com"
        assert subscription.customer_id == customer.id
        assert subscription.price_id == "price_123"
        assert subscription.status == SubscriptionStatus.ACTIVE
