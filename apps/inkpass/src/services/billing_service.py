"""
Billing Service for InkPass.

Handles Stripe billing operations using aios-stripe package.
Stripe credentials are stored encrypted per organization.
"""

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from aios_stripe import (
    StripeClient,
    StripeConfig,
    StripeError,
    StripeWebhookError,
    CheckoutSession,
    WebhookEvent,
)

from src.database.models import BillingConfig, Organization
from src.security.encryption import encrypt_data, decrypt_data

logger = structlog.get_logger(__name__)


class BillingService:
    """
    Service for handling Stripe billing operations.

    Stripe credentials are stored encrypted in the database per organization.
    This allows different parent services to configure
    their own Stripe keys for their organizations.
    """

    def __init__(self, db: Session):
        """
        Initialize billing service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def _get_billing_config(self, organization_id: str) -> BillingConfig | None:
        """Get billing config for organization."""
        return (
            self.db.query(BillingConfig)
            .filter(BillingConfig.organization_id == organization_id)
            .first()
        )

    def _get_stripe_client(self, organization_id: str) -> StripeClient:
        """
        Get Stripe client for organization.

        Args:
            organization_id: Organization ID

        Returns:
            Configured StripeClient

        Raises:
            ValueError: If billing is not configured for organization
        """
        config = self._get_billing_config(organization_id)
        if not config:
            raise ValueError(f"Billing not configured for organization {organization_id}")

        api_key = decrypt_data(config.stripe_api_key_encrypted)
        webhook_secret = None
        if config.stripe_webhook_secret_encrypted:
            webhook_secret = decrypt_data(config.stripe_webhook_secret_encrypted)

        stripe_config = StripeConfig(
            api_key=api_key,
            webhook_secret=webhook_secret,
        )
        return StripeClient(stripe_config)

    async def configure_billing(
        self,
        organization_id: str,
        api_key: str,
        webhook_secret: str | None = None,
        prices: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Configure Stripe billing for an organization.

        Stores encrypted Stripe credentials and price mappings.

        Args:
            organization_id: Organization ID
            api_key: Stripe API key (sk_test_... or sk_live_...)
            webhook_secret: Stripe webhook signing secret (optional)
            prices: Price ID mapping (e.g., {"pro": "price_xxx"})

        Returns:
            Configuration confirmation
        """
        logger.info(
            "configuring_billing",
            organization_id=organization_id,
            has_webhook_secret=bool(webhook_secret),
            price_count=len(prices or {}),
        )

        # Verify organization exists
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise ValueError(f"Organization not found: {organization_id}")

        # Encrypt credentials
        encrypted_api_key = encrypt_data(api_key)
        encrypted_webhook_secret = encrypt_data(webhook_secret) if webhook_secret else None

        # Check if config already exists
        existing_config = self._get_billing_config(organization_id)

        if existing_config:
            # Update existing config
            existing_config.stripe_api_key_encrypted = encrypted_api_key
            existing_config.stripe_webhook_secret_encrypted = encrypted_webhook_secret
            existing_config.price_ids = prices or {}
            existing_config.updated_at = datetime.utcnow()
        else:
            # Create new config
            new_config = BillingConfig(
                organization_id=organization_id,
                stripe_api_key_encrypted=encrypted_api_key,
                stripe_webhook_secret_encrypted=encrypted_webhook_secret,
                price_ids=prices or {},
            )
            self.db.add(new_config)

        self.db.commit()

        logger.info(
            "billing_configured",
            organization_id=organization_id,
            is_update=bool(existing_config),
        )

        return {
            "configured": True,
            "organization_id": organization_id,
            "has_webhook_secret": bool(webhook_secret),
            "price_ids": list((prices or {}).keys()),
        }

    async def create_checkout_session(
        self,
        organization_id: str,
        price_key: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        """
        Create a Stripe checkout session.

        Args:
            organization_id: Organization ID
            price_key: Price key (e.g., "pro") mapped to actual price ID
            customer_email: Customer email
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is cancelled
            metadata: Optional metadata for the session

        Returns:
            CheckoutSession with session ID and URL
        """
        config = self._get_billing_config(organization_id)
        if not config:
            raise ValueError(f"Billing not configured for organization {organization_id}")

        # Get actual price ID from price key
        price_id = config.price_ids.get(price_key)
        if not price_id:
            raise ValueError(f"Price key not found: {price_key}")

        logger.info(
            "creating_checkout_session",
            organization_id=organization_id,
            price_key=price_key,
            customer_email=customer_email,
        )

        client = self._get_stripe_client(organization_id)

        # Add organization and price key to metadata
        full_metadata = {
            "organization_id": organization_id,
            "price_key": price_key,
            **(metadata or {}),
        }

        session = await client.create_checkout_session(
            price_id=price_id,
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=full_metadata,
        )

        logger.info(
            "checkout_session_created",
            organization_id=organization_id,
            session_id=session.id,
        )

        return session

    async def handle_webhook(
        self,
        organization_id: str,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        """
        Verify and process Stripe webhook.

        Updates organization subscription status based on webhook events.

        Args:
            organization_id: Organization ID
            payload: Raw webhook payload
            signature: Stripe signature header

        Returns:
            Processing result
        """
        logger.info(
            "handling_webhook",
            organization_id=organization_id,
            signature_length=len(signature),
        )

        client = self._get_stripe_client(organization_id)

        try:
            event = client.verify_webhook_signature(payload, signature)
        except StripeWebhookError as e:
            logger.error(
                "webhook_verification_failed",
                organization_id=organization_id,
                error=str(e),
            )
            raise

        logger.info(
            "webhook_verified",
            organization_id=organization_id,
            event_type=event.type,
            event_id=event.id,
        )

        # Process event based on type
        result = await self._process_webhook_event(organization_id, event)

        return {
            "processed": True,
            "event_id": event.id,
            "event_type": event.type,
            **result,
        }

    async def _process_webhook_event(
        self,
        organization_id: str,
        event: WebhookEvent,
    ) -> dict[str, Any]:
        """Process webhook event and update organization status."""
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            logger.error("organization_not_found", organization_id=organization_id)
            return {"error": "Organization not found"}

        config = self._get_billing_config(organization_id)

        if event.type == "checkout.session.completed":
            session_data = event.data.get("object", {})
            customer_id = session_data.get("customer")
            subscription_id = session_data.get("subscription")

            # Get price key from metadata
            metadata = session_data.get("metadata", {})
            price_key = metadata.get("price_key", "pro")

            # Map price key to tier
            tier = price_key  # price_key is typically the tier name

            org.stripe_customer_id = customer_id
            org.subscription_id = subscription_id
            org.subscription_status = "active"
            org.subscription_tier = tier

            logger.info(
                "checkout_completed",
                organization_id=organization_id,
                customer_id=customer_id,
                tier=tier,
            )

        elif event.type == "customer.subscription.created":
            sub_data = event.data.get("object", {})
            org.subscription_id = sub_data.get("id")
            org.subscription_status = "active"

            # Get period end
            period_end = sub_data.get("current_period_end")
            if period_end:
                org.subscription_ends_at = datetime.fromtimestamp(period_end)

            logger.info(
                "subscription_created",
                organization_id=organization_id,
                subscription_id=org.subscription_id,
            )

        elif event.type == "customer.subscription.updated":
            sub_data = event.data.get("object", {})
            status = sub_data.get("status", "active")

            org.subscription_status = status
            org.subscription_id = sub_data.get("id")

            # Update period end
            period_end = sub_data.get("current_period_end")
            if period_end:
                org.subscription_ends_at = datetime.fromtimestamp(period_end)

            # Check for cancellation
            if sub_data.get("cancel_at_period_end"):
                org.subscription_status = "canceled"

            logger.info(
                "subscription_updated",
                organization_id=organization_id,
                status=status,
            )

        elif event.type == "customer.subscription.deleted":
            org.subscription_status = "canceled"
            org.subscription_tier = "free"

            logger.info(
                "subscription_deleted",
                organization_id=organization_id,
            )

        elif event.type == "invoice.payment_failed":
            org.subscription_status = "past_due"

            logger.warning(
                "payment_failed",
                organization_id=organization_id,
            )

        self.db.commit()

        return {"status_updated": True, "new_status": org.subscription_status}

    async def get_subscription(self, organization_id: str) -> dict[str, Any]:
        """
        Get current subscription status for organization.

        Args:
            organization_id: Organization ID

        Returns:
            Subscription status and details
        """
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise ValueError(f"Organization not found: {organization_id}")

        return {
            "status": org.subscription_status or "none",
            "tier": org.subscription_tier or "free",
            "subscription_id": org.subscription_id,
            "stripe_customer_id": org.stripe_customer_id,
            "ends_at": org.subscription_ends_at.isoformat() if org.subscription_ends_at else None,
        }

    async def create_billing_portal_session(
        self,
        organization_id: str,
        return_url: str,
    ) -> str:
        """
        Create Stripe billing portal session.

        Args:
            organization_id: Organization ID
            return_url: URL to return to after portal session

        Returns:
            Billing portal URL
        """
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise ValueError(f"Organization not found: {organization_id}")

        if not org.stripe_customer_id:
            raise ValueError("No Stripe customer ID found for organization")

        client = self._get_stripe_client(organization_id)

        portal_url = await client.create_billing_portal_session(
            customer_id=org.stripe_customer_id,
            return_url=return_url,
        )

        logger.info(
            "billing_portal_created",
            organization_id=organization_id,
        )

        return portal_url

    async def is_billing_configured(self, organization_id: str) -> bool:
        """Check if billing is configured for organization."""
        config = self._get_billing_config(organization_id)
        return config is not None
