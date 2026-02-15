"""E2E tests for webhook verification."""

import os
import pytest

from aios_stripe import StripeClient, StripeConfig
from aios_stripe.exceptions import StripeWebhookError


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("STRIPE_TEST_API_KEY"),
        reason="STRIPE_TEST_API_KEY not set",
    ),
]


class TestWebhookVerificationE2E:
    """E2E tests for webhook signature verification."""

    def test_invalid_signature_rejected(self, live_client: StripeClient):
        """Test that invalid webhook signatures are rejected."""
        payload = b'{"type": "checkout.session.completed", "data": {}}'

        with pytest.raises(StripeWebhookError, match="Invalid webhook"):
            live_client.verify_webhook_signature(payload, "invalid_signature")

    def test_webhook_without_secret_configured(self):
        """Test webhook verification fails when secret not configured."""
        config = StripeConfig(
            api_key=os.environ["STRIPE_TEST_API_KEY"],
            webhook_secret=None,  # No secret configured
        )
        client = StripeClient(config)

        with pytest.raises(StripeWebhookError, match="not configured"):
            client.verify_webhook_signature(b"{}", "sig_123")

    def test_invalid_payload_rejected(self, live_client: StripeClient):
        """Test that invalid JSON payloads are rejected."""
        if not live_client.config.webhook_secret:
            pytest.skip("STRIPE_TEST_WEBHOOK_SECRET not set")

        with pytest.raises(StripeWebhookError):
            live_client.verify_webhook_signature(b"not valid json", "sig_123")
