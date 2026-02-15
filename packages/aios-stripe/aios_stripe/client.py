"""
Stripe client implementation.

Concrete implementation using the official Stripe API.
Handles all payment processing, customer management, and subscription operations.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import stripe
import structlog

from .config import StripeConfig
from .exceptions import (
    StripeConnectionError,
    StripeCustomerError,
    StripeError,
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

logger = structlog.get_logger(__name__)


class StripeClientInterface(ABC):
    """Abstract interface for Stripe operations."""

    # Customer operations
    @abstractmethod
    async def create_customer(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Customer:
        """Create a new Stripe customer."""
        ...

    @abstractmethod
    async def get_customer(self, customer_id: str) -> Customer | None:
        """Get a customer by ID."""
        ...

    @abstractmethod
    async def get_customer_by_email(self, email: str) -> Customer | None:
        """Get a customer by email."""
        ...

    # Checkout operations
    @abstractmethod
    async def create_checkout_session(
        self,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        """Create a Stripe Checkout session."""
        ...

    @abstractmethod
    async def get_checkout_session(self, session_id: str) -> CheckoutSession | None:
        """Get a checkout session by ID."""
        ...

    # Subscription operations
    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> Subscription | None:
        """Get a subscription by ID."""
        ...

    @abstractmethod
    async def list_customer_subscriptions(self, customer_id: str) -> list[Subscription]:
        """List all subscriptions for a customer."""
        ...

    @abstractmethod
    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str] | None = None,
    ) -> Subscription:
        """Create a subscription directly (without checkout session)."""
        ...

    @abstractmethod
    async def cancel_subscription(
        self, subscription_id: str, at_period_end: bool = True
    ) -> Subscription:
        """Cancel a subscription."""
        ...

    # Webhook operations
    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify webhook signature and parse event."""
        ...

    # Price operations
    @abstractmethod
    async def get_price(self, price_id: str) -> Price | None:
        """Get a price by ID."""
        ...

    @abstractmethod
    async def list_prices(self, product_id: str | None = None) -> list[Price]:
        """List all active prices, optionally filtered by product."""
        ...

    # Billing portal
    @abstractmethod
    async def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> str:
        """Create a billing portal session. Returns the portal URL."""
        ...

    # Health check
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the Stripe API is accessible."""
        ...


class StripeClient(StripeClientInterface):
    """Concrete Stripe client implementation."""

    def __init__(self, config: StripeConfig):
        """Initialize the Stripe client.

        Args:
            config: StripeConfig instance with API credentials
        """
        self.config = config
        stripe.api_key = config.api_key

        logger.info(
            "stripe_client_initialized",
            is_test_mode=config.is_test_mode,
        )

    def _convert_stripe_customer(self, stripe_customer: Any) -> Customer:
        """Convert Stripe customer object to Customer model."""
        return Customer(
            id=stripe_customer.id,
            email=stripe_customer.email,
            name=stripe_customer.name,
            metadata=dict(stripe_customer.metadata or {}),
            created_at=datetime.fromtimestamp(stripe_customer.created),
        )

    def _convert_stripe_subscription(self, stripe_sub: Any) -> Subscription:
        """Convert Stripe subscription object to Subscription model."""
        price_id = stripe_sub.items.data[0].price.id if stripe_sub.items.data else ""

        return Subscription(
            id=stripe_sub.id,
            customer_id=stripe_sub.customer,
            status=SubscriptionStatus(stripe_sub.status),
            price_id=price_id,
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end),
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
            canceled_at=(
                datetime.fromtimestamp(stripe_sub.canceled_at)
                if stripe_sub.canceled_at
                else None
            ),
            metadata=dict(stripe_sub.metadata or {}),
        )

    def _convert_stripe_checkout_session(self, stripe_session: Any) -> CheckoutSession:
        """Convert Stripe checkout session to CheckoutSession model."""
        price_id = ""
        # line_items may not be present on newly created sessions (need to expand)
        if hasattr(stripe_session, 'line_items') and stripe_session.line_items:
            if stripe_session.line_items.data:
                price_id = stripe_session.line_items.data[0].price.id

        customer_email = None
        if hasattr(stripe_session, 'customer_details') and stripe_session.customer_details:
            customer_email = stripe_session.customer_details.email
        elif hasattr(stripe_session, 'customer_email') and stripe_session.customer_email:
            customer_email = stripe_session.customer_email

        return CheckoutSession(
            id=stripe_session.id,
            url=stripe_session.url or "",
            customer_email=customer_email,
            customer_id=stripe_session.customer if hasattr(stripe_session, 'customer') else None,
            price_id=price_id,
            metadata=dict(stripe_session.metadata or {}) if hasattr(stripe_session, 'metadata') else {},
            status=stripe_session.status if hasattr(stripe_session, 'status') else None,
            payment_status=stripe_session.payment_status if hasattr(stripe_session, 'payment_status') else None,
        )

    def _convert_stripe_price(self, stripe_price: Any) -> Price:
        """Convert Stripe price object to Price model."""
        return Price(
            id=stripe_price.id,
            product_id=stripe_price.product,
            unit_amount=stripe_price.unit_amount or 0,
            currency=stripe_price.currency,
            recurring_interval=(
                stripe_price.recurring.interval if stripe_price.recurring else None
            ),
            active=stripe_price.active,
        )

    async def _run_in_executor(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous Stripe API call in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    # Customer operations

    async def create_customer(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Customer:
        """Create a new Stripe customer."""
        try:
            logger.info("creating_stripe_customer", email=email, name=name)

            customer_data: dict[str, Any] = {
                "email": email,
                "metadata": metadata or {},
            }
            if name:
                customer_data["name"] = name

            stripe_customer = await self._run_in_executor(
                stripe.Customer.create, **customer_data
            )

            customer = self._convert_stripe_customer(stripe_customer)
            logger.info("stripe_customer_created", customer_id=customer.id, email=email)
            return customer

        except stripe.error.StripeError as e:
            logger.error("stripe_customer_create_failed", email=email, error=str(e))
            raise StripeCustomerError(
                f"Failed to create Stripe customer: {str(e)}",
                details={"email": email},
                original_error=e,
            )

    async def get_customer(self, customer_id: str) -> Customer | None:
        """Get a customer by ID."""
        try:
            logger.debug("fetching_stripe_customer", customer_id=customer_id)

            stripe_customer = await self._run_in_executor(
                stripe.Customer.retrieve, customer_id
            )

            if stripe_customer.deleted:
                return None

            return self._convert_stripe_customer(stripe_customer)

        except stripe.error.InvalidRequestError:
            logger.warning("stripe_customer_not_found", customer_id=customer_id)
            return None
        except stripe.error.StripeError as e:
            logger.error(
                "stripe_customer_fetch_failed", customer_id=customer_id, error=str(e)
            )
            raise StripeCustomerError(
                f"Failed to fetch Stripe customer: {str(e)}",
                details={"customer_id": customer_id},
                original_error=e,
            )

    async def get_customer_by_email(self, email: str) -> Customer | None:
        """Get a customer by email."""
        try:
            logger.debug("searching_stripe_customer_by_email", email=email)

            result = await self._run_in_executor(
                stripe.Customer.list,
                email=email,
                limit=1,
            )

            if result.data:
                return self._convert_stripe_customer(result.data[0])

            return None

        except stripe.error.StripeError as e:
            logger.error("stripe_customer_search_failed", email=email, error=str(e))
            raise StripeCustomerError(
                f"Failed to search Stripe customer: {str(e)}",
                details={"email": email},
                original_error=e,
            )

    # Checkout operations

    async def create_checkout_session(
        self,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        """Create a Stripe Checkout session."""
        try:
            logger.info(
                "creating_checkout_session",
                price_id=price_id,
                customer_email=customer_email,
            )

            session_data = {
                "mode": "subscription",
                "customer_email": customer_email,
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            }

            stripe_session = await self._run_in_executor(
                stripe.checkout.Session.create, **session_data
            )

            session = self._convert_stripe_checkout_session(stripe_session)
            logger.info(
                "checkout_session_created",
                session_id=session.id,
                customer_email=customer_email,
            )
            return session

        except stripe.error.StripeError as e:
            logger.error("checkout_session_create_failed", price_id=price_id, error=str(e))
            raise StripePaymentError(
                f"Failed to create checkout session: {str(e)}",
                details={"price_id": price_id, "customer_email": customer_email},
                original_error=e,
            )

    async def get_checkout_session(self, session_id: str) -> CheckoutSession | None:
        """Get a checkout session by ID."""
        try:
            logger.debug("fetching_checkout_session", session_id=session_id)

            stripe_session = await self._run_in_executor(
                stripe.checkout.Session.retrieve,
                session_id,
                expand=["line_items"],
            )

            return self._convert_stripe_checkout_session(stripe_session)

        except stripe.error.InvalidRequestError:
            logger.warning("checkout_session_not_found", session_id=session_id)
            return None
        except stripe.error.StripeError as e:
            logger.error(
                "checkout_session_fetch_failed", session_id=session_id, error=str(e)
            )
            raise StripePaymentError(
                f"Failed to fetch checkout session: {str(e)}",
                details={"session_id": session_id},
                original_error=e,
            )

    # Subscription operations

    async def get_subscription(self, subscription_id: str) -> Subscription | None:
        """Get a subscription by ID."""
        try:
            logger.debug("fetching_subscription", subscription_id=subscription_id)

            stripe_sub = await self._run_in_executor(
                stripe.Subscription.retrieve, subscription_id
            )

            return self._convert_stripe_subscription(stripe_sub)

        except stripe.error.InvalidRequestError:
            logger.warning("subscription_not_found", subscription_id=subscription_id)
            return None
        except stripe.error.StripeError as e:
            logger.error(
                "subscription_fetch_failed", subscription_id=subscription_id, error=str(e)
            )
            raise StripeSubscriptionError(
                f"Failed to fetch subscription: {str(e)}",
                details={"subscription_id": subscription_id},
                original_error=e,
            )

    async def list_customer_subscriptions(self, customer_id: str) -> list[Subscription]:
        """List all subscriptions for a customer."""
        try:
            logger.debug("listing_customer_subscriptions", customer_id=customer_id)

            result = await self._run_in_executor(
                stripe.Subscription.list,
                customer=customer_id,
                limit=100,
            )

            subscriptions = [
                self._convert_stripe_subscription(sub) for sub in result.data
            ]
            logger.debug(
                "customer_subscriptions_listed",
                customer_id=customer_id,
                count=len(subscriptions),
            )
            return subscriptions

        except stripe.error.StripeError as e:
            logger.error(
                "list_subscriptions_failed", customer_id=customer_id, error=str(e)
            )
            raise StripeSubscriptionError(
                f"Failed to list subscriptions: {str(e)}",
                details={"customer_id": customer_id},
                original_error=e,
            )

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str] | None = None,
    ) -> Subscription:
        """Create a subscription directly (without checkout session)."""
        try:
            logger.info(
                "creating_subscription",
                customer_id=customer_id,
                price_id=price_id,
            )

            subscription_data: dict[str, Any] = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "metadata": metadata or {},
            }

            stripe_sub = await self._run_in_executor(
                stripe.Subscription.create, **subscription_data
            )

            subscription = self._convert_stripe_subscription(stripe_sub)
            logger.info(
                "subscription_created",
                subscription_id=subscription.id,
                customer_id=customer_id,
            )
            return subscription

        except stripe.error.StripeError as e:
            logger.error(
                "subscription_create_failed",
                customer_id=customer_id,
                price_id=price_id,
                error=str(e),
            )
            raise StripeSubscriptionError(
                f"Failed to create subscription: {str(e)}",
                details={"customer_id": customer_id, "price_id": price_id},
                original_error=e,
            )

    async def cancel_subscription(
        self, subscription_id: str, at_period_end: bool = True
    ) -> Subscription:
        """Cancel a subscription."""
        try:
            logger.info(
                "canceling_subscription",
                subscription_id=subscription_id,
                at_period_end=at_period_end,
            )

            if at_period_end:
                stripe_sub = await self._run_in_executor(
                    stripe.Subscription.modify,
                    subscription_id,
                    cancel_at_period_end=True,
                )
            else:
                stripe_sub = await self._run_in_executor(
                    stripe.Subscription.cancel,
                    subscription_id,
                )

            subscription = self._convert_stripe_subscription(stripe_sub)
            logger.info("subscription_canceled", subscription_id=subscription_id)
            return subscription

        except stripe.error.StripeError as e:
            logger.error(
                "subscription_cancel_failed", subscription_id=subscription_id, error=str(e)
            )
            raise StripeSubscriptionError(
                f"Failed to cancel subscription: {str(e)}",
                details={"subscription_id": subscription_id},
                original_error=e,
            )

    # Webhook operations

    def verify_webhook_signature(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify webhook signature and parse event."""
        if not self.config.webhook_secret:
            raise StripeWebhookError(
                "Webhook secret not configured",
                details={"has_secret": False},
            )

        try:
            logger.debug("verifying_webhook_signature")

            event = stripe.Webhook.construct_event(
                payload, signature, self.config.webhook_secret
            )

            webhook_event = WebhookEvent(
                id=event["id"],
                type=event["type"],
                data=event["data"],
                created=datetime.fromtimestamp(event["created"]),
                livemode=event.get("livemode", False),
            )

            logger.info(
                "webhook_signature_verified",
                event_type=webhook_event.type,
                event_id=webhook_event.id,
            )
            return webhook_event

        except ValueError as e:
            logger.error("webhook_payload_invalid", error=str(e))
            raise StripeWebhookError(
                "Invalid webhook payload",
                original_error=e,
            )
        except stripe.error.SignatureVerificationError as e:
            logger.error("webhook_signature_invalid", error=str(e))
            raise StripeWebhookError(
                "Invalid webhook signature",
                original_error=e,
            )

    # Price operations

    async def get_price(self, price_id: str) -> Price | None:
        """Get a price by ID."""
        try:
            logger.debug("fetching_price", price_id=price_id)

            stripe_price = await self._run_in_executor(stripe.Price.retrieve, price_id)

            return self._convert_stripe_price(stripe_price)

        except stripe.error.InvalidRequestError:
            logger.warning("price_not_found", price_id=price_id)
            return None
        except stripe.error.StripeError as e:
            logger.error("price_fetch_failed", price_id=price_id, error=str(e))
            raise StripeError(
                f"Failed to fetch price: {str(e)}",
                details={"price_id": price_id},
                original_error=e,
            )

    async def list_prices(self, product_id: str | None = None) -> list[Price]:
        """List all active prices, optionally filtered by product."""
        try:
            logger.debug("listing_prices", product_id=product_id)

            list_params: dict[str, Any] = {"active": True, "limit": 100}
            if product_id:
                list_params["product"] = product_id

            result = await self._run_in_executor(stripe.Price.list, **list_params)

            prices = [self._convert_stripe_price(price) for price in result.data]
            logger.debug("prices_listed", count=len(prices))
            return prices

        except stripe.error.StripeError as e:
            logger.error("list_prices_failed", error=str(e))
            raise StripeError(
                f"Failed to list prices: {str(e)}",
                original_error=e,
            )

    # Billing portal

    async def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> str:
        """Create a billing portal session. Returns the portal URL."""
        try:
            logger.info("creating_billing_portal_session", customer_id=customer_id)

            session = await self._run_in_executor(
                stripe.billing_portal.Session.create,
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(
                "billing_portal_session_created",
                customer_id=customer_id,
                session_id=session.id,
            )
            return session.url

        except stripe.error.StripeError as e:
            logger.error(
                "billing_portal_create_failed", customer_id=customer_id, error=str(e)
            )
            raise StripeError(
                f"Failed to create billing portal session: {str(e)}",
                details={"customer_id": customer_id},
                original_error=e,
            )

    # Health check

    async def health_check(self) -> bool:
        """Check if the Stripe API is accessible."""
        try:
            logger.debug("checking_stripe_health")

            await self._run_in_executor(stripe.Customer.list, limit=1)

            logger.info("stripe_health_check_passed")
            return True

        except Exception as e:
            logger.error("stripe_health_check_failed", error=str(e))
            return False
