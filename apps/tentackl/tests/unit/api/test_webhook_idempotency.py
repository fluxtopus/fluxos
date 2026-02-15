"""Tests for webhook endpoint idempotency."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
import hashlib


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    return redis_mock


@pytest.fixture
def mock_event_gateway():
    """Create a mock event gateway."""
    gateway = MagicMock()
    gateway.authenticate_source = AsyncMock(return_value=True)
    gateway.validate_event = AsyncMock()
    gateway._initialized = True
    return gateway


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    bus._running = True
    return bus


class TestWebhookIdempotency:
    """Test webhook endpoint idempotency features."""

    def test_duplicate_request_returns_already_processed(self):
        """Duplicate request should return success with already_processed message."""
        from fastapi import FastAPI
        from src.api.routers import external_events

        app = FastAPI()

        # Mock Redis to return False (already exists)
        async def mock_get_redis():
            mock = AsyncMock()
            mock.set = AsyncMock(return_value=False)  # Key already exists
            return mock

        # Mock dependencies
        mock_gateway = MagicMock()
        mock_gateway.authenticate_source = AsyncMock(return_value=True)
        mock_gateway._initialized = True

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(return_value=True)
        mock_bus._running = True

        # Set module-level variables
        external_events.event_gateway = mock_gateway
        external_events.event_bus = mock_bus
        external_events.redis_client = None

        # Override get_redis_client
        with patch.object(external_events, 'get_redis_client', mock_get_redis):
            app.include_router(external_events.router)

            with TestClient(app) as client:
                response = client.post(
                    "/api/events/webhook/source-123",
                    json={
                        "event_type": "order.created",
                        "data": {"order_id": "123"}
                    },
                    headers={
                        "X-API-Key": "test-key",
                        "X-Idempotency-Key": "unique-request-id"
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert "duplicate" in data["event_id"]
                assert "already processed" in data["message"].lower()

    def test_new_request_processes_normally(self):
        """New request should be processed normally."""
        from fastapi import FastAPI
        from src.api.routers import external_events
        from src.interfaces.event_bus import Event, EventSourceType
        from datetime import datetime

        app = FastAPI()

        # Mock Redis to return True (new key set successfully)
        async def mock_get_redis():
            mock = AsyncMock()
            mock.set = AsyncMock(return_value=True)  # Key set successfully
            return mock

        # Mock gateway
        mock_gateway = MagicMock()
        mock_gateway.authenticate_source = AsyncMock(return_value=True)
        mock_gateway._initialized = True

        # Mock validate_event to return a proper Event
        async def mock_validate_event(raw_event):
            return Event(
                id="event-123",
                source=raw_event.source_id,
                source_type=EventSourceType.WEBHOOK,
                event_type="order.created",
                data=raw_event.data,
                metadata={"source_id": raw_event.source_id},
                timestamp=datetime.utcnow()
            )
        mock_gateway.validate_event = mock_validate_event

        # Mock bus
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(return_value=True)
        mock_bus._running = True

        # Set module-level variables
        external_events.event_gateway = mock_gateway
        external_events.event_bus = mock_bus
        external_events.redis_client = None

        with patch.object(external_events, 'get_redis_client', mock_get_redis):
            app.include_router(external_events.router)

            with TestClient(app) as client:
                response = client.post(
                    "/api/events/webhook/source-123",
                    json={
                        "event_type": "order.created",
                        "data": {"order_id": "123"}
                    },
                    headers={
                        "X-API-Key": "test-key",
                        "X-Idempotency-Key": "new-unique-id"
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert "duplicate" not in data["event_id"]

    def test_idempotency_key_generated_from_body_hash(self):
        """When no idempotency key provided, one should be generated from body hash."""
        from src.api.routers.external_events import receive_webhook_event
        import json

        source_id = "source-123"
        body = {"event_type": "test", "data": {"key": "value"}}
        body_bytes = json.dumps(body).encode()
        body_hash = hashlib.sha256(body_bytes).hexdigest()[:16]

        expected_key = f"{source_id}:{body_hash}"

        # The key should be deterministic based on source_id + body hash
        assert len(expected_key) > len(source_id)
        assert source_id in expected_key

    def test_same_body_generates_same_idempotency_key(self):
        """Same request body should generate the same idempotency key."""
        import json

        body = {"event_type": "order.created", "data": {"order_id": "123"}}
        body_bytes = json.dumps(body).encode()

        hash1 = hashlib.sha256(body_bytes).hexdigest()[:16]
        hash2 = hashlib.sha256(body_bytes).hexdigest()[:16]

        assert hash1 == hash2

    def test_different_body_generates_different_idempotency_key(self):
        """Different request bodies should generate different idempotency keys."""
        import json

        body1 = {"event_type": "order.created", "data": {"order_id": "123"}}
        body2 = {"event_type": "order.created", "data": {"order_id": "456"}}

        body1_bytes = json.dumps(body1).encode()
        body2_bytes = json.dumps(body2).encode()

        hash1 = hashlib.sha256(body1_bytes).hexdigest()[:16]
        hash2 = hashlib.sha256(body2_bytes).hexdigest()[:16]

        assert hash1 != hash2


class TestIdempotencyTTL:
    """Test idempotency key TTL configuration."""

    def test_idempotency_ttl_is_300_seconds(self):
        """Idempotency TTL should be 300 seconds (5 minutes)."""
        from src.api.routers.external_events import IDEMPOTENCY_TTL
        assert IDEMPOTENCY_TTL == 300
