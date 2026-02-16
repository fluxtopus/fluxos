"""
Billing API Routes.

Endpoints for Stripe billing configuration and operations.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fluxos_stripe import StripeWebhookError

from src.database.database import get_db
from src.middleware.auth_middleware import AuthContext, get_auth_context, require_permission
from src.services.billing_service import BillingService

logger = structlog.get_logger(__name__)

router = APIRouter()


# === Request/Response Models ===


class ConfigureBillingRequest(BaseModel):
    """Request to configure Stripe billing for an organization."""

    stripe_api_key: str = Field(..., description="Stripe API key (sk_test_... or sk_live_...)")
    stripe_webhook_secret: str | None = Field(None, description="Stripe webhook signing secret")
    prices: dict[str, str] | None = Field(
        None,
        description='Price ID mapping (e.g., {"pro": "price_xxx", "enterprise": "price_yyy"})',
    )


class ConfigureBillingResponse(BaseModel):
    """Response from configuring billing."""

    configured: bool
    organization_id: str
    has_webhook_secret: bool
    price_ids: list[str]


class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""

    price_key: str = Field(..., description="Price key (e.g., 'pro', 'enterprise')")
    success_url: str = Field(..., description="URL to redirect after successful payment")
    cancel_url: str = Field(..., description="URL to redirect if payment is cancelled")
    metadata: dict[str, str] | None = Field(None, description="Optional metadata")


class CheckoutResponse(BaseModel):
    """Response from creating checkout session."""

    session_id: str
    url: str


class SubscriptionResponse(BaseModel):
    """Subscription status response."""

    status: str = Field(..., description="Subscription status: none, active, past_due, canceled")
    tier: str = Field(..., description="Subscription tier: free, pro, enterprise")
    subscription_id: str | None = None
    stripe_customer_id: str | None = None
    ends_at: str | None = None


class BillingPortalRequest(BaseModel):
    """Request for billing portal URL."""

    return_url: str = Field(..., description="URL to return to after portal session")


class BillingPortalResponse(BaseModel):
    """Response with billing portal URL."""

    url: str


class WebhookResponse(BaseModel):
    """Response from webhook processing."""

    received: bool
    event_id: str
    event_type: str
    processed_at: datetime


# === Helper Functions ===


def require_auth(auth_context: AuthContext) -> str:
    """Require authentication and return organization ID."""
    if auth_context.auth_type == "none":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    org_id = auth_context.organization_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization context required",
        )
    return org_id


def require_api_key_auth(auth_context: AuthContext) -> str:
    """Require API key authentication (service-to-service)."""
    if auth_context.auth_type != "api_key":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key authentication required for this operation",
        )
    return require_auth(auth_context)


# === Routes ===


@router.post(
    "/configure",
    response_model=ConfigureBillingResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure Stripe billing",
    description="Configure Stripe API keys and price mappings for an organization. Requires API key auth.",
)
async def configure_billing(
    request: ConfigureBillingRequest,
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ConfigureBillingResponse:
    """
    Configure Stripe billing for the organization.

    This endpoint is typically called by parent services
    to set up billing for their organizations. Requires API key authentication.
    """
    organization_id = require_api_key_auth(auth_context)

    logger.info(
        "configure_billing_request",
        organization_id=organization_id,
        has_webhook_secret=bool(request.stripe_webhook_secret),
    )

    try:
        service = BillingService(db)
        result = await service.configure_billing(
            organization_id=organization_id,
            api_key=request.stripe_api_key,
            webhook_secret=request.stripe_webhook_secret,
            prices=request.prices,
        )

        return ConfigureBillingResponse(
            configured=result["configured"],
            organization_id=result["organization_id"],
            has_webhook_secret=result["has_webhook_secret"],
            price_ids=result["price_ids"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("configure_billing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to configure billing",
        )


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create checkout session",
    description="Create a Stripe checkout session for subscription payment. Requires billing:create permission.",
)
async def create_checkout(
    request: CheckoutRequest,
    _perm: None = Depends(require_permission("billing", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    """Create a Stripe checkout session. Requires billing:create permission."""
    organization_id = require_auth(auth_context)

    logger.info(
        "create_checkout_request",
        organization_id=organization_id,
        price_key=request.price_key,
    )

    # Get customer email
    customer_email = None
    if auth_context.user:
        customer_email = auth_context.user.email

    if not customer_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email required for checkout",
        )

    try:
        service = BillingService(db)
        session = await service.create_checkout_session(
            organization_id=organization_id,
            price_key=request.price_key,
            customer_email=customer_email,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata=request.metadata,
        )

        return CheckoutResponse(
            session_id=session.id,
            url=session.url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("create_checkout_error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session",
        )


@router.post(
    "/webhook/{organization_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle Stripe webhook",
    description="Receive and process Stripe webhook events.",
)
async def stripe_webhook(
    organization_id: str,
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: str = Header(..., alias="stripe-signature"),
) -> WebhookResponse:
    """
    Handle Stripe webhook events.

    This endpoint is called by Stripe when events occur (e.g., payment completed).
    Authentication is done via Stripe signature verification.
    """
    logger.info(
        "webhook_received",
        organization_id=organization_id,
        signature_length=len(stripe_signature),
    )

    payload = await request.body()

    try:
        service = BillingService(db)
        result = await service.handle_webhook(
            organization_id=organization_id,
            payload=payload,
            signature=stripe_signature,
        )

        return WebhookResponse(
            received=True,
            event_id=result["event_id"],
            event_type=result["event_type"],
            processed_at=datetime.utcnow(),
        )
    except StripeWebhookError as e:
        logger.error("webhook_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    except ValueError as e:
        logger.error("webhook_processing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("webhook_error", error=str(e), error_type=type(e).__name__)
        # Return 200 to prevent Stripe retries for non-critical errors
        return WebhookResponse(
            received=True,
            event_id="error",
            event_type="error",
            processed_at=datetime.utcnow(),
        )


@router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get subscription status",
    description="Get current subscription status. Requires billing:view permission.",
)
async def get_subscription(
    _perm: None = Depends(require_permission("billing", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    """Get current subscription status. Requires billing:view permission."""
    organization_id = require_auth(auth_context)

    try:
        service = BillingService(db)
        result = await service.get_subscription(organization_id)

        return SubscriptionResponse(
            status=result["status"],
            tier=result["tier"],
            subscription_id=result.get("subscription_id"),
            stripe_customer_id=result.get("stripe_customer_id"),
            ends_at=result.get("ends_at"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("get_subscription_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get subscription status",
        )


@router.post(
    "/portal",
    response_model=BillingPortalResponse,
    status_code=status.HTTP_200_OK,
    summary="Get billing portal URL",
    description="Get URL to Stripe billing portal. Requires billing:manage permission.",
)
async def get_billing_portal(
    request: BillingPortalRequest,
    _perm: None = Depends(require_permission("billing", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> BillingPortalResponse:
    """Get Stripe billing portal URL. Requires billing:manage permission."""
    organization_id = require_auth(auth_context)

    try:
        service = BillingService(db)
        url = await service.create_billing_portal_session(
            organization_id=organization_id,
            return_url=request.return_url,
        )

        return BillingPortalResponse(url=url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("billing_portal_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create billing portal session",
        )


@router.get(
    "/configured",
    status_code=status.HTTP_200_OK,
    summary="Check if billing is configured",
    description="Check if billing is configured. Requires billing:view permission.",
)
async def is_billing_configured(
    _perm: None = Depends(require_permission("billing", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Check if billing is configured. Requires billing:view permission."""
    organization_id = require_auth(auth_context)

    service = BillingService(db)
    configured = await service.is_billing_configured(organization_id)

    return {"configured": configured}
