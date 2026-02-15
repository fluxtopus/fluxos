"""Unit tests for TaskTriggerRegistry."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry
from src.interfaces.event_bus import Event, EventSourceType


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.sadd = AsyncMock(return_value=1)
    redis.srem = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.scan = AsyncMock(return_value=(0, []))
    redis.aclose = AsyncMock()
    return redis


@pytest.fixture
def registry(mock_redis):
    """Create a TaskTriggerRegistry with mocked Redis."""
    reg = TaskTriggerRegistry()
    reg._redis_client = mock_redis
    reg._initialized = True
    return reg


class TestRegisterTrigger:
    """Tests for trigger registration."""

    @pytest.mark.asyncio
    async def test_register_trigger_stores_in_redis(self, registry, mock_redis):
        """Verify trigger is stored in Redis with correct key format."""
        task_id = "task-123"
        org_id = "org-456"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.integration.*",
            "enabled": True,
        }

        result = await registry.register_trigger(task_id, org_id, trigger_config)

        assert result is True
        # Check config was stored
        mock_redis.set.assert_called_once()
        config_key = mock_redis.set.call_args[0][0]
        assert f"task:{task_id}" in config_key

        # Check task was added to pattern set
        mock_redis.sadd.assert_called_once()
        pattern_key = mock_redis.sadd.call_args[0][0]
        assert f"org:{org_id}:pattern:external.integration.*" in pattern_key

    @pytest.mark.asyncio
    async def test_register_trigger_without_pattern_fails(self, registry):
        """Verify registration fails without event_pattern."""
        result = await registry.register_trigger(
            task_id="task-123",
            organization_id="org-456",
            trigger_config={"type": "event", "enabled": True},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_register_disabled_trigger_skipped(self, registry, mock_redis):
        """Verify disabled triggers are not registered."""
        result = await registry.register_trigger(
            task_id="task-123",
            organization_id="org-456",
            trigger_config={
                "type": "event",
                "event_pattern": "external.*",
                "enabled": False,
            },
        )

        assert result is False
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_updates_memory_cache(self, registry):
        """Verify in-memory cache is updated."""
        task_id = "task-123"
        org_id = "org-456"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.webhook.*",
            "enabled": True,
        }

        await registry.register_trigger(task_id, org_id, trigger_config)

        # Check config cache
        assert task_id in registry._config_cache
        assert registry._config_cache[task_id]["organization_id"] == org_id

        # Check pattern cache
        cache_key = (org_id, "external.webhook.*")
        assert cache_key in registry._pattern_cache
        assert task_id in registry._pattern_cache[cache_key]


class TestUnregisterTrigger:
    """Tests for trigger unregistration."""

    @pytest.mark.asyncio
    async def test_unregister_removes_from_redis(self, registry, mock_redis):
        """Verify unregister cleans up Redis keys."""
        task_id = "task-123"
        org_id = "org-456"

        # Pre-populate cache
        mock_redis.get.return_value = '{"event_pattern": "external.*", "organization_id": "org-456"}'

        result = await registry.unregister_trigger(task_id)

        assert result is True
        mock_redis.delete.assert_called_once()
        mock_redis.srem.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregister_updates_memory_cache(self, registry, mock_redis):
        """Verify unregister clears memory cache."""
        task_id = "task-123"
        org_id = "org-456"

        # Pre-populate caches
        registry._config_cache[task_id] = {
            "event_pattern": "external.*",
            "organization_id": org_id,
        }
        registry._pattern_cache[(org_id, "external.*")] = {task_id}
        mock_redis.get.return_value = '{"event_pattern": "external.*", "organization_id": "org-456"}'

        await registry.unregister_trigger(task_id)

        assert task_id not in registry._config_cache
        assert (org_id, "external.*") not in registry._pattern_cache


class TestFindMatchingTasks:
    """Tests for finding tasks that match events."""

    @pytest.mark.asyncio
    async def test_find_matching_tasks_returns_registered_tasks(self, registry, mock_redis):
        """Verify events match registered patterns."""
        task_id = "task-123"
        org_id = "org-456"

        # Pre-populate pattern cache
        registry._pattern_cache[(org_id, "external.integration.*")] = {task_id}
        registry._config_cache[task_id] = {
            "event_pattern": "external.integration.*",
            "organization_id": org_id,
            "enabled": True,
        }

        # Setup Redis mock to return matching keys
        mock_redis.scan.return_value = (
            0,
            [f"tentackl:triggers:org:{org_id}:pattern:external.integration.*"]
        )
        mock_redis.smembers.return_value = {task_id}
        mock_redis.get.return_value = '{"event_pattern": "external.integration.*", "enabled": true}'

        event = Event(
            id="evt-1",
            event_type="external.integration.webhook",
            source="integration:abc",
            metadata={"organization_id": org_id},
        )

        result = await registry.find_matching_tasks(event)

        assert task_id in result

    @pytest.mark.asyncio
    async def test_find_matching_respects_org_scope(self, registry, mock_redis):
        """Verify only tasks in the same org are returned."""
        event = Event(
            id="evt-1",
            event_type="external.integration.webhook",
            source="integration:abc",
            metadata={"organization_id": "org-A"},
        )

        # Setup Redis to scan for org-A patterns only
        mock_redis.scan.return_value = (0, [])

        result = await registry.find_matching_tasks(event)

        # Scan should have been called with org-A prefix
        scan_call = mock_redis.scan.call_args
        assert "org:org-A:pattern:" in scan_call[1]["match"]

    @pytest.mark.asyncio
    async def test_find_matching_without_org_returns_empty(self, registry):
        """Verify events without org_id return no matches."""
        event = Event(
            id="evt-1",
            event_type="external.integration.webhook",
            source="integration:abc",
            metadata={},  # No organization_id
        )

        result = await registry.find_matching_tasks(event)

        assert result == []

    @pytest.mark.asyncio
    async def test_source_filter_applied(self, registry, mock_redis):
        """Verify source_filter prevents non-matching events."""
        task_id = "task-123"
        org_id = "org-456"

        registry._config_cache[task_id] = {
            "event_pattern": "external.integration.*",
            "organization_id": org_id,
            "source_filter": "integration:specific-bot",
            "enabled": True,
        }

        mock_redis.scan.return_value = (
            0,
            [f"tentackl:triggers:org:{org_id}:pattern:external.integration.*"]
        )
        mock_redis.smembers.return_value = {task_id}

        # Event from different source
        event = Event(
            id="evt-1",
            event_type="external.integration.webhook",
            source="integration:other-bot",
            metadata={"organization_id": org_id},
        )

        result = await registry.find_matching_tasks(event)

        assert task_id not in result


class TestPatternMatching:
    """Tests for glob pattern matching."""

    def test_exact_match(self, registry):
        """Verify exact pattern matches."""
        assert registry._matches_pattern("external.webhook.stripe", "external.webhook.stripe")

    def test_wildcard_match(self, registry):
        """Verify wildcard pattern matches."""
        assert registry._matches_pattern("external.integration.webhook", "external.integration.*")
        assert registry._matches_pattern("external.integration.discord", "external.integration.*")

    def test_no_match(self, registry):
        """Verify non-matching patterns don't match."""
        assert not registry._matches_pattern("external.webhook", "external.integration.*")
        assert not registry._matches_pattern("internal.event", "external.*")


