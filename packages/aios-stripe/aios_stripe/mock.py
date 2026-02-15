"""
Mock Stripe client for testing.

Provides an in-memory implementation of StripeClientInterface for testing
without making real Stripe API calls.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from .client import StripeClientInterface
from .exceptions import (
    StripeCustomerError,
    StripePaymentError,
    StripeSubscriptionError,
    StripeWebhookError,
)
from .models import (
    CheckoutSession,
    Customer,
    Price,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)


# Factory functions for creating test data


def customer_factory(**kwargs: Any) -> Customer:
    """Create a test Customer."""
    return Customer(
        id=kwargs.get("id", f"cus_{uuid.uuid4().hex[:14]}"),
        email=kwargs.get("email", f"test-{uuid.uuid4().hex[:6]}@example.com"),
        name=kwargs.get("name"),
        metadata=kwargs.get("metadata", {}),
        created_at=kwargs.get("created_at", datetime.utcnow()),
    )


def subscription_factory(**kwargs: Any) -> Subscription:
    """Create a test Subscription."""
    now = datetime.utcnow()
    return Subscription(
        id=kwargs.get("id", f"sub_{uuid.uuid4().hex[:14]}"),
        customer_id=kwargs.get("customer_id", f"cus_{uuid.uuid4().hex[:14]}"),
        status=kwargs.get("status", SubscriptionStatus.ACTIVE),
        price_id=kwargs.get("price_id", f"price_{uuid.uuid4().hex[:14]}"),
        current_period_start=kwargs.get("current_period_start", now),
        current_period_end=kwargs.get(
            "current_period_end", now + timedelta(days=30)
        ),
        cancel_at_period_end=kwargs.get("cancel_at_period_end", False),
        canceled_at=kwargs.get("canceled_at"),
        metadata=kwargs.get("metadata", {}),
    )


def checkout_session_factory(**kwargs: Any) -> CheckoutSession:
    """Create a test CheckoutSession."""
    session_id = kwargs.get("id", f"cs_{uuid.uuid4().hex[:24]}")
    return CheckoutSession(
        id=session_id,
        url=kwargs.get("url", f"https://checkout.stripe.com/c/pay/{session_id}"),
        customer_email=kwargs.get("customer_email"),
        customer_id=kwargs.get("customer_id"),
        price_id=kwargs.get("price_id", ""),
        metadata=kwargs.get("metadata", {}),
        status=kwargs.get("status", "open"),
        payment_status=kwargs.get("payment_status", "unpaid"),
    )


def price_factory(**kwargs: Any) -> Price:
    """Create a test Price."""
    return Price(
        id=kwargs.get("id", f"price_{uuid.uuid4().hex[:14]}"),
        product_id=kwargs.get("product_id", f"prod_{uuid.uuid4().hex[:14]}"),
        unit_amount=kwargs.get("unit_amount", 4900),  # $49.00
        currency=kwargs.get("currency", "usd"),
        recurring_interval=kwargs.get("recurring_interval", "month"),
        active=kwargs.get("active", True),
    )


def webhook_event_factory(**kwargs: Any) -> WebhookEvent:
    """Create a test WebhookEvent."""
    return WebhookEvent(
        id=kwargs.get("id", f"evt_{uuid.uuid4().hex[:14]}"),
        type=kwargs.get("type", "checkout.session.completed"),
        data=kwargs.get("data", {"object": {}}),
        created=kwargs.get("created", datetime.utcnow()),
        livemode=kwargs.get("livemode", False),
    )


class MockStripeClient(StripeClientInterface):
    """Mock Stripe client for testing.

    Stores data in memory and simulates Stripe API behavior.

    Example:
        mock_client = MockStripeClient()

        # Pre-populate with test data
        mock_client.add_customer(customer_factory(email="test@example.com"))

        # Or let it create on demand
        customer = await mock_client.create_customer(email="new@example.com")
    """

    def __init__(self) -> None:
        """Initialize the mock client."""
        self._customers: dict[str, Customer] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._checkout_sessions: dict[str, CheckoutSession] = {}
        self._prices: dict[str, Price] = {}

        # Control flags for testing error scenarios
        self._should_fail = False
        self._fail_message = "Mock failure"
        self._is_healthy = True

    # Control methods for testing

    def set_should_fail(self, should_fail: bool, message: str = "Mock failure") -> None:
        """Configure the mock to fail on next operation."""
        self._should_fail = should_fail
        self._fail_message = message

    def set_healthy(self, healthy: bool) -> None:
        """Set health check result."""
        self._is_healthy = healthy

    def add_customer(self, customer: Customer) -> None:
        """Add a customer to the mock store."""
        self._customers[customer.id] = customer

    def add_subscription(self, subscription: Subscription) -> None:
        """Add a subscription to the mock store."""
        self._subscriptions[subscription.id] = subscription

    def add_checkout_session(self, session: CheckoutSession) -> None:
        """Add a checkout session to the mock store."""
        self._checkout_sessions[session.id] = session

    def add_price(self, price: Price) -> None:
        """Add a price to the mock store."""
        self._prices[price.id] = price

    def clear(self) -> None:
        """Clear all stored data."""
        self._customers.clear()
        self._subscriptions.clear()
        self._checkout_sessions.clear()
        self._prices.clear()

    def _check_failure(self, exception_class: type[Exception]) -> None:
        """Check if mock should fail and raise exception."""
        if self._should_fail:
            self._should_fail = False  # Reset after one failure
            raise exception_class(self._fail_message)

    # Customer operations

    async def create_customer(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Customer:
        """Create a mock customer."""
        self._check_failure(StripeCustomerError)

        customer = customer_factory(
            email=email,
            name=name,
            metadata=metadata or {},
        )
        self._customers[customer.id] = customer
        return customer

    async def get_customer(self, customer_id: str) -> Customer | None:
        """Get a customer by ID."""
        self._check_failure(StripeCustomerError)
        return self._customers.get(customer_id)

    async def get_customer_by_email(self, email: str) -> Customer | None:
        """Get a customer by email."""
        self._check_failure(StripeCustomerError)
        for customer in self._customers.values():
            if customer.email == email:
                return customer
        return None

    # Checkout operations

    async def create_checkout_session(
        self,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        """Create a mock checkout session."""
        self._check_failure(StripePaymentError)

        session = checkout_session_factory(
            customer_email=customer_email,
            price_id=price_id,
            metadata=metadata or {},
        )
        self._checkout_sessions[session.id] = session
        return session

    async def get_checkout_session(self, session_id: str) -> CheckoutSession | None:
        """Get a checkout session by ID."""
        self._check_failure(StripePaymentError)
        return self._checkout_sessions.get(session_id)

    # Subscription operations

    async def get_subscription(self, subscription_id: str) -> Subscription | None:
        """Get a subscription by ID."""
        self._check_failure(StripeSubscriptionError)
        return self._subscriptions.get(subscription_id)

    async def list_customer_subscriptions(self, customer_id: str) -> list[Subscription]:
        """List all subscriptions for a customer."""
        self._check_failure(StripeSubscriptionError)
        return [
            sub
            for sub in self._subscriptions.values()
            if sub.customer_id == customer_id
        ]

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str] | None = None,
    ) -> Subscription:
        """Create a mock subscription directly."""
        self._check_failure(StripeSubscriptionError)

        if customer_id not in self._customers:
            raise StripeSubscriptionError(
                f"Customer not found: {customer_id}",
                details={"customer_id": customer_id},
            )

        subscription = subscription_factory(
            customer_id=customer_id,
            price_id=price_id,
            metadata=metadata or {},
        )
        self._subscriptions[subscription.id] = subscription
        return subscription

    async def cancel_subscription(
        self, subscription_id: str, at_period_end: bool = True
    ) -> Subscription:
        """Cancel a subscription."""
        self._check_failure(StripeSubscriptionError)

        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            raise StripeSubscriptionError(
                f"Subscription not found: {subscription_id}",
                details={"subscription_id": subscription_id},
            )

        # Update the subscription
        if at_period_end:
            subscription.cancel_at_period_end = True
        else:
            subscription.status = SubscriptionStatus.CANCELED
            subscription.canceled_at = datetime.utcnow()

        return subscription

    # Webhook operations

    def verify_webhook_signature(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify webhook signature (mock always succeeds with valid signature)."""
        if signature == "invalid":
            raise StripeWebhookError("Invalid webhook signature")

        # Parse the payload and create event
        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise StripeWebhookError("Invalid webhook payload", original_error=e)

        return webhook_event_factory(
            type=data.get("type", "test.event"),
            data=data.get("data", {}),
        )

    # Price operations

    async def get_price(self, price_id: str) -> Price | None:
        """Get a price by ID."""
        self._check_failure(StripePaymentError)
        return self._prices.get(price_id)

    async def list_prices(self, product_id: str | None = None) -> list[Price]:
        """List all prices, optionally filtered by product."""
        self._check_failure(StripePaymentError)

        prices = list(self._prices.values())
        if product_id:
            prices = [p for p in prices if p.product_id == product_id]
        return [p for p in prices if p.active]

    # Billing portal

    async def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> str:
        """Create a mock billing portal session."""
        self._check_failure(StripePaymentError)

        if customer_id not in self._customers:
            raise StripeCustomerError(
                f"Customer not found: {customer_id}",
                details={"customer_id": customer_id},
            )

        session_id = f"bps_{uuid.uuid4().hex[:24]}"
        return f"https://billing.stripe.com/p/session/{session_id}"

    # Health check

    async def health_check(self) -> bool:
        """Return configured health status."""
        return self._is_healthy

    # Simulation helpers

    def simulate_checkout_complete(
        self, session_id: str
    ) -> tuple[Customer, Subscription]:
        """Simulate a checkout completion.

        Creates customer and subscription from the checkout session.
        Returns the created customer and subscription.
        """
        session = self._checkout_sessions.get(session_id)
        if not session:
            raise ValueError(f"Checkout session not found: {session_id}")

        # Create or get customer
        customer = None
        if session.customer_email:
            for c in self._customers.values():
                if c.email == session.customer_email:
                    customer = c
                    break

        if not customer:
            customer = customer_factory(email=session.customer_email or "unknown@example.com")
            self._customers[customer.id] = customer

        # Create subscription
        subscription = subscription_factory(
            customer_id=customer.id,
            price_id=session.price_id,
        )
        self._subscriptions[subscription.id] = subscription

        # Update session
        session.status = "complete"
        session.payment_status = "paid"
        session.customer_id = customer.id

        return customer, subscription
