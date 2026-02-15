"""Stripe billing service"""

import stripe
from typing import Optional, Dict, Any
from src.config import settings
import structlog

logger = structlog.get_logger()

# Initialize Stripe
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """Service for handling Stripe billing operations"""
    
    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            logger.warning("Stripe secret key not configured")
    
    async def create_customer(self, email: str, user_id: str) -> Optional[str]:
        """Create a Stripe customer"""
        if not settings.STRIPE_SECRET_KEY:
            return None
        
        try:
            customer = stripe.Customer.create(
                email=email,
                metadata={"user_id": user_id}
            )
            return customer.id
        except Exception as e:
            logger.error("Failed to create Stripe customer", error=str(e))
            return None
    
    async def create_subscription(
        self,
        customer_id: str,
        price_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create an annual subscription"""
        if not settings.STRIPE_SECRET_KEY:
            return None
        
        try:
            # Use default price ID or create price on the fly
            if not price_id:
                # Create annual price if it doesn't exist
                price = stripe.Price.create(
                    unit_amount=settings.ANNUAL_SUBSCRIPTION_PRICE,  # $499.00 in cents
                    currency="usd",
                    recurring={"interval": "year"},
                    product_data={"name": "Mimic Annual Subscription"}
                )
                price_id = price.id
            
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                metadata={"plan": "annual"}
            )
            
            return {
                "subscription_id": subscription.id,
                "customer_id": customer_id,
                "status": subscription.status,
                "current_period_end": subscription.current_period_end
            }
        except Exception as e:
            logger.error("Failed to create Stripe subscription", error=str(e))
            return None
    
    async def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a subscription"""
        if not settings.STRIPE_SECRET_KEY:
            return False
        
        try:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            return True
        except Exception as e:
            logger.error("Failed to cancel Stripe subscription", error=str(e))
            return False
    
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Optional[Dict[str, Any]]:
        """Verify Stripe webhook signature"""
        if not settings.STRIPE_WEBHOOK_SECRET:
            return None
        
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            logger.error("Invalid Stripe webhook payload", error=str(e))
            return None
        except stripe.error.SignatureVerificationError as e:
            logger.error("Invalid Stripe webhook signature", error=str(e))
            return None

