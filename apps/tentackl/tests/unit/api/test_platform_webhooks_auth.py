"""Tests for platform webhook authentication enforcement."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.api.routers import platform_webhooks


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(platform_webhooks.router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def _valid_payload():
    return {
        "ticket_id": "t-1",
        "customer_email": "customer@example.com",
        "subject": "Need help",
        "body": "Issue details",
        "source": "api",
    }


def test_support_rejects_without_internal_key(client):
    platform_webhooks.PLATFORM_WEBHOOK_KEY = "test-key"

    response = client.post("/api/platform/webhooks/support", json=_valid_payload())
    assert response.status_code == 401


def test_support_accepts_with_valid_internal_key(client, app):
    platform_webhooks.PLATFORM_WEBHOOK_KEY = "test-key"

    mock_use_cases = MagicMock()
    mock_task = MagicMock()
    mock_task.id = "task-123"
    mock_task.steps = []
    mock_use_cases.create_task = AsyncMock(return_value=mock_task)

    async def _override_task_use_cases():
        return mock_use_cases

    app.dependency_overrides[platform_webhooks.get_task_use_cases] = _override_task_use_cases

    response = client.post(
        "/api/platform/webhooks/support",
        json=_valid_payload(),
        headers={"X-Platform-Webhook-Key": "test-key"},
    )
    assert response.status_code == 202
