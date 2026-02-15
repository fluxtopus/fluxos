# Mimic - Notification Service & Webhook Gateway

Unified message gateway for this monorepo (outbound notifications + inbound webhooks).

## Features

### Egress (Outbound Notifications)
- Email delivery via Resend/Postmark
- Notification templates
- Delivery tracking
- BYOK (Bring Your Own Keys) support

### Ingress (Webhook Gateway)
- Centralized webhook ingestion for Stripe and Resend
- Signature verification (Stripe)
- Event logging and audit trail
- Async event routing via Celery
- Idempotent processing (duplicate prevention)

## Quick Start

```bash
# Start all services (from monorepo root)
docker compose up -d --build

# Access services
# API: http://localhost:8006
# API Docs: http://localhost:8006/docs
```

Mimic initializes its database schema on startup. The webhook worker runs as the `mimic-worker` service.

## Webhook Gateway Endpoints

### Stripe Webhooks

```bash
# Production (with signature verification)
POST /api/v1/gateway/webhooks/stripe
Headers: Stripe-Signature: t=...,v1=...

# Development (no signature, DEV mode only)
POST /api/v1/gateway/webhooks/stripe/test
```

### Resend Webhooks

```bash
# Email delivery events
POST /api/v1/gateway/webhooks/resend
Headers: svix-signature: ...
```

### Admin Endpoints

```bash
# List recent webhook events
GET /api/v1/gateway/webhooks/events?provider=stripe&status=delivered&limit=50

# Get event details with delivery tracking
GET /api/v1/gateway/webhooks/events/{event_id}
```

## Configuration

### Environment Variables

```bash
# Webhook Gateway
STRIPE_SECRET_KEY=sk_test_...           # Stripe API key
STRIPE_WEBHOOK_SECRET=whsec_...         # Stripe webhook signing secret
RESEND_WEBHOOK_SECRET=                  # Optional Svix secret

# Internal Service URLs
INKPASS_INTERNAL_URL=http://inkpass:8000
MIMIC_SERVICE_API_KEY=sk_mimic_service_dev

# Celery
CELERY_BROKER_URL=redis://redis:6379/6
CELERY_RESULT_BACKEND=redis://redis:6379/6

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/aios_mimic

# Email (existing)
EMAIL_PROVIDER=dev
DEV_SMTP_HOST=mailpit
DEV_SMTP_PORT=1025
```

## Database Models

### WebhookEvent
Stores all incoming webhook events for audit and idempotency.

```python
id: UUID
provider: str          # stripe, resend, etc.
event_type: str        # checkout.session.completed
event_id: str          # Provider's unique event ID
payload: JSON          # Raw webhook payload
signature: str         # Signature for audit
status: str            # received, delivered, failed
processed_at: datetime
error_message: str
retry_count: int
```

### WebhookDelivery
Tracks delivery of events to downstream services.

```python
id: UUID
event_id: UUID         # FK to WebhookEvent
target_service: str    # inkpass, tentackl, custom, etc.
task_name: str         # Celery task name
celery_task_id: str
status: str            # pending, dispatched, success, failed
result: JSON
attempt_count: int
```

## Celery Tasks

| Task | Purpose |
|------|---------|
| `mimic.tasks.route_to_inkpass_subscription_created` | Handle new subscriptions |
| `mimic.tasks.route_to_inkpass_subscription_deleted` | Handle cancellations |
| `mimic.tasks.route_to_inkpass_subscription_updated` | Handle updates |
| `mimic.tasks.route_to_inkpass_invoice_event` | Handle invoice events |
| `mimic.tasks.handle_email_delivery_event` | Track email delivery |

## Development

### Running Tests

```bash
docker compose exec mimic pytest tests/ -v
```

### Running the Celery Worker

```bash
# In foreground (for debugging)
docker compose exec mimic celery -A src.core.celery_app worker --loglevel=debug

# In background
docker compose exec -d mimic celery -A src.core.celery_app worker --loglevel=info
```

### Testing Webhooks Locally

```bash
# Use the test endpoint (DEV mode only)
curl -X POST http://localhost:8006/api/v1/gateway/webhooks/stripe/test \
  -H "Content-Type: application/json" \
  -d '{
    "type": "checkout.session.completed",
    "data": {
      "object": {
        "id": "cs_test_123",
        "customer": "cus_test_123",
        "customer_email": "test@example.com",
        "subscription": "sub_test_123",
        "metadata": {"product_type": "tentackl_solo"}
      }
    }
  }'
```

### Viewing Webhook Events

```bash
# List recent events
curl http://localhost:8006/api/v1/gateway/webhooks/events

# Get specific event
curl http://localhost:8006/api/v1/gateway/webhooks/events/{event_id}
```

## File Structure

```
apps/mimic/
├── src/
│   ├── api/
│   │   └── routes/
│   │       ├── gateway_webhooks.py  # Webhook ingestion
│   │       ├── billing.py           # Existing billing routes
│   │       └── notifications.py     # Existing notification routes
│   ├── core/
│   │   ├── celery_app.py            # Celery configuration
│   │   └── tasks.py                 # Event routing tasks
│   ├── database/
│   │   └── models.py                # WebhookEvent, WebhookDelivery
│   └── config.py                    # Settings
├── alembic/
│   └── versions/
│       ├── 001_initial.py
│       └── 002_webhook_gateway.py   # Webhook tables
├── tests/
└── requirements.txt
```

## Production Deployment

### Stripe Webhook Configuration

1. Go to Stripe Dashboard > Developers > Webhooks
2. Add endpoint: `https://mimic.fluxtopus.com/api/v1/gateway/webhooks/stripe`
3. Select events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
4. Copy the signing secret to `STRIPE_WEBHOOK_SECRET`

## See Also

- `docs/architecture/Architecture-Guardrails.md`
