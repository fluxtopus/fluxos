"""Unit tests for TaskService fast path functionality.

Tests the fast path data retrieval flow that bypasses LLM planning
for simple queries like "get events today".
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, date, timedelta

from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.planning_models import (
    DataQuery,
    FastPathResult,
    is_fast_path_eligible,
    compute_date_range,
    IntentType,
)
from src.domain.tasks.models import Task, TaskStatus, TaskStep, StepStatus


class TestIsFastPathEligible:
    """Tests for is_fast_path_eligible function."""

    def test_eligible_simple_event_query(self):
        """Test that simple event queries are eligible."""
        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "event",
                "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            },
            "workflow_steps": ["query_events"],
        }
        assert is_fast_path_eligible(intent_info) is True

    def test_eligible_contact_list(self):
        """Test that contact list queries are eligible."""
        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "contact",
                "limit": 100,
            },
            "workflow_steps": ["list_contacts"],
        }
        assert is_fast_path_eligible(intent_info) is True

    def test_eligible_search_query(self):
        """Test that search queries are eligible."""
        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "event",
                "search_text": "standup",
            },
            "workflow_steps": ["search_events"],
        }
        assert is_fast_path_eligible(intent_info) is True

    def test_not_eligible_workflow_intent(self):
        """Test that workflow intents are not eligible."""
        intent_info = {
            "intent_type": "workflow",
            "data_query": None,
            "workflow_steps": ["fetch_data", "summarize"],
        }
        assert is_fast_path_eligible(intent_info) is False

    def test_not_eligible_scheduling_intent(self):
        """Test that scheduling intents are not eligible."""
        intent_info = {
            "intent_type": "scheduling",
            "has_schedule": True,
            "data_query": None,
        }
        assert is_fast_path_eligible(intent_info) is False

    def test_not_eligible_no_data_query(self):
        """Test that missing data_query makes it ineligible."""
        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": None,
        }
        assert is_fast_path_eligible(intent_info) is False

    def test_not_eligible_no_object_type(self):
        """Test that missing object_type makes it ineligible."""
        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "date_range": {"start": "2024-01-01", "end": "2024-01-01"},
            },
        }
        assert is_fast_path_eligible(intent_info) is False

    def test_not_eligible_complex_workflow_steps(self):
        """Test that complex verbs in workflow_steps make it ineligible."""
        complex_verbs = ["summarize", "analyze", "compare", "create", "research", "generate"]
        for verb in complex_verbs:
            intent_info = {
                "intent_type": "data_retrieval",
                "data_query": {
                    "object_type": "event",
                },
                "workflow_steps": [f"{verb}_events"],
            }
            assert is_fast_path_eligible(intent_info) is False, f"Should not be eligible with {verb}"

    def test_not_eligible_none_intent(self):
        """Test that None intent is not eligible."""
        assert is_fast_path_eligible(None) is False

    def test_not_eligible_empty_intent(self):
        """Test that empty intent is not eligible."""
        assert is_fast_path_eligible({}) is False


class TestDataQuery:
    """Tests for DataQuery dataclass."""

    def test_from_intent_valid(self):
        """Test creating DataQuery from valid intent."""
        data_query_dict = {
            "object_type": "event",
            "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            "search_text": "standup",
            "where": {"status": {"$eq": "confirmed"}},
            "limit": 50,
            "order_by": "data.start_time",
        }

        query = DataQuery.from_intent(data_query_dict)

        assert query is not None
        assert query.object_type == "event"
        assert query.date_range["start"] == "2024-01-01T00:00:00Z"
        assert query.search_text == "standup"
        assert query.limit == 50
        assert query.order_by == "data.start_time"

    def test_from_intent_minimal(self):
        """Test creating DataQuery with minimal fields."""
        data_query_dict = {"object_type": "contact"}

        query = DataQuery.from_intent(data_query_dict)

        assert query is not None
        assert query.object_type == "contact"
        assert query.date_range is None
        assert query.search_text is None
        assert query.where is None
        assert query.limit == 100  # Default
        assert query.order_by is None

    def test_from_intent_none(self):
        """Test that None returns None."""
        assert DataQuery.from_intent(None) is None

    def test_from_intent_missing_object_type(self):
        """Test that missing object_type returns None."""
        assert DataQuery.from_intent({"limit": 100}) is None

    def test_build_where_clause_with_date_range(self):
        """Test building where clause with date range."""
        query = DataQuery(
            object_type="event",
            date_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
        )

        where = query.build_where_clause()

        assert where is not None
        assert "start" in where
        assert where["start"]["$gte"] == "2024-01-01T00:00:00Z"
        assert where["start"]["$lte"] == "2024-01-01T23:59:59Z"

    def test_build_where_clause_with_existing_where(self):
        """Test building where clause with existing where conditions."""
        query = DataQuery(
            object_type="event",
            where={"status": {"$eq": "confirmed"}},
            date_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
        )

        where = query.build_where_clause()

        assert where is not None
        assert "status" in where
        assert "start" in where

    def test_build_where_clause_no_filters(self):
        """Test building where clause with no filters returns None."""
        query = DataQuery(object_type="contact")

        where = query.build_where_clause()

        assert where is None


class TestFastPathResult:
    """Tests for FastPathResult dataclass."""

    def test_total_time_ms(self):
        """Test total_time_ms property."""
        result = FastPathResult(
            success=True,
            data=[{"id": "1"}],
            total_count=1,
            query_time_ms=50,
            intent_time_ms=200,
        )

        assert result.total_time_ms == 250

    def test_to_dict(self):
        """Test to_dict method."""
        result = FastPathResult(
            success=True,
            data=[{"id": "1", "type": "event"}],
            total_count=1,
            query_time_ms=50,
            intent_time_ms=200,
            error=None,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["data"] == [{"id": "1", "type": "event"}]
        assert d["total_count"] == 1
        assert d["query_time_ms"] == 50
        assert d["intent_time_ms"] == 200
        assert d["total_time_ms"] == 250
        assert d["error"] is None

    def test_to_dict_with_error(self):
        """Test to_dict with error."""
        result = FastPathResult(
            success=False,
            query_time_ms=10,
            error="Database connection failed",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["error"] == "Database connection failed"
        assert d["data"] == []
        assert d["total_count"] == 0

    def test_to_dict_with_object_type(self):
        """Test to_dict includes object_type for frontend rendering hints."""
        result = FastPathResult(
            success=True,
            data=[{"id": "1", "title": "Standup"}],
            total_count=1,
            query_time_ms=50,
            intent_time_ms=200,
            object_type="event",
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["object_type"] == "event"
        assert d["data"] == [{"id": "1", "title": "Standup"}]

    def test_to_dict_object_type_none_by_default(self):
        """Test object_type is None by default."""
        result = FastPathResult(
            success=True,
            data=[],
            total_count=0,
            query_time_ms=10,
        )

        d = result.to_dict()

        assert d["object_type"] is None

    def test_object_type_contact(self):
        """Test object_type for contact queries."""
        result = FastPathResult(
            success=True,
            data=[{"id": "1", "name": "John Doe", "email": "john@example.com"}],
            total_count=1,
            query_time_ms=30,
            intent_time_ms=100,
            object_type="contact",
        )

        d = result.to_dict()

        assert d["object_type"] == "contact"


class TestComputeDateRange:
    """Tests for compute_date_range function."""

    def test_today(self):
        """Test 'today' date range."""
        ref = date(2024, 6, 15)  # Saturday
        result = compute_date_range("today", ref)

        assert result is not None
        assert result["start"].startswith("2024-06-15T00:00:00")
        assert result["end"].startswith("2024-06-15T23:59:59")

    def test_yesterday(self):
        """Test 'yesterday' date range."""
        ref = date(2024, 6, 15)
        result = compute_date_range("yesterday", ref)

        assert result is not None
        assert result["start"].startswith("2024-06-14T00:00:00")
        assert result["end"].startswith("2024-06-14T23:59:59")

    def test_tomorrow(self):
        """Test 'tomorrow' date range."""
        ref = date(2024, 6, 15)
        result = compute_date_range("tomorrow", ref)

        assert result is not None
        assert result["start"].startswith("2024-06-16T00:00:00")
        assert result["end"].startswith("2024-06-16T23:59:59")

    def test_this_week(self):
        """Test 'this week' date range."""
        ref = date(2024, 6, 15)  # Saturday
        result = compute_date_range("this week", ref)

        assert result is not None
        # Week starts Monday (June 10) and ends Sunday (June 16)
        assert result["start"].startswith("2024-06-10T00:00:00")
        assert result["end"].startswith("2024-06-16T23:59:59")

    def test_this_month(self):
        """Test 'this month' date range."""
        ref = date(2024, 6, 15)
        result = compute_date_range("this month", ref)

        assert result is not None
        assert result["start"].startswith("2024-06-01")
        # End should be June 30
        assert "2024-06-30" in result["end"]

    def test_none_description(self):
        """Test None description returns None."""
        assert compute_date_range(None) is None

    def test_unrecognized_description(self):
        """Test unrecognized description returns None."""
        assert compute_date_range("next fortnight") is None


class TestTaskServiceFastPath:
    """Tests for TaskService fast path methods."""

    @pytest.mark.asyncio
    async def test_try_fast_path_not_eligible(self):
        """Test that ineligible intents fall back to normal path."""
        service = TaskService()

        # Non-eligible intent (workflow type)
        intent_info = {
            "intent_type": "workflow",
            "data_query": None,
            "workflow_steps": ["summarize", "email"],
        }

        result = await service._try_fast_path(
            user_id="test-user",
            organization_id="test-org",
            goal="Summarize news and email it",
            intent_info=intent_info,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_try_fast_path_none_intent(self):
        """Test that None intent falls back to normal path."""
        service = TaskService()

        result = await service._try_fast_path(
            user_id="test-user",
            organization_id="test-org",
            goal="Get events today",
            intent_info=None,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_try_fast_path_eligible_success(self):
        """Test successful fast path execution."""
        service = TaskService()

        # Mock Redis store
        service._redis_store = Mock()
        service._redis_store.create_task = AsyncMock()

        # Mock PG store
        service._pg_store = Mock()
        service._pg_store.create_task = AsyncMock()

        # Mock workspace service
        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=[
            {"id": "event-1", "type": "event", "data": {"title": "Meeting"}},
            {"id": "event-2", "type": "event", "data": {"title": "Standup"}},
        ])

        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "event",
                "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get events for today",
        }

        with patch('src.interfaces.database.Database') as mock_db_cls:
            mock_db = Mock()
            mock_db.get_session = MagicMock()
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=Mock())
            mock_db.get_session.return_value.__aexit__ = AsyncMock()
            mock_db_cls.return_value = mock_db

            with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                result = await service._try_fast_path(
                    user_id="test-user",
                    organization_id="test-org",
                    goal="Get events today",
                    intent_info=intent_info,
                )

        assert result is not None
        assert isinstance(result, Task)
        assert result.status == TaskStatus.COMPLETED
        assert result.metadata.get("fast_path") is True
        assert result.metadata.get("result_count") == 2
        # result_data is now a dict with object_type, data, and total_count
        result_data = result.metadata.get("result_data", {})
        assert result_data.get("object_type") == "event"
        assert len(result_data.get("data", [])) == 2
        assert result_data.get("total_count") == 2

    @pytest.mark.asyncio
    async def test_try_fast_path_query_failure_falls_back(self):
        """Test that query failure falls back to normal path."""
        service = TaskService()

        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "event",
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get events",
        }

        with patch('src.interfaces.database.Database') as mock_db_cls:
            mock_db_cls.side_effect = Exception("Database connection failed")

            result = await service._try_fast_path(
                user_id="test-user",
                organization_id="test-org",
                goal="Get events",
                intent_info=intent_info,
            )

        # Should fall back gracefully, returning None
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_fast_path_query_structured(self):
        """Test structured query execution."""
        service = TaskService()

        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=[
            {"id": "1", "type": "event", "data": {"title": "Meeting"}},
        ])

        data_query = DataQuery(
            object_type="event",
            date_range={"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            limit=50,
        )

        with patch('src.interfaces.database.Database') as mock_db_cls:
            mock_session = Mock()
            mock_db = Mock()
            mock_db.get_session = MagicMock()
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock()
            mock_db_cls.return_value = mock_db

            with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                result = await service._execute_fast_path_query(
                    organization_id="test-org",
                    data_query=data_query,
                )

        assert result.success is True
        assert result.total_count == 1
        assert result.query_time_ms >= 0
        mock_workspace.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_fast_path_query_search(self):
        """Test full-text search query execution."""
        service = TaskService()

        mock_workspace = Mock()
        mock_workspace.search = AsyncMock(return_value=[
            {"id": "1", "type": "event", "data": {"title": "Standup Meeting"}},
        ])

        data_query = DataQuery(
            object_type="event",
            search_text="standup",
            limit=50,
        )

        with patch('src.interfaces.database.Database') as mock_db_cls:
            mock_session = Mock()
            mock_db = Mock()
            mock_db.get_session = MagicMock()
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock()
            mock_db_cls.return_value = mock_db

            with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                result = await service._execute_fast_path_query(
                    organization_id="test-org",
                    data_query=data_query,
                )

        assert result.success is True
        mock_workspace.search.assert_called_once_with(
            org_id="test-org",
            query="standup",
            type="event",
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_create_fast_path_task(self):
        """Test creating completed task from fast path result."""
        service = TaskService()

        service._redis_store = Mock()
        service._redis_store.create_task = AsyncMock()

        service._pg_store = Mock()
        service._pg_store.create_task = AsyncMock()

        intent_info = {
            "intent_type": "data_retrieval",
            "data_query": {
                "object_type": "event",
                "date_range": {"start": "2024-01-01", "end": "2024-01-01"},
            },
            "rephrased_intent": "Get events for today",
        }

        fast_result = FastPathResult(
            success=True,
            data=[{"id": "1", "type": "event"}],
            total_count=1,
            query_time_ms=50,
            intent_time_ms=200,
        )

        task = await service._create_fast_path_task(
            user_id="test-user",
            organization_id="test-org",
            goal="Get events today",
            intent_info=intent_info,
            fast_result=fast_result,
        )

        assert task.status == TaskStatus.COMPLETED
        assert task.user_id == "test-user"
        assert task.organization_id == "test-org"
        assert task.goal == "Get events today"
        assert task.metadata["fast_path"] is True
        assert task.metadata["result_count"] == 1
        # result_data is now a dict with object_type, data, and total_count
        result_data = task.metadata["result_data"]
        assert result_data["object_type"] is None  # No object_type in this test fixture
        assert result_data["data"] == [{"id": "1", "type": "event"}]
        assert result_data["total_count"] == 1
        assert task.completed_at is not None
        assert len(task.steps) == 1
        assert task.steps[0].status == StepStatus.DONE

        # Verify stores were called
        service._pg_store.create_task.assert_called_once()
        service._redis_store.create_task.assert_called_once()


class TestCreateTaskFastPathIntegration:
    """Tests for create_task with fast path routing."""

    @pytest.mark.asyncio
    async def test_try_fast_path_returns_completed_task_for_data_retrieval(self):
        """Test that _try_fast_path returns a COMPLETED task for data retrieval."""
        service = TaskService()

        # Mock stores
        service._redis_store = Mock()
        service._redis_store.create_task = AsyncMock()

        service._pg_store = Mock()
        service._pg_store.create_task = AsyncMock()

        # Data retrieval intent
        mock_intent = {
            "intent_type": "data_retrieval",
            "has_schedule": False,
            "schedule": None,
            "data_query": {
                "object_type": "event",
                "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            },
            "workflow_steps": ["query_events"],
            "rephrased_intent": "Get events for today",
        }

        # Mock workspace service
        mock_workspace = Mock()
        mock_workspace.query = AsyncMock(return_value=[
            {"id": "event-1", "type": "event", "data": {"title": "Meeting"}},
        ])

        with patch('src.interfaces.database.Database') as mock_db_cls:
            mock_db = Mock()
            mock_session = AsyncMock()
            mock_async_cm = AsyncMock()
            mock_async_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_async_cm.__aexit__ = AsyncMock(return_value=None)
            mock_db.get_session = Mock(return_value=mock_async_cm)
            mock_db_cls.return_value = mock_db

            with patch('src.infrastructure.workspace.workspace_service.WorkspaceService', return_value=mock_workspace):
                task = await service._try_fast_path(
                    user_id="test-user",
                    organization_id="test-org",
                    goal="Get me all events for today",
                    intent_info=mock_intent,
                )

        # Should have used fast path
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.metadata.get("fast_path") is True

    @pytest.mark.asyncio
    async def test_create_task_skips_fast_path_for_workflow(self):
        """Test that create_task skips fast path for workflow intents."""
        service = TaskService()

        # Mock intent extractor returning workflow intent
        mock_intent = {
            "intent_type": "workflow",
            "has_schedule": False,
            "schedule": None,
            "data_query": None,
            "workflow_steps": ["fetch_news", "summarize", "email"],
            "rephrased_intent": "Fetch news, summarize, and email",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        # This should NOT trigger fast path, so we just test the eligibility check
        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            intent_info = await service._detect_scheduling_intent(
                "Summarize top HN stories and email them"
            )

        assert intent_info["intent_type"] == "workflow"
        assert is_fast_path_eligible(intent_info) is False
