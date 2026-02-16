"""
Webhook Gateway Routes.

Handles inbound webhooks from external services:
- Stripe: Payment and subscription events
- Resend: Email delivery events

All webhooks are logged for audit, then routed to appropriate services via Celery.
"""

from datetime import datetime
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.database.database import get_db
from src.database.models import WebhookEvent, WebhookDelivery
from src.api.auth import require_permission, AuthContext

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/gateway/webhooks", tags=["webhook-gateway"])


# ============================================================================
# Stripe Webhooks
# ============================================================================


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Receive Stripe webhooks",
    description="Handles payment and subscription events from Stripe",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """
    Handle Stripe webhook events.

    Verifies signature, logs event, and routes to downstream services.
    """
    payload = await request.body()
    db: Session = next(get_db())

    # Verify signature
    if not stripe_signature:
        logger.warning("stripe_webhook_missing_signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MissingSignature", "message": "Stripe-Signature header required"},
        )

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("stripe_webhook_secret_not_configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "ConfigurationError", "message": "Stripe webhook secret not configured"},
        )

    try:
        from fluxos_stripe import StripeClient, StripeConfig, StripeWebhookError

        config = StripeConfig(
            api_key=settings.STRIPE_SECRET_KEY or "",
            webhook_secret=settings.STRIPE_WEBHOOK_SECRET,
        )
        client = StripeClient(config)
        event = client.verify_webhook_signature(payload, stripe_signature)

    except StripeWebhookError as e:
        logger.error("stripe_webhook_signature_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "InvalidSignature", "message": "Invalid webhook signature"},
        )

    # Log the event for audit and idempotency
    try:
        webhook_event = WebhookEvent(
            provider="stripe",
            event_type=event.type,
            event_id=event.id,
            payload=event.data,
            signature=stripe_signature[:100] if stripe_signature else None,  # Truncate for storage
            status="received",
        )
        db.add(webhook_event)
        db.commit()
        db.refresh(webhook_event)
    except IntegrityError:
        db.rollback()
        # Duplicate event - already processed
        logger.info("stripe_webhook_duplicate", event_id=event.id, event_type=event.type)
        return {"received": True, "event_type": event.type, "status": "duplicate"}

    logger.info(
        "stripe_webhook_received",
        event_id=event.id,
        event_type=event.type,
        webhook_event_id=webhook_event.id,
    )

    # Route to appropriate Celery tasks
    try:
        await _route_stripe_event(db, webhook_event, event)
        webhook_event.status = "delivered"
        webhook_event.processed_at = datetime.utcnow()
    except Exception as e:
        logger.error(
            "stripe_webhook_routing_failed",
            event_id=event.id,
            error=str(e),
        )
        webhook_event.status = "failed"
        webhook_event.error_message = str(e)

    db.commit()
    return {"received": True, "event_type": event.type, "event_id": webhook_event.id}


async def _route_stripe_event(db: Session, webhook_event: WebhookEvent, event):
    """Route Stripe event to appropriate services via Celery."""
    from src.core.celery_app import app as celery_app

    event_type = event.type
    event_data = event.data

    # Determine which services need this event
    routes = []

    if event_type == "checkout.session.completed":
        # InkPass: Update subscription state
        routes.append(("inkpass", "mimic.tasks.route_to_inkpass_subscription_created"))

    elif event_type == "customer.subscription.deleted":
        # InkPass: Update subscription state
        routes.append(("inkpass", "mimic.tasks.route_to_inkpass_subscription_deleted"))

    elif event_type == "customer.subscription.updated":
        # InkPass: Update subscription state
        routes.append(("inkpass", "mimic.tasks.route_to_inkpass_subscription_updated"))

    elif event_type in ["invoice.payment_failed", "invoice.payment_succeeded"]:
        # InkPass: Update billing state
        routes.append(("inkpass", "mimic.tasks.route_to_inkpass_invoice_event"))

    else:
        logger.info("stripe_event_ignored", event_type=event_type)
        return

    # Create delivery records and dispatch Celery tasks
    for target_service, task_name in routes:
        delivery = WebhookDelivery(
            event_id=webhook_event.id,
            target_service=target_service,
            task_name=task_name,
            status="pending",
        )
        db.add(delivery)
        db.flush()

        # Dispatch Celery task
        task = celery_app.send_task(
            task_name,
            kwargs={
                "event_type": event_type,
                "event_data": event_data,
                "webhook_event_id": webhook_event.id,
                "delivery_id": delivery.id,
            },
        )

        delivery.celery_task_id = task.id
        delivery.status = "dispatched"
        delivery.attempt_count = 1
        delivery.last_attempt_at = datetime.utcnow()

        logger.info(
            "stripe_event_routed",
            target_service=target_service,
            task_name=task_name,
            celery_task_id=task.id,
        )


