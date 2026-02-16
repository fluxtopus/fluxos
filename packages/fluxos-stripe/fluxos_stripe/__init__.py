"""
    fluxos-stripe - Shared Stripe integration package.

    A standalone, reusable Stripe integration for services in this repo.

Example usage:
    from fluxos_stripe import StripeClient, StripeConfig

    config = StripeConfig(
        api_key="sk_test_...",
        webhook_secret="whsec_...",
    )
    client = StripeClient(config)

    # Create a customer
    customer = await client.create_customer(
        email="user@example.com",
        name="John Doe",
    )

    # Create checkout session
    session = await client.create_checkout_session(
        price_id="price_...",
        customer_email="user@example.com",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )
"""

from .client import StripeClient, StripeClientInterface
from .config import StripeConfig
from .exceptions import (
    StripeConfigError,
    StripeConnectionError,
    StripeCustomerError,
    StripeError,
    StripePaymentError,
    StripeSubscriptionError,
    StripeWebhookError,
)
from .models import (
    BillingPortalSession,
    CheckoutSession,
    Customer,
    Price,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from .version import __version__

__all__ = [
    # Client
    "StripeClient",
    "StripeClientInterface",
    # Config
    "StripeConfig",
    # Exceptions
    "StripeError",
    "StripeConfigError",
    "StripeConnectionError",
    "StripeCustomerError",
    "StripePaymentError",
    "StripeSubscriptionError",
    "StripeWebhookError",
    # Models
    "Customer",
    "Subscription",
    "SubscriptionStatus",
    "CheckoutSession",
    "WebhookEvent",
    "Price",
    "BillingPortalSession",
    # Version
    "__version__",
]
