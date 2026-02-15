# aios-stripe

Shared Stripe integration package used by services in this repo.

## Installation

```bash
# For development (editable install)
pip install -e packages/aios-stripe

# Or add to requirements.txt
-e ./packages/aios-stripe
```

## Quick Start

```python
from aios_stripe import StripeClient, StripeConfig

# Create config
config = StripeConfig(
    api_key="sk_test_...",
    webhook_secret="whsec_...",  # Optional
)

# Create client
client = StripeClient(config)

# Create a customer
customer = await client.create_customer(
    email="user@example.com",
    name="John Doe",
    metadata={"organization_id": "org_123"},
)

# Create checkout session
session = await client.create_checkout_session(
    price_id="price_...",
    customer_email="user@example.com",
    success_url="https://example.com/success",
    cancel_url="https://example.com/cancel",
)
print(f"Checkout URL: {session.url}")

# Verify webhook
event = client.verify_webhook_signature(payload, signature)
print(f"Event type: {event.type}")
```

## Testing

### Unit Tests (no Stripe API key needed)

```bash
cd packages/aios-stripe
pip install -e ".[dev]"
pytest tests/unit -v
```

### E2E Tests (requires Stripe test mode API key)

```bash
export STRIPE_TEST_API_KEY=sk_test_...
export STRIPE_TEST_WEBHOOK_SECRET=whsec_...  # From stripe-cli
export STRIPE_TEST_PRICE_ID=price_...        # A test price ID

pytest tests/e2e -v -m e2e
```

### Using Mock Client for Tests

```python
from aios_stripe.mock import MockStripeClient, customer_factory

# Create mock client
mock_client = MockStripeClient()

# Pre-populate with test data
mock_client.add_customer(customer_factory(email="existing@test.com"))

# Use in tests
customer = await mock_client.create_customer(email="new@test.com")
assert customer.id.startswith("cus_")

# Simulate failures
mock_client.set_should_fail(True, "Simulated network error")
```

## API Reference

### StripeConfig

```python
StripeConfig(
    api_key: str,                    # Required - Stripe secret key
    webhook_secret: str | None,      # Optional - for webhook verification
    timeout: float = 30.0,           # API request timeout
    max_retries: int = 3,            # Max retry attempts
)
```

### StripeClient Methods

| Method | Description |
|--------|-------------|
| `create_customer(email, name?, metadata?)` | Create a Stripe customer |
| `get_customer(customer_id)` | Get customer by ID |
| `get_customer_by_email(email)` | Search customer by email |
| `create_checkout_session(...)` | Create checkout session |
| `get_checkout_session(session_id)` | Get checkout session |
| `get_subscription(subscription_id)` | Get subscription |
| `list_customer_subscriptions(customer_id)` | List customer subscriptions |
| `cancel_subscription(subscription_id, at_period_end?)` | Cancel subscription |
| `verify_webhook_signature(payload, signature)` | Verify webhook |
| `get_price(price_id)` | Get price by ID |
| `list_prices(product_id?)` | List active prices |
| `create_billing_portal_session(customer_id, return_url)` | Create billing portal |
| `health_check()` | Check Stripe API connectivity |

### Exceptions

```python
from aios_stripe import (
    StripeError,           # Base exception
    StripeConfigError,     # Invalid configuration
    StripeCustomerError,   # Customer operations
    StripePaymentError,    # Payment/checkout operations
    StripeSubscriptionError,  # Subscription operations
    StripeWebhookError,    # Webhook verification
    StripeConnectionError, # API connectivity
)
```

## License

MIT. See the repository root `LICENSE`.