class TestLoadAllTriggers:
    """Tests for loading triggers on startup."""

    @pytest.mark.asyncio
    async def test_load_populates_caches(self, registry, mock_redis):
        """Verify load_all_triggers populates memory caches."""
        task_id = "task-123"
        org_id = "org-456"
        config = {
            "event_pattern": "external.*",
            "organization_id": org_id,
            "enabled": True,
        }

        mock_redis.scan.return_value = (
            0,
            [f"tentackl:triggers:task:{task_id}"]
        )
        mock_redis.get.return_value = '{"event_pattern": "external.*", "organization_id": "org-456", "enabled": true}'

        count = await registry.load_all_triggers()

        assert count == 1
        assert task_id in registry._config_cache
        assert (org_id, "external.*") in registry._pattern_cache

    @pytest.mark.asyncio
    async def test_load_skips_disabled(self, registry, mock_redis):
        """Verify disabled triggers are not loaded into pattern cache."""
        mock_redis.scan.return_value = (
            0,
            ["tentackl:triggers:task:task-123"]
        )
        mock_redis.get.return_value = '{"event_pattern": "external.*", "organization_id": "org-456", "enabled": false}'

        count = await registry.load_all_triggers()

        assert count == 0
        # Config should still be cached for lookups
        assert "task-123" in registry._config_cache
        # But not in pattern cache since disabled
        assert ("org-456", "external.*") not in registry._pattern_cache


class TestGetTriggerConfig:
    """Tests for getting trigger configuration."""

    @pytest.mark.asyncio
    async def test_get_from_cache(self, registry):
        """Verify config is returned from cache."""
        task_id = "task-123"
        config = {"event_pattern": "external.*", "enabled": True}
        registry._config_cache[task_id] = config

        result = await registry.get_trigger_config(task_id)

        assert result == config

    @pytest.mark.asyncio
    async def test_get_from_redis(self, registry, mock_redis):
        """Verify config is fetched from Redis when not cached."""
        task_id = "task-123"
        config = {"event_pattern": "external.*", "enabled": True}
        mock_redis.get.return_value = '{"event_pattern": "external.*", "enabled": true}'

        result = await registry.get_trigger_config(task_id)

        assert result == config
        # Should now be cached
        assert task_id in registry._config_cache

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, registry, mock_redis):
        """Verify None is returned for non-existent triggers."""
        mock_redis.get.return_value = None

        result = await registry.get_trigger_config("nonexistent")

        assert result is None
