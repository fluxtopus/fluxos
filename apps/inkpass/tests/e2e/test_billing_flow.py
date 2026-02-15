"""End-to-end tests for billing flow."""

import json
import uuid

import pytest
from fastapi import status


@pytest.fixture
def api_key_and_org(client, db):
    """Create a user, activate them, and create an API key for service auth."""
    unique_id = uuid.uuid4().hex[:8]
    email = f"billing-test-{unique_id}@example.com"
    org_name = f"Billing Test Org {unique_id}"

    # Register user
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "BillingTestPass123!",
            "organization_name": org_name,
        },
    )
    assert register_response.status_code == status.HTTP_201_CREATED
    data = register_response.json()
    org_id = data["organization_id"]

    # Activate user directly in database
    from src.database.models import User

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.status = "active"
        db.commit()

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "BillingTestPass123!",
        },
    )
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

    # Create API key
    api_key_response = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "billing-test-key"},
    )
    assert api_key_response.status_code in (200, 201)
    api_key = api_key_response.json()["key"]

    return {
        "api_key": api_key,
        "token": token,
        "org_id": org_id,
        "email": email,
    }


@pytest.mark.e2e
class TestBillingFlow:
    """Test complete billing flow."""

    def test_configure_billing(self, client, api_key_and_org):
        """Test configuring Stripe billing for an organization."""
        # Configure billing with API key auth
        response = client.post(
            "/api/v1/billing/configure",
            headers={"X-API-Key": api_key_and_org["api_key"]},
            json={
                "stripe_api_key": "sk_test_fake_key_12345",
                "stripe_webhook_secret": "whsec_fake_secret_12345",
                "prices": {
                    "pro": "price_pro_123",
                    "enterprise": "price_enterprise_456",
                },
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["configured"] is True
        assert data["organization_id"] == api_key_and_org["org_id"]
        assert "pro" in data["price_ids"]
        assert "enterprise" in data["price_ids"]

    def test_check_billing_configured(self, client, api_key_and_org, db):
        """Test checking if billing is configured."""
        # First configure billing
        client.post(
            "/api/v1/billing/configure",
            headers={"X-API-Key": api_key_and_org["api_key"]},
            json={
                "stripe_api_key": "sk_test_fake_key_12345",
                "prices": {"pro": "price_pro_123"},
            },
        )

        # Check if configured
        response = client.get(
            "/api/v1/billing/configured",
            headers={"X-API-Key": api_key_and_org["api_key"]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["configured"] is True

    def test_get_subscription_initial_state(self, client, api_key_and_org):
        """Test getting subscription status (initial state)."""
        response = client.get(
            "/api/v1/billing/subscription",
            headers={"Authorization": f"Bearer {api_key_and_org['token']}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "none"
        assert data["tier"] == "free"

    def test_configure_billing_requires_api_key(self, client, api_key_and_org):
        """Test that configure billing requires API key auth, not JWT."""
        # Try with JWT token (should fail)
        response = client.post(
            "/api/v1/billing/configure",
            headers={"Authorization": f"Bearer {api_key_and_org['token']}"},
            json={
                "stripe_api_key": "sk_test_fake_key_12345",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_checkout_requires_billing_config(self, client, api_key_and_org):
        """Test that checkout fails if billing is not configured."""
        # Try to create checkout without configuring billing first
        response = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {api_key_and_org['token']}"},
            json={
                "price_key": "pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )

        # Should fail because billing not configured
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_billing_portal_requires_customer(self, client, api_key_and_org):
        """Test that billing portal fails without Stripe customer ID."""
        response = client.post(
            "/api/v1/billing/portal",
            headers={"Authorization": f"Bearer {api_key_and_org['token']}"},
            json={"return_url": "https://example.com"},
        )

        # Should fail because no Stripe customer ID
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.e2e
class TestBillingWebhook:
    """Test Stripe webhook handling."""

    def test_webhook_invalid_signature(self, client, api_key_and_org, db):
        """Test webhook rejects invalid signature."""
        # Configure billing first
        client.post(
            "/api/v1/billing/configure",
            headers={"X-API-Key": api_key_and_org["api_key"]},
            json={
                "stripe_api_key": "sk_test_fake_key_12345",
                "stripe_webhook_secret": "whsec_test_secret",
                "prices": {"pro": "price_pro_123"},
            },
        )

        # Send webhook with invalid signature
        response = client.post(
            f"/api/v1/billing/webhook/{api_key_and_org['org_id']}",
            headers={"stripe-signature": "invalid_signature"},
            content=json.dumps({"type": "checkout.session.completed"}).encode(),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.e2e
class TestSubscriptionUpdates:
    """Test subscription status updates through direct DB manipulation (simulating webhook effects)."""

    def test_subscription_status_after_activation(self, client, api_key_and_org, db):
        """Test subscription status after it's activated (simulating webhook)."""
        from src.database.models import Organization

        # Update org directly (simulating what webhook would do)
        org = db.query(Organization).filter(Organization.id == api_key_and_org["org_id"]).first()
        org.stripe_customer_id = "cus_test_123"
        org.subscription_id = "sub_test_456"
        org.subscription_status = "active"
        org.subscription_tier = "pro"
        db.commit()

        # Get subscription status
        response = client.get(
            "/api/v1/billing/subscription",
            headers={"Authorization": f"Bearer {api_key_and_org['token']}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "active"
        assert data["tier"] == "pro"
        assert data["stripe_customer_id"] == "cus_test_123"
        assert data["subscription_id"] == "sub_test_456"
