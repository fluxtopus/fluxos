"""
Integration tests for fast path data retrieval.

These tests verify the end-to-end fast path flow:
1. Intent extraction detects data_retrieval intent
2. Fast path query executes against real workspace data
3. Task is created with COMPLETED status and result_data

Note: These tests use real database connections when available.
"""

import pytest
import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch, Mock, MagicMock
import uuid

from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus
from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.planning_models import (
    DataQuery,
    FastPathResult,
    is_fast_path_eligible,
)


@pytest.fixture
async def task_service():
    """Create TaskService with mocked dependencies for integration tests."""
    service = TaskService(inline_fast_path_precheck=True)

    # Mock stores for isolation
    service._redis_store = Mock()
    service._redis_store.create_task = AsyncMock()
    service._redis_store._connect = AsyncMock()
    service._redis_store.update_task = AsyncMock()

    service._pg_store = Mock()
    service._pg_store.create_task = AsyncMock()
    service._pg_store.update_task = AsyncMock()

    # Mark as initialized
    service._initialized = True

    yield service


@pytest.fixture
def sample_events():
    """Sample event data for tests."""
    today = date.today()
    return [
        {
            "id": str(uuid.uuid4()),
            "org_id": "test-org",
            "type": "event",
            "data": {
                "title": "Daily Standup",
                "description": "Team standup meeting",
                "start_time": f"{today}T09:00:00Z",
                "end_time": f"{today}T09:30:00Z",
            },
            "tags": ["meeting", "daily"],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "org_id": "test-org",
            "type": "event",
            "data": {
                "title": "Project Review",
                "description": "Weekly project review",
                "start_time": f"{today}T14:00:00Z",
                "end_time": f"{today}T15:00:00Z",
            },
            "tags": ["meeting", "weekly"],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "org_id": "test-org",
            "type": "event",
            "data": {
                "title": "1:1 with Manager",
                "description": "Regular 1:1 sync",
                "start_time": f"{today}T16:00:00Z",
                "end_time": f"{today}T16:30:00Z",
            },
            "tags": ["meeting", "1:1"],
            "created_at": datetime.utcnow().isoformat(),
        },
    ]


@pytest.fixture
def sample_contacts():
    """Sample contact data for tests."""
    return [
        {
            "id": str(uuid.uuid4()),
            "org_id": "test-org",
            "type": "contact",
            "data": {
                "name": "Alice Smith",
                "email": "alice@example.com",
                "phone": "555-0001",
            },
            "tags": ["team"],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "org_id": "test-org",
            "type": "contact",
            "data": {
                "name": "Bob Jones",
                "email": "bob@example.com",
                "phone": "555-0002",
            },
            "tags": ["team"],
            "created_at": datetime.utcnow().isoformat(),
        },
    ]


