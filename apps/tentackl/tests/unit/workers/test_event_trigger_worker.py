"""Tests for EventTriggerWorker deduplication logic."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.workers.event_trigger_worker import EventTriggerWorker, RELEASE_LOCK_SCRIPT
from src.interfaces.event_bus import Event, EventSourceType


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = MagicMock()
    bus.redis_url = "redis://localhost:6379/0"
    bus.key_prefix = "tentackl:eventbus"
    bus.start = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.get_event_by_id = AsyncMock()
    return bus


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = AsyncMock()
    client.set = AsyncMock(return_value=True)  # Lock acquired by default
    client.eval = AsyncMock(return_value=1)  # Lock released successfully
    client.hgetall = AsyncMock(return_value={})
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_event():
    """Create a sample event for testing."""
    return Event(
        id="test-event-123",
        source="webhook",
        source_type=EventSourceType.WEBHOOK,
        event_type="external.webhook.order.created",
        data={"order_id": "ORD-001", "amount": 100},
        metadata={"source_id": "source-abc"},
        timestamp=datetime.utcnow()
    )


@pytest.fixture
def worker(mock_event_bus):
    """Create an EventTriggerWorker instance."""
    return EventTriggerWorker(mock_event_bus)


class TestEventTriggerWorkerInit:
    """Test EventTriggerWorker initialization."""

    def test_subscriber_id_includes_pid(self, worker):
        """Subscriber ID should include process ID for uniqueness."""
        import os
        assert f"event-trigger-worker-{os.getpid()}" == worker._subscriber_id

    def test_lock_ttl_is_set(self, worker):
        """Lock TTL should be configured."""
        assert worker._lock_ttl == 300  # 5 minutes


class TestEventDeduplication:
    """Test event deduplication via Redis locks."""

    @pytest.mark.asyncio
    async def test_first_event_acquires_lock_and_processes(
        self, worker, mock_redis_client, sample_event
    ):
        """First event should acquire lock and be processed."""
        worker._redis_client = mock_redis_client
        worker._callback_engine = AsyncMock()
        worker._callback_engine.execute_callback = AsyncMock(
            return_value=MagicMock(success=True, results=[])
        )

        # Mock source config lookup
        worker._get_source_config = AsyncMock(return_value={
            "id": "source-abc",
            "name": "Test Source",
            "active": True,
            "config": {"playground_session": "session-123"}
        })
        worker._get_callback_for_source = AsyncMock(return_value=MagicMock())

        # Lock should be acquired (first call)
        mock_redis_client.set.return_value = True

        await worker._handle_event(sample_event)

        # Verify lock was attempted
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert call_args[0][0] == f"tentackl:lock:event:{sample_event.id}"
        assert call_args[1]["nx"] is True
        assert call_args[1]["ex"] == 300

        # Verify lock was released
        mock_redis_client.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_event_skipped_when_lock_not_acquired(
        self, worker, mock_redis_client, sample_event
    ):
        """Duplicate event should be skipped when lock cannot be acquired."""
        worker._redis_client = mock_redis_client
        worker._callback_engine = AsyncMock()

        # Lock acquisition fails (already held by another worker)
        mock_redis_client.set.return_value = False

        # This should NOT call the callback engine
        await worker._handle_event(sample_event)

        # Verify callback was NOT executed
        worker._callback_engine.execute_callback.assert_not_called()

        # Verify lock release was NOT attempted (we didn't acquire it)
        mock_redis_client.eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_released_even_on_error(
        self, worker, mock_redis_client, sample_event
    ):
        """Lock should be released even if processing fails."""
        worker._redis_client = mock_redis_client
        worker._callback_engine = AsyncMock()

        # Lock acquired successfully
        mock_redis_client.set.return_value = True

        # But processing fails
        worker._get_source_config = AsyncMock(side_effect=Exception("Processing error"))

        # Should not raise (error is caught)
        await worker._handle_event(sample_event)

        # Verify lock was still released
        mock_redis_client.eval.assert_called_once()
        eval_args = mock_redis_client.eval.call_args[0]
        assert eval_args[0] == RELEASE_LOCK_SCRIPT
        assert eval_args[2] == f"tentackl:lock:event:{sample_event.id}"

    @pytest.mark.asyncio
    async def test_concurrent_events_only_one_processes(
        self, mock_event_bus, mock_redis_client, sample_event
    ):
        """Simulate multiple workers receiving the same event - only one should process."""
        # Create two workers (simulating two Gunicorn processes)
        worker1 = EventTriggerWorker(mock_event_bus)
        worker2 = EventTriggerWorker(mock_event_bus)

        # Track which workers processed the event
        processed_by = []

        async def mock_process(event, lock_key):
            processed_by.append(worker1._subscriber_id if len(processed_by) == 0 else worker2._subscriber_id)

        # First worker gets the lock
        redis_client1 = AsyncMock()
        redis_client1.set = AsyncMock(return_value=True)
        redis_client1.eval = AsyncMock(return_value=1)
        worker1._redis_client = redis_client1
        worker1._process_event_with_lock = AsyncMock(side_effect=lambda e, k: processed_by.append("worker1"))

        # Second worker fails to get the lock
        redis_client2 = AsyncMock()
        redis_client2.set = AsyncMock(return_value=False)  # Lock denied
        redis_client2.eval = AsyncMock(return_value=0)
        worker2._redis_client = redis_client2
        worker2._process_event_with_lock = AsyncMock(side_effect=lambda e, k: processed_by.append("worker2"))

        # Both workers try to handle the same event
        await asyncio.gather(
            worker1._handle_event(sample_event),
            worker2._handle_event(sample_event)
        )

        # Only worker1 should have processed (it got the lock)
        assert processed_by == ["worker1"]
        worker1._process_event_with_lock.assert_called_once()
        worker2._process_event_with_lock.assert_not_called()


class TestLuaScript:
    """Test the lock release Lua script."""

    def test_release_lock_script_format(self):
        """Verify the Lua script has correct format."""
        assert "redis.call" in RELEASE_LOCK_SCRIPT
        assert "get" in RELEASE_LOCK_SCRIPT
        assert "del" in RELEASE_LOCK_SCRIPT
        assert "KEYS[1]" in RELEASE_LOCK_SCRIPT
        assert "ARGV[1]" in RELEASE_LOCK_SCRIPT