# ============================================================================
# Resend Webhooks (Email delivery status)
# ============================================================================


@router.post(
    "/resend",
    status_code=status.HTTP_200_OK,
    summary="Receive Resend webhooks",
    description="Handles email delivery events from Resend",
)
async def resend_webhook(
    request: Request,
    svix_id: Optional[str] = Header(None, alias="svix-id"),
    svix_timestamp: Optional[str] = Header(None, alias="svix-timestamp"),
    svix_signature: Optional[str] = Header(None, alias="svix-signature"),
):
    """
    Handle Resend webhook events.

    Resend uses Svix for webhook delivery with signature verification.
    """
    payload = await request.json()
    db: Session = next(get_db())

    # TODO: Implement Svix signature verification when RESEND_WEBHOOK_SECRET is set
    # For now, we'll accept the webhook without verification in dev mode
    if settings.RESEND_WEBHOOK_SECRET and svix_signature:
        # Verify signature using svix library
        # from svix.webhooks import Webhook
        # wh = Webhook(settings.RESEND_WEBHOOK_SECRET)
        # wh.verify(payload_bytes, headers)
        pass

    event_type = payload.get("type", "unknown")
    event_id = payload.get("data", {}).get("email_id", str(datetime.utcnow().timestamp()))

    # Log the event
    try:
        webhook_event = WebhookEvent(
            provider="resend",
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            signature=svix_signature[:100] if svix_signature else None,
            status="received",
        )
        db.add(webhook_event)
        db.commit()
        db.refresh(webhook_event)
    except IntegrityError:
        db.rollback()
        logger.info("resend_webhook_duplicate", event_id=event_id, event_type=event_type)
        return {"received": True, "event_type": event_type, "status": "duplicate"}

    logger.info(
        "resend_webhook_received",
        event_type=event_type,
        event_id=event_id,
        webhook_event_id=webhook_event.id,
    )

    # Route internally to Mimic for delivery tracking
    try:
        await _route_resend_event(db, webhook_event, payload)
        webhook_event.status = "delivered"
        webhook_event.processed_at = datetime.utcnow()
    except Exception as e:
        logger.error(
            "resend_webhook_routing_failed",
            event_id=event_id,
            error=str(e),
        )
        webhook_event.status = "failed"
        webhook_event.error_message = str(e)

    db.commit()
    return {"received": True, "event_type": event_type, "event_id": webhook_event.id}


async def _route_resend_event(db: Session, webhook_event: WebhookEvent, payload: dict):
    """Route Resend event to internal Mimic handler via Celery."""
    from src.core.celery_app import app as celery_app

    event_type = payload.get("type", "unknown")

    # Resend events handled internally by Mimic
    if event_type in ["email.delivered", "email.bounced", "email.complained", "email.opened"]:
        task_name = "mimic.tasks.handle_email_delivery_event"
    else:
        logger.info("resend_event_ignored", event_type=event_type)
        return

    delivery = WebhookDelivery(
        event_id=webhook_event.id,
        target_service="mimic",
        task_name=task_name,
        status="pending",
    )
    db.add(delivery)
    db.flush()

    task = celery_app.send_task(
        task_name,
        kwargs={
            "event_type": event_type,
            "payload": payload,
            "webhook_event_id": webhook_event.id,
            "delivery_id": delivery.id,
        },
    )

    delivery.celery_task_id = task.id
    delivery.status = "dispatched"
    delivery.attempt_count = 1
    delivery.last_attempt_at = datetime.utcnow()

    logger.info(
        "resend_event_routed",
        target_service="mimic",
        task_name=task_name,
        celery_task_id=task.id,
    )


