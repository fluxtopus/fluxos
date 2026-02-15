"""OAuth CSRF hardening tests."""

import pytest
from fastapi import status
from unittest.mock import patch


@pytest.mark.integration
def test_oauth_login_sets_state_cookie(client):
    """Login redirect must set a state cookie for callback verification."""
    with patch(
        "src.services.oauth_service.OAuthService.initiate_oauth_flow",
        return_value=("https://oauth.example.com/auth", "csrf-state-123"),
    ):
        response = client.get(
            "/api/v1/auth/oauth/mock/login",
            follow_redirects=False,
        )

    assert response.status_code in (status.HTTP_302_FOUND, status.HTTP_307_TEMPORARY_REDIRECT)
    assert "oauth_state=csrf-state-123" in response.headers.get("set-cookie", "")


@pytest.mark.integration
def test_oauth_callback_post_rejects_missing_state_cookie(client):
    """POST callback must fail when state cookie is missing."""
    response = client.post(
        "/api/v1/auth/oauth/callback",
        json={
            "code": "mock-code",
            "state": "state-123",
            "provider": "mock",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid state token" in response.json()["detail"]

