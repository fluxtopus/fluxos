"""Integration tests for internal route authentication."""

import pytest
from fastapi import status

from src.config import settings


@pytest.mark.integration
def test_internal_route_requires_service_api_key(client):
    """Internal endpoint should reject unauthenticated requests."""
    response = client.post(
        "/api/v1/internal/templates/apply",
        json={
            "organization_id": "org-1",
            "owner_user_id": "user-1",
            "product_type": "invalid",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "X-Service-API-Key" in response.json()["detail"]


@pytest.mark.integration
def test_internal_route_accepts_valid_service_api_key(client):
    """Internal endpoint should accept valid service keys before business validation."""
    previous_keys = settings.SERVICE_API_KEYS
    settings.SERVICE_API_KEYS = "aios:test-internal-key"
    try:
        response = client.post(
            "/api/v1/internal/templates/apply",
            json={
                "organization_id": "org-1",
                "owner_user_id": "user-1",
                "product_type": "invalid",
            },
            headers={"X-Service-API-Key": "test-internal-key"},
        )
    finally:
        settings.SERVICE_API_KEYS = previous_keys

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid product type" in response.json()["detail"]
