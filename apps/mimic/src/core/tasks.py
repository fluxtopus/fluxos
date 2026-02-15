"""
Celery tasks for webhook event routing.

Routes webhook events from Mimic gateway to downstream services:
- InkPass: Billing and subscription state
- Mimic: Email delivery tracking
- Tentackl/Custom: Integration event routing (INT-012)
"""

import httpx
import structlog
from datetime import datetime
from sqlalchemy.orm import Session

from src.core.celery_app import app
from src.config import settings
from src.database.database import SessionLocal
from src.database.models import WebhookDelivery, IntegrationWebhookDelivery

logger = structlog.get_logger(__name__)


def get_db_session() -> Session:
    """Get a database session for task execution."""
    return SessionLocal()


def update_delivery_status(db: Session, delivery_id: str, status: str, result: dict = None):
    """Update delivery record with result."""
    delivery = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
    if delivery:
        delivery.status = status
        delivery.result = result
        delivery.last_attempt_at = datetime.utcnow()
        db.commit()


# ============================================================================
# InkPass Tasks (Billing/Subscription)
# ============================================================================


@app.task(bind=True, name='mimic.tasks.route_to_inkpass_subscription_created')
def route_to_inkpass_subscription_created(
    self,
    event_type: str,
    event_data: dict,
    webhook_event_id: str,
    delivery_id: str,
):
    """Route checkout.session.completed to InkPass for subscription creation."""
    db = get_db_session()
    try:
        logger.info(
            "routing_to_inkpass_subscription_created",
            event_type=event_type,
            webhook_event_id=webhook_event_id,
        )

        session_data = event_data.get("object", {})
        customer_email = session_data.get("customer_details", {}).get("email")
        if not customer_email:
            customer_email = session_data.get("customer_email")

        stripe_customer_id = session_data.get("customer")
        stripe_subscription_id = session_data.get("subscription")
        metadata = session_data.get("metadata", {})

        payload = {
            "event_type": "subscription.created",
            "customer_email": customer_email,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "metadata": metadata,
        }

        # Call InkPass internal API
        with httpx.Client(timeout=30.0) as client:
            headers = {}
            if settings.MIMIC_SERVICE_API_KEY:
                headers["X-Service-API-Key"] = settings.MIMIC_SERVICE_API_KEY

            response = client.post(
                f"{settings.INKPASS_INTERNAL_URL}/api/v1/internal/billing/subscription-event",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        update_delivery_status(db, delivery_id, "success", {"response": response.json()})
        logger.info("inkpass_subscription_created_success", delivery_id=delivery_id)

    except Exception as e:
        logger.error(
            "inkpass_subscription_created_failed",
            delivery_id=delivery_id,
            error=str(e),
        )
        update_delivery_status(db, delivery_id, "failed", {"error": str(e)})
        raise
    finally:
        db.close()


@app.task(bind=True, name='mimic.tasks.route_to_inkpass_subscription_deleted')
def route_to_inkpass_subscription_deleted(
    self,
    event_type: str,
    event_data: dict,
    webhook_event_id: str,
    delivery_id: str,
):
    """Route customer.subscription.deleted to InkPass."""
    db = get_db_session()
    try:
        logger.info(
            "routing_to_inkpass_subscription_deleted",
            event_type=event_type,
            webhook_event_id=webhook_event_id,
        )

        subscription_data = event_data.get("object", {})
        stripe_customer_id = subscription_data.get("customer")
        stripe_subscription_id = subscription_data.get("id")

        payload = {
            "event_type": "subscription.deleted",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "canceled_at": subscription_data.get("canceled_at"),
        }

        with httpx.Client(timeout=30.0) as client:
            headers = {}
            if settings.MIMIC_SERVICE_API_KEY:
                headers["X-Service-API-Key"] = settings.MIMIC_SERVICE_API_KEY

            response = client.post(
                f"{settings.INKPASS_INTERNAL_URL}/api/v1/internal/billing/subscription-event",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        update_delivery_status(db, delivery_id, "success", {"response": response.json()})
        logger.info("inkpass_subscription_deleted_success", delivery_id=delivery_id)

    except Exception as e:
        logger.error(
            "inkpass_subscription_deleted_failed",
            delivery_id=delivery_id,
            error=str(e),
        )
        update_delivery_status(db, delivery_id, "failed", {"error": str(e)})
        raise
    finally:
        db.close()


@app.task(bind=True, name='mimic.tasks.route_to_inkpass_subscription_updated')
def route_to_inkpass_subscription_updated(
    self,
    event_type: str,
    event_data: dict,
    webhook_event_id: str,
    delivery_id: str,
):
    """Route customer.subscription.updated to InkPass."""
    db = get_db_session()
    try:
        logger.info(
            "routing_to_inkpass_subscription_updated",
            event_type=event_type,
            webhook_event_id=webhook_event_id,
        )

        subscription_data = event_data.get("object", {})
        stripe_customer_id = subscription_data.get("customer")
        stripe_subscription_id = subscription_data.get("id")
        subscription_status = subscription_data.get("status")

        payload = {
            "event_type": "subscription.updated",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "subscription_status": subscription_status,
        }

        with httpx.Client(timeout=30.0) as client:
            headers = {}
            if settings.MIMIC_SERVICE_API_KEY:
                headers["X-Service-API-Key"] = settings.MIMIC_SERVICE_API_KEY

            response = client.post(
                f"{settings.INKPASS_INTERNAL_URL}/api/v1/internal/billing/subscription-event",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        update_delivery_status(db, delivery_id, "success", {"response": response.json()})
        logger.info("inkpass_subscription_updated_success", delivery_id=delivery_id)

    except Exception as e:
        logger.error(
            "inkpass_subscription_updated_failed",
            delivery_id=delivery_id,
            error=str(e),
        )
        update_delivery_status(db, delivery_id, "failed", {"error": str(e)})
        raise
    finally:
        db.close()


@app.task(bind=True, name='mimic.tasks.route_to_inkpass_invoice_event')
def route_to_inkpass_invoice_event(
    self,
    event_type: str,
    event_data: dict,
    webhook_event_id: str,
    delivery_id: str,
):
    """Route invoice events to InkPass."""
    db = get_db_session()
    try:
        logger.info(
            "routing_to_inkpass_invoice_event",
            event_type=event_type,
            webhook_event_id=webhook_event_id,
        )

        invoice_data = event_data.get("object", {})
        stripe_customer_id = invoice_data.get("customer")
        stripe_subscription_id = invoice_data.get("subscription")

        payload = {
            "event_type": f"invoice.{event_type.split('.')[-1]}",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "amount_due": invoice_data.get("amount_due"),
            "amount_paid": invoice_data.get("amount_paid"),
            "status": invoice_data.get("status"),
        }

        with httpx.Client(timeout=30.0) as client:
            headers = {}
            if settings.MIMIC_SERVICE_API_KEY:
                headers["X-Service-API-Key"] = settings.MIMIC_SERVICE_API_KEY

            response = client.post(
                f"{settings.INKPASS_INTERNAL_URL}/api/v1/internal/billing/invoice-event",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

        update_delivery_status(db, delivery_id, "success", {"response": response.json()})
        logger.info("inkpass_invoice_event_success", delivery_id=delivery_id)

    except Exception as e:
        logger.error(
            "inkpass_invoice_event_failed",
            delivery_id=delivery_id,
            error=str(e),
        )
        update_delivery_status(db, delivery_id, "failed", {"error": str(e)})
        raise
    finally:
        db.close()


# ============================================================================
# Mimic Internal Tasks (Email Delivery)
# ============================================================================


@app.task(bind=True, name='mimic.tasks.handle_email_delivery_event')
def handle_email_delivery_event(
    self,
    event_type: str,
    payload: dict,
    webhook_event_id: str,
    delivery_id: str,
):
    """Handle email delivery events from Resend internally."""
    db = get_db_session()
    try:
        logger.info(
            "handling_email_delivery_event",
            event_type=event_type,
            webhook_event_id=webhook_event_id,
        )

        email_data = payload.get("data", {})
        email_id = email_data.get("email_id")

        # Update delivery log based on event type
        from src.database.models import DeliveryLog

        # Find delivery log by provider message ID (stored when email was sent)
        # This is a simplified approach - in production you'd store the provider ID
        # when sending and look it up here

        if event_type == "email.delivered":
            status = "delivered"
        elif event_type == "email.bounced":
            status = "bounced"
        elif event_type == "email.complained":
            status = "complained"
        elif event_type == "email.opened":
            # Don't change status for opens, just log it
            logger.info("email_opened", email_id=email_id)
            update_delivery_status(db, delivery_id, "success", {"email_id": email_id, "event": "opened"})
            return

        # TODO: Look up DeliveryLog by email_id and update status
        # For now, just log the event
        logger.info(
            "email_delivery_status_update",
            email_id=email_id,
            status=status,
        )

        update_delivery_status(db, delivery_id, "success", {"email_id": email_id, "status": status})
        logger.info("email_delivery_event_handled", delivery_id=delivery_id)

    except Exception as e:
        logger.error(
            "email_delivery_event_failed",
            delivery_id=delivery_id,
            error=str(e),
        )
        update_delivery_status(db, delivery_id, "failed", {"error": str(e)})
        raise
    finally:
        db.close()


# ============================================================================
# Integration Event Routing (INT-012)
# ============================================================================


def _update_integration_delivery(
    db: Session,
    delivery_id: str,
    delivery_status: str,
    response_status_code: int = None,
    response_body: dict = None,
    error_message: str = None,
):
    """Update an IntegrationWebhookDelivery record."""
    delivery = (
        db.query(IntegrationWebhookDelivery)
        .filter(IntegrationWebhookDelivery.id == delivery_id)
        .first()
    )
    if delivery:
        delivery.status = delivery_status
        delivery.response_status_code = response_status_code
        delivery.response_body = response_body
        delivery.error_message = error_message
        delivery.last_attempt_at = datetime.utcnow()
        delivery.attempt_count = (delivery.attempt_count or 0) + 1
        db.commit()


@app.task(
    bind=True,
    name='mimic.tasks.route_integration_event',
    max_retries=3,
    default_retry_delay=30,
)
def route_integration_event(
    self,
    event_id: str,
    delivery_id: str,
    destination_service: str,
    destination_config: dict,
    transformed_payload: dict,
    integration_id: str,
    organization_id: str,
):
    """Route an integration webhook event to its destination service.

    Supports routing to:
    - tentackl: POST to Tentackl's internal event receiver
    - custom: POST to a user-configured webhook URL
    """
    db = get_db_session()
    try:
        logger.info(
            "routing_integration_event",
            event_id=event_id,
            delivery_id=delivery_id,
            destination_service=destination_service,
            integration_id=integration_id,
        )

        payload = {
            "event_id": event_id,
            "integration_id": integration_id,
            "organization_id": organization_id,
            "event_type": transformed_payload.get("event_type", "webhook"),
            "data": transformed_payload,
        }

        # Include Discord interaction metadata if present in the raw data
        raw_data = transformed_payload.get("data", {})
        if isinstance(raw_data, dict):
            if raw_data.get("application_id"):
                payload["application_id"] = raw_data["application_id"]
            if raw_data.get("token"):
                payload["interaction_token"] = raw_data["token"]

        headers = {}
        if settings.MIMIC_SERVICE_API_KEY:
            headers["X-Internal-Key"] = settings.MIMIC_SERVICE_API_KEY

        if destination_service == "tentackl":
            url = f"{settings.TENTACKL_INTERNAL_URL}/api/internal/integration-events"
        elif destination_service == "custom":
            url = destination_config.get("webhook_url")
            if not url:
                raise ValueError("Custom destination requires webhook_url in destination_config")
            # For custom destinations, don't send internal key
            headers.pop("X-Internal-Key", None)
            # Add any custom headers from config
            custom_headers = destination_config.get("headers", {})
            if isinstance(custom_headers, dict):
                headers.update(custom_headers)
        else:
            raise ValueError(f"Unknown destination_service: {destination_service}")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        response_body = None
        try:
            response_body = response.json()
        except Exception:
            response_body = {"raw": response.text[:1000]}

        _update_integration_delivery(
            db,
            delivery_id,
            delivery_status="success",
            response_status_code=response.status_code,
            response_body=response_body,
        )
        logger.info(
            "integration_event_routed",
            event_id=event_id,
            delivery_id=delivery_id,
            destination_service=destination_service,
        )

    except Exception as e:
        logger.error(
            "integration_event_routing_failed",
            event_id=event_id,
            delivery_id=delivery_id,
            destination_service=destination_service,
            error=str(e),
            retry_count=self.request.retries,
        )
        _update_integration_delivery(
            db,
            delivery_id,
            delivery_status="failed",
            error_message=str(e),
        )
        # Retry with exponential backoff
        try:
            self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                "integration_event_routing_max_retries",
                event_id=event_id,
                delivery_id=delivery_id,
            )
    finally:
        db.close()
