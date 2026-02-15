"""Integration tests for task triggers."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
import json

from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry
from src.application.tasks.runtime import TaskRuntime as TaskService
from src.interfaces.event_bus import Event, EventSourceType
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus


@pytest.fixture
async def redis_registry():
    """Create a real TaskTriggerRegistry with Redis."""
    registry = TaskTriggerRegistry()
    await registry.initialize()
    yield registry
    await registry.cleanup()


@pytest.mark.integration
class TestTaskTriggerFlow:
    """Integration tests for the full trigger flow."""

    @pytest.mark.asyncio
    async def test_register_and_find_trigger(self, redis_registry):
        """Test registering a trigger and finding it via event matching."""
        task_id = "test-task-001"
        org_id = "test-org-001"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.integration.webhook",
            "enabled": True,
        }

        # Register
        success = await redis_registry.register_trigger(task_id, org_id, trigger_config)
        assert success is True

        # Create matching event
        event = Event(
            id="evt-001",
            event_type="external.integration.webhook",
            source="integration:discord-bot",
            metadata={"organization_id": org_id},
        )

        # Find matching tasks
        matches = await redis_registry.find_matching_tasks(event)
        assert task_id in matches

        # Cleanup
        await redis_registry.unregister_trigger(task_id)

    @pytest.mark.asyncio
    async def test_wildcard_pattern_matching(self, redis_registry):
        """Test wildcard patterns match multiple event types."""
        task_id = "test-task-002"
        org_id = "test-org-002"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.integration.*",
            "enabled": True,
        }

        await redis_registry.register_trigger(task_id, org_id, trigger_config)

        # Test different event types
        for event_type in ["external.integration.webhook", "external.integration.message"]:
            event = Event(
                id=f"evt-{event_type}",
                event_type=event_type,
                source="integration:test",
                metadata={"organization_id": org_id},
            )
            matches = await redis_registry.find_matching_tasks(event)
            assert task_id in matches, f"Expected {task_id} to match {event_type}"

        # Non-matching event
        event = Event(
            id="evt-nomatch",
            event_type="external.webhook.stripe",
            source="stripe",
            metadata={"organization_id": org_id},
        )
        matches = await redis_registry.find_matching_tasks(event)
        assert task_id not in matches

        await redis_registry.unregister_trigger(task_id)

    @pytest.mark.asyncio
    async def test_source_filter(self, redis_registry):
        """Test source_filter restricts which events trigger the task."""
        task_id = "test-task-003"
        org_id = "test-org-003"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.integration.*",
            "source_filter": "integration:specific-bot",
            "enabled": True,
        }

        await redis_registry.register_trigger(task_id, org_id, trigger_config)

        # Matching source
        event = Event(
            id="evt-match",
            event_type="external.integration.webhook",
            source="integration:specific-bot",
            metadata={"organization_id": org_id},
        )
        matches = await redis_registry.find_matching_tasks(event)
        assert task_id in matches

        # Non-matching source
        event = Event(
            id="evt-nomatch",
            event_type="external.integration.webhook",
            source="integration:other-bot",
            metadata={"organization_id": org_id},
        )
        matches = await redis_registry.find_matching_tasks(event)
        assert task_id not in matches

        await redis_registry.unregister_trigger(task_id)

    @pytest.mark.asyncio
    async def test_org_isolation(self, redis_registry):
        """Test tasks only match events from the same organization."""
        task_id = "test-task-004"
        org_a = "org-A"
        org_b = "org-B"

        trigger_config = {
            "type": "event",
            "event_pattern": "external.*",
            "enabled": True,
        }

        await redis_registry.register_trigger(task_id, org_a, trigger_config)

        # Event from same org matches
        event_a = Event(
            id="evt-orgA",
            event_type="external.webhook",
            source="test",
            metadata={"organization_id": org_a},
        )
        matches = await redis_registry.find_matching_tasks(event_a)
        assert task_id in matches

        # Event from different org doesn't match
        event_b = Event(
            id="evt-orgB",
            event_type="external.webhook",
            source="test",
            metadata={"organization_id": org_b},
        )
        matches = await redis_registry.find_matching_tasks(event_b)
        assert task_id not in matches

        await redis_registry.unregister_trigger(task_id)

    @pytest.mark.asyncio
    async def test_load_triggers_on_startup(self, redis_registry):
        """Test triggers are loaded from Redis on startup."""
        task_id = "test-task-005"
        org_id = "test-org-005"
        trigger_config = {
            "type": "event",
            "event_pattern": "external.startup.*",
            "enabled": True,
        }

        # Register trigger
        await redis_registry.register_trigger(task_id, org_id, trigger_config)

        # Clear in-memory cache to simulate restart
        redis_registry._config_cache.clear()
        redis_registry._pattern_cache.clear()

        # Load from Redis
        count = await redis_registry.load_all_triggers()
        assert count >= 1

        # Verify trigger is back in cache
        assert task_id in redis_registry._config_cache
        assert (org_id, "external.startup.*") in redis_registry._pattern_cache

        await redis_registry.unregister_trigger(task_id)


@pytest.mark.integration
class TestTaskServiceTriggerIntegration:
    """Test TaskService auto-registers triggers."""

    @pytest.mark.asyncio
    async def test_create_task_with_trigger_registers(self):
        """Test creating a task with trigger config auto-registers."""
        # Create mock trigger registry
        mock_registry = AsyncMock()
        mock_registry.register_trigger = AsyncMock(return_value=True)

        # Create TaskService with mock registry
        with patch.object(TaskService, '_ensure_initialized', new_callable=AsyncMock):
            service = TaskService(trigger_registry=mock_registry)
            service._redis_store = AsyncMock()
            service._redis_store.create_task = AsyncMock()
            service._redis_store.update_task = AsyncMock()
            service._pg_store = None
            service._risk_detector = AsyncMock()
            service._risk_detector.assess_plan = lambda x: {}
            service._tree_adapter = AsyncMock()
            service._tree_adapter.create_task_tree = AsyncMock(return_value="tree-123")
            service._initialized = True

            # Create task with trigger in metadata
            task = await service.create_task_with_steps(
                user_id="user-123",
                organization_id="org-123",
                goal="Test trigger task",
                steps=[
                    {
                        "name": "step1",
                        "agent_type": "llm",
                        "inputs": {"prompt": "test"},
                    }
                ],
            )

            # Manually add trigger to metadata and call register
            task.metadata = {"trigger": {"event_pattern": "external.*", "enabled": True}}
            await service._register_task_trigger(task)

            # Verify registry was called
            mock_registry.register_trigger.assert_called_once_with(
                task_id=task.id,
                organization_id="org-123",
                trigger_config={"event_pattern": "external.*", "enabled": True},
            )

    @pytest.mark.asyncio
    async def test_cancel_task_unregisters_trigger(self):
        """Test cancelling a task unregisters its trigger."""
        mock_registry = AsyncMock()
        mock_registry.unregister_trigger = AsyncMock(return_value=True)

        task = Task(
            id="task-to-cancel",
            user_id="user-123",
            organization_id="org-123",
            goal="Test",
            steps=[],
            status=TaskStatus.READY,
            metadata={"trigger": {"event_pattern": "external.*"}},
        )

        with patch.object(TaskService, '_ensure_initialized', new_callable=AsyncMock):
            service = TaskService(trigger_registry=mock_registry)
            service._redis_store = AsyncMock()
            service._pg_store = AsyncMock()
            service._pg_store.get_task = AsyncMock(return_value=task)
            service._state_machine = AsyncMock()
            service._state_machine.transition = AsyncMock(return_value=task)
            service._initialized = True
            service._active_executions = {}

            await service.cancel_plan(task.id, "user-123")

            mock_registry.unregister_trigger.assert_called_once_with(task.id)