# ============================================================================
# Admin Endpoints
# ============================================================================


# ============================================================================
# Test Endpoint (DEV ONLY)
# ============================================================================


@router.post(
    "/stripe/test",
    status_code=status.HTTP_200_OK,
    summary="Test Stripe webhook endpoint (DEV ONLY)",
    description="Process simulated Stripe events without signature verification",
    include_in_schema=False,
)
async def stripe_webhook_test(
    request: Request,
):
    """
    Test endpoint for simulating Stripe webhooks without signature verification.

    WARNING: Only for development/testing.
    """
    from src.config import settings as mimic_settings

    # Only allow in dev mode
    if mimic_settings.APP_ENV not in ["development", "test"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Forbidden", "message": "Test endpoint only available in dev mode"},
        )

    payload = await request.json()
    db: Session = next(get_db())

    event_type = payload.get("type")
    event_id = payload.get("data", {}).get("object", {}).get("id", str(datetime.utcnow().timestamp()))

    # Create a mock event object
    class MockEvent:
        def __init__(self, payload):
            self.id = f"evt_test_{event_id}"
            self.type = payload.get("type")
            self.data = payload.get("data", {})

    event = MockEvent(payload)

    # Log the event
    try:
        webhook_event = WebhookEvent(
            provider="stripe",
            event_type=event.type,
            event_id=event.id,
            payload=event.data,
            signature="test_signature",
            status="received",
        )
        db.add(webhook_event)
        db.commit()
        db.refresh(webhook_event)
    except IntegrityError:
        db.rollback()
        logger.info("stripe_test_webhook_duplicate", event_id=event.id)
        return {"received": True, "event_type": event.type, "status": "duplicate"}

    logger.info(
        "stripe_test_webhook_received",
        event_id=event.id,
        event_type=event.type,
        webhook_event_id=webhook_event.id,
    )

    # Route to Celery tasks
    try:
        await _route_stripe_event(db, webhook_event, event)
        webhook_event.status = "delivered"
        webhook_event.processed_at = datetime.utcnow()
    except Exception as e:
        logger.error(
            "stripe_test_webhook_routing_failed",
            event_id=event.id,
            error=str(e),
        )
        webhook_event.status = "failed"
        webhook_event.error_message = str(e)

    db.commit()
    return {"received": True, "event_type": event.type, "event_id": webhook_event.id}


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.get(
    "/events",
    summary="List webhook events",
    description="List recent webhook events for monitoring",
)
async def list_webhook_events(
    auth: Annotated[AuthContext, Depends(require_permission("gateway", "admin"))],
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """List recent webhook events."""
    db: Session = next(get_db())

    query = db.query(WebhookEvent)

    if provider:
        query = query.filter(WebhookEvent.provider == provider)
    if status:
        query = query.filter(WebhookEvent.status == status)

    events = query.order_by(WebhookEvent.created_at.desc()).limit(limit).all()

    return {
        "events": [
            {
                "id": e.id,
                "provider": e.provider,
                "event_type": e.event_type,
                "event_id": e.event_id,
                "status": e.status,
                "retry_count": e.retry_count,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
                "error_message": e.error_message,
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get(
    "/events/{event_id}",
    summary="Get webhook event details",
    description="Get details of a specific webhook event including deliveries",
)
async def get_webhook_event(
    event_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("gateway", "admin"))],
):
    """Get webhook event details with delivery tracking."""
    db: Session = next(get_db())

    event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NotFound", "message": "Webhook event not found"},
        )

    deliveries = db.query(WebhookDelivery).filter(WebhookDelivery.event_id == event_id).all()

    return {
        "event": {
            "id": event.id,
            "provider": event.provider,
            "event_type": event.event_type,
            "event_id": event.event_id,
            "payload": event.payload,
            "status": event.status,
            "retry_count": event.retry_count,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "processed_at": event.processed_at.isoformat() if event.processed_at else None,
            "error_message": event.error_message,
        },
        "deliveries": [
            {
                "id": d.id,
                "target_service": d.target_service,
                "task_name": d.task_name,
                "status": d.status,
                "celery_task_id": d.celery_task_id,
                "result": d.result,
                "attempt_count": d.attempt_count,
                "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
            }
            for d in deliveries
        ],
    }
