"""
Stripe data models.

Generic models without app-specific product types.
Consumers map price IDs to their own product types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SubscriptionStatus(str, Enum):
    """Standard Stripe subscription statuses."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAUSED = "paused"


@dataclass
class Customer:
    """Stripe customer."""

    id: str
    email: str
    name: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class Subscription:
    """Stripe subscription."""

    id: str
    customer_id: str
    status: SubscriptionStatus
    price_id: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    canceled_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class CheckoutSession:
    """Stripe Checkout session."""

    id: str
    url: str
    customer_email: str | None = None
    customer_id: str | None = None
    price_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    status: str = "open"
    payment_status: str = "unpaid"


@dataclass
class WebhookEvent:
    """Stripe webhook event."""

    id: str
    type: str
    data: dict[str, Any]
    created: datetime
    livemode: bool = False


@dataclass
class Price:
    """Stripe price."""

    id: str
    product_id: str
    unit_amount: int  # in cents
    currency: str = "usd"
    recurring_interval: str | None = None  # "month", "year"
    active: bool = True


@dataclass
class BillingPortalSession:
    """Stripe billing portal session."""

    id: str
    url: str
    customer_id: str
    return_url: str
