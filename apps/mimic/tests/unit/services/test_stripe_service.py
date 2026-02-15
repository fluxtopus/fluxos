"""Unit tests for Stripe service"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.stripe_service import StripeService


@pytest.fixture
def stripe_service():
    """Create Stripe service instance"""
    return StripeService()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_customer(stripe_service):
    """Test creating a Stripe customer"""
    with patch('src.services.stripe_service.stripe') as mock_stripe, \
         patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_SECRET_KEY = "sk_test_fake"
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_stripe.Customer.create.return_value = mock_customer

        result = await stripe_service.create_customer("test@example.com", "user-123")

        assert result == "cus_test123"
        mock_stripe.Customer.create.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_customer_no_stripe_key(stripe_service):
    """Test creating customer when Stripe key is not configured"""
    with patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_SECRET_KEY = None
        
        result = await stripe_service.create_customer("test@example.com", "user-123")
        
        assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subscription(stripe_service):
    """Test creating a subscription"""
    with patch('src.services.stripe_service.stripe') as mock_stripe, \
         patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_SECRET_KEY = "sk_test_fake"
        mock_settings.ANNUAL_SUBSCRIPTION_PRICE = 49900
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "active"
        mock_subscription.current_period_end = 1735689600

        mock_stripe.Price.create.return_value = MagicMock(id="price_test")
        mock_stripe.Subscription.create.return_value = mock_subscription

        result = await stripe_service.create_subscription("cus_test123")

        assert result is not None
        assert result["subscription_id"] == "sub_test123"
        assert result["status"] == "active"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_subscription(stripe_service):
    """Test canceling a subscription"""
    with patch('src.services.stripe_service.stripe') as mock_stripe, \
         patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_SECRET_KEY = "sk_test_fake"
        mock_subscription = MagicMock()
        mock_stripe.Subscription.modify.return_value = mock_subscription

        result = await stripe_service.cancel_subscription("sub_test123")

        assert result is True
        mock_stripe.Subscription.modify.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_webhook(stripe_service):
    """Test verifying Stripe webhook signature"""
    with patch('src.services.stripe_service.stripe') as mock_stripe, \
         patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        mock_event = {"type": "customer.subscription.updated", "data": {}}
        mock_stripe.Webhook.construct_event.return_value = mock_event

        payload = b'{"test": "data"}'
        signature = "test-signature"

        result = await stripe_service.verify_webhook(payload, signature)

        assert result == mock_event
        mock_stripe.Webhook.construct_event.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_webhook_invalid_signature(stripe_service):
    """Test verifying webhook with invalid signature"""
    import stripe as real_stripe

    with patch('src.services.stripe_service.stripe') as mock_stripe, \
         patch('src.services.stripe_service.settings') as mock_settings:
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        # Important: ensure mock_stripe.error.SignatureVerificationError is the real class
        # so the except clause can catch it
        mock_stripe.error = real_stripe.error
        mock_stripe.Webhook.construct_event.side_effect = real_stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        payload = b'{"test": "data"}'
        signature = "invalid-signature"

        result = await stripe_service.verify_webhook(payload, signature)

        assert result is None