class TestFastPathIntegration:
    """Integration tests for the fast path data retrieval flow."""

    @pytest.mark.asyncio
    async def test_fast_path_events_today(self, task_service, sample_events):
        """Test fast path for 'get events today' query."""

        # Mock intent extractor to return data_retrieval intent
        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "date_range": {
                    "start": f"{date.today()}T00:00:00Z",
                    "end": f"{date.today()}T23:59:59Z",
                },
                "limit": 100,
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Retrieve all events for today",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        # Mock workspace service to return sample events
        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=sample_events)

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="get me all events for today",
                    )

        # Verify fast path was used
        assert task.status == TaskStatus.COMPLETED
        assert task.metadata.get("fast_path") is True
        assert task.metadata.get("result_count") == 3
        assert len(task.metadata.get("result_data", [])) == 3

        # Verify task has the query step
        assert len(task.steps) == 1
        assert task.steps[0].name == "Query Data"
        assert task.steps[0].status == StepStatus.DONE
        assert task.steps[0].outputs.get("count") == 3

    @pytest.mark.asyncio
    async def test_fast_path_show_contacts(self, task_service, sample_contacts):
        """Test fast path for 'show my contacts' query."""

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "contact",
                "limit": 100,
            },
            "workflow_steps": ["list_contacts"],
            "rephrased_intent": "List all contacts",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=sample_contacts)

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="show my contacts",
                    )

        assert task.status == TaskStatus.COMPLETED
        assert task.metadata.get("fast_path") is True
        assert task.metadata.get("result_count") == 2

    @pytest.mark.asyncio
    async def test_fast_path_search_events(self, task_service, sample_events):
        """Test fast path for search query like 'find events about standup'."""

        # Filter to just the standup event
        standup_events = [e for e in sample_events if "standup" in e["data"]["title"].lower()]

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "search_text": "standup",
                "limit": 50,
            },
            "workflow_steps": ["search_events"],
            "rephrased_intent": "Search for events containing 'standup'",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        mock_workspace = Mock()
        mock_workspace.search = AsyncMock(return_value=standup_events)

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="find events about standup",
                    )

        # Verify search was called instead of query
        mock_workspace.search.assert_called_once()
        assert task.status == TaskStatus.COMPLETED
        assert task.metadata.get("fast_path") is True
        assert task.metadata.get("result_count") == 1

    @pytest.mark.asyncio
    async def test_fast_path_skipped_for_workflow(self, task_service):
        """Test that complex workflow queries skip fast path."""

        mock_intent = {
            "intent_type": "workflow",
            "has_schedule": False,
            "schedule": None,
            "data_query": None,
            "workflow_steps": ["fetch_news", "summarize", "send_email"],
            "rephrased_intent": "Fetch HN stories, summarize them, and email the digest",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            # Fast path should not be eligible
            intent_info = await task_service._detect_scheduling_intent(
                "summarize top HN stories and email them"
            )

        assert intent_info["intent_type"] == "workflow"
        assert is_fast_path_eligible(intent_info) is False

    @pytest.mark.asyncio
    async def test_fast_path_fallback_on_error(self, task_service):
        """Test that fast path failures fall back to normal flow gracefully."""

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get events",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        # Simulate database error
        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db_cls.side_effect = Exception("Database connection failed")

                # Fast path should fail and return None
                result = await task_service._try_fast_path(
                    user_id="test-user",
                    organization_id="test-org",
                    goal="get events",
                    intent_info=mock_intent,
                )

        # Should gracefully return None (fall back to normal path)
        assert result is None

    @pytest.mark.asyncio
    async def test_fast_path_timing_metrics(self, task_service, sample_events):
        """Test that fast path includes timing metrics."""

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "limit": 100,
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get all events",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=sample_events)

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="get all events",
                    )

        # Verify timing metrics are present
        assert task.metadata.get("fast_path_stats") is not None
        stats = task.metadata["fast_path_stats"]
        assert "query_time_ms" in stats
        assert stats["query_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_fast_path_creates_audit_trail(self, task_service, sample_events):
        """Test that fast path creates proper audit trail (task record)."""

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "limit": 100,
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get all events",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=sample_events)

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="get all events",
                    )

        # Verify task was stored in both PostgreSQL and Redis
        task_service._pg_store.create_task.assert_called_once()
        task_service._redis_store.create_task.assert_called_once()

        # Verify the stored task has correct properties
        stored_task = task_service._pg_store.create_task.call_args[0][0]
        assert stored_task.id == task.id
        assert stored_task.goal == "get all events"
        assert stored_task.status == TaskStatus.COMPLETED
        assert stored_task.metadata.get("fast_path") is True


class TestFastPathPerformance:
    """Performance-focused tests for fast path."""

    @pytest.mark.asyncio
    async def test_fast_path_performance_target(self, task_service, sample_events):
        """Test that fast path meets the 800ms target."""
        import time

        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "limit": 100,
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get all events",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        mock_workspace = Mock()
        # Simulate a realistic query response time (~50ms)
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(0.05)
            return sample_events
        mock_workspace.query = slow_query

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            with patch('src.interfaces.database.Database') as mock_db_cls:
                mock_db = Mock()
                mock_db.get_session = MagicMock()
                mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
                mock_db.get_session.return_value.__aexit__ = AsyncMock()
                mock_db_cls.return_value = mock_db

                with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                    start = time.time()
                    task = await task_service.create_task(
                        user_id="test-user",
                        organization_id="test-org",
                        goal="get all events",
                    )
                    elapsed_ms = (time.time() - start) * 1000

        # Verify fast path was used
        assert task.status == TaskStatus.COMPLETED
        assert task.metadata.get("fast_path") is True

        # Note: This test uses mocked intent extraction, so actual time will be
        # much faster than real LLM call. In production benchmarks, verify
        # total time including intent extraction is < 800ms.
        # Here we just verify the query portion is fast.
        assert elapsed_ms < 500, f"Fast path took {elapsed_ms:.0f}ms, expected < 500ms"
