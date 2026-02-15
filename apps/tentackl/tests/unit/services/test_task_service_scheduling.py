"""Unit tests for TaskService scheduling functionality.

Tests the scheduling intent detection and scheduled workflow creation flow.
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.models import Task, TaskStatus
from src.domain.tasks.planning_models import PlanningIntent, ScheduleSpec


def _mock_planning_event_bus():
    bus = Mock()
    bus.planning_started = AsyncMock()
    bus.planning_intent_detected = AsyncMock()
    bus.planning_fast_path = AsyncMock()
    bus.planning_llm_started = AsyncMock()
    bus.planning_llm_retry = AsyncMock()
    bus.planning_steps_generated = AsyncMock()
    bus.planning_risk_detection = AsyncMock()
    bus.planning_completed = AsyncMock()
    bus.planning_failed = AsyncMock()
    return bus


class TestDetectSchedulingIntent:
    """Tests for _detect_scheduling_intent method."""

    @pytest.mark.asyncio
    async def test_detects_daily_schedule(self):
        """Test that daily schedule is detected."""
        service = TaskService()

        # Mock the intent extractor
        mock_intent = {
            "has_schedule": True,
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            "workflow_steps": ["research", "generate_report"],
            "rephrased_intent": "Research competitors daily",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            result = await service._detect_scheduling_intent(
                "Every morning at 9am, research competitors"
            )

        assert result is not None
        assert result["has_schedule"] is True
        assert result["schedule"]["cron"] == "0 9 * * *"
        assert result["schedule"]["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_detects_weekly_schedule(self):
        """Test that weekly schedule is detected."""
        service = TaskService()

        mock_intent = {
            "has_schedule": True,
            "schedule": {"cron": "0 10 * * 1", "timezone": "America/New_York"},
            "workflow_steps": ["analyze", "report"],
            "rephrased_intent": "Weekly analysis on Mondays",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            result = await service._detect_scheduling_intent(
                "Every Monday at 10am EST, analyze metrics"
            )

        assert result is not None
        assert result["has_schedule"] is True
        assert "1" in result["schedule"]["cron"]  # Monday = 1

    @pytest.mark.asyncio
    async def test_no_schedule_detected(self):
        """Test that non-scheduled tasks return has_schedule=False."""
        service = TaskService()

        mock_intent = {
            "has_schedule": False,
            "schedule": None,
            "workflow_steps": ["fetch", "summarize"],
            "rephrased_intent": "Fetch and summarize HN stories",
        }

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(return_value=mock_intent)
        mock_extractor.cleanup = AsyncMock()

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            result = await service._detect_scheduling_intent(
                "Fetch top HN stories and summarize them"
            )

        assert result is not None
        assert result["has_schedule"] is False
        assert result["schedule"] is None

    @pytest.mark.asyncio
    async def test_handles_extraction_error(self):
        """Test that extraction errors return None."""
        service = TaskService()

        mock_extractor = Mock()
        mock_extractor.initialize = AsyncMock()
        mock_extractor.extract_intent = AsyncMock(side_effect=Exception("LLM error"))
        mock_extractor.cleanup = AsyncMock()

        with patch('src.agents.intent_extractor_agent.IntentExtractorAgent', return_value=mock_extractor):
            result = await service._detect_scheduling_intent("Some goal")

        assert result is None


class TestCreateAutomationForTask:
    """Tests for _create_automation_for_task method."""

    @pytest.mark.asyncio
    async def test_creates_recurring_automation(self):
        service = TaskService()
        service._redis_store = Mock()
        service._redis_store.update_task = AsyncMock()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.get_session = Mock(return_value=session_cm)

        mock_pg_store = Mock()
        mock_pg_store.db = mock_db
        mock_pg_store.update_task = AsyncMock()
        service._pg_store = mock_pg_store

        task_id = str(uuid.uuid4())
        cron = "0 9 * * *"

        with patch("src.core.cron_utils.calculate_next_run", return_value=datetime.utcnow()):
            await service._create_automation_for_task(
                task_id=task_id,
                user_id="user-123",
                organization_id="org-123",
                goal="Every morning, research competitors",
                cron=cron,
                timezone="UTC",
                execute_at=None,
            )

        assert mock_session.add.called
        added = mock_session.add.call_args.args[0]
        assert added.owner_id == "user-123"
        assert str(added.task_id) == task_id
        assert added.cron == cron
        assert added.execute_at is None
        assert added.timezone == "UTC"
        assert added.enabled is True

        service._redis_store.update_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_one_time_automation(self):
        service = TaskService()
        service._redis_store = Mock()
        service._redis_store.update_task = AsyncMock()

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.get_session = Mock(return_value=session_cm)

        mock_pg_store = Mock()
        mock_pg_store.db = mock_db
        mock_pg_store.update_task = AsyncMock()
        service._pg_store = mock_pg_store

        execute_at = datetime.utcnow()
        task_id = str(uuid.uuid4())

        await service._create_automation_for_task(
            task_id=task_id,
            user_id="user-123",
            organization_id=None,
            goal="Schedule a one-time report",
            cron=None,
            timezone="UTC",
            execute_at=execute_at,
        )

        added = mock_session.add.call_args.args[0]
        assert added.execute_at == execute_at
        assert added.cron is None


class TestCreateTaskWithScheduling:
    """Tests for create_task method with scheduling detection."""

    def _setup_bg_task_mocks(self, service):
        """Set up common mocks needed for _plan_task_async background task."""
        service._plan_cancellation_port = Mock()
        service._plan_cancellation_port.is_cancelled = AsyncMock(return_value=False)
        service._fast_path_planner_port = Mock()
        service._fast_path_planner_port.try_fast_path = AsyncMock(return_value=None)
        service._auto_start_task = AsyncMock()
        service._planning_event_bus = _mock_planning_event_bus()

        # Mock the task returned by get_task (used during tree creation)
        service._planning_store = Mock()
        service._planning_store.update_task = AsyncMock()
        service._planning_store.get_task = AsyncMock(return_value=Task(
            goal="test", user_id="user-123", organization_id="org-123",
            steps=[], status=TaskStatus.PLANNING,
        ))

    @pytest.mark.asyncio
    async def test_scheduled_task_creates_automation(self):
        """Test that scheduled goals create an automation row after planning."""
        service = TaskService()

        # Mock initialization
        service._initialized = True
        service._redis_store = Mock()
        service._redis_store.create_task = AsyncMock()
        service._redis_store.update_task = AsyncMock()
        service._pg_store = None
        service._tree_adapter = Mock()
        service._tree_adapter.create_task_tree = AsyncMock(return_value="tree-1")
        service._risk_detector = None

        # Mock scheduling intent detection with schedule
        schedule_info = {
            "has_schedule": True,
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
            "one_shot_goal": "Research competitors",
        }
        service._planning_intent_port = Mock()
        service._planning_intent_port.extract_intent = AsyncMock(return_value=PlanningIntent(
            intent_type="workflow",
            has_schedule=True,
            schedule=ScheduleSpec(
                cron=schedule_info["schedule"]["cron"],
                timezone=schedule_info["schedule"]["timezone"],
            ),
            workflow_steps=schedule_info.get("workflow_steps", []),
            rephrased_intent=schedule_info.get("rephrased_intent"),
            one_shot_goal=schedule_info.get("one_shot_goal"),
        ))

        # Mock the planner
        from src.domain.tasks.models import TaskStep
        service._workflow_planner = Mock()
        service._workflow_planner.start_conversation = AsyncMock()
        service._workflow_planner.end_conversation = AsyncMock()
        service._workflow_planner.generate_delegation_steps = AsyncMock(return_value=[
            TaskStep(id="s1", name="Research", description="Research competitors", agent_type="researcher"),
        ])

        # Mock state transition and automation creation
        service._status_transition_port = Mock()
        service._status_transition_port.transition = AsyncMock(return_value=Task(
            goal="Research competitors", user_id="user-123",
            organization_id="org-123", steps=[], status=TaskStatus.READY,
        ))
        service._automation_scheduler_port = Mock()
        service._automation_scheduler_port.create_automation_for_task = AsyncMock()
        self._setup_bg_task_mocks(service)

        await service.create_task(
            user_id="user-123",
            organization_id="org-123",
            goal="Every morning at 9am, research competitors",
        )

        # Await background planning task
        bg_task = list(service._active_planning.values())[0]
        await bg_task

        # Verify automation was created for scheduled task
        service._automation_scheduler_port.create_automation_for_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_scheduled_task_does_not_create_automation(self):
        """Test that non-scheduled tasks skip automation creation."""
        service = TaskService()

        # Mock initialization
        service._initialized = True
        service._redis_store = Mock()
        service._redis_store.create_task = AsyncMock()
        service._redis_store.update_task = AsyncMock()
        service._pg_store = None
        service._tree_adapter = Mock()
        service._tree_adapter.create_task_tree = AsyncMock(return_value="tree-1")
        service._risk_detector = None

        # No scheduling intent
        service._planning_intent_port = Mock()
        service._planning_intent_port.extract_intent = AsyncMock(return_value=PlanningIntent(
            intent_type="workflow",
            has_schedule=False,
            schedule=None,
            workflow_steps=[],
        ))

        # Mock the planner
        from src.domain.tasks.models import TaskStep
        service._workflow_planner = Mock()
        service._workflow_planner.start_conversation = AsyncMock()
        service._workflow_planner.end_conversation = AsyncMock()
        service._workflow_planner.generate_delegation_steps = AsyncMock(return_value=[
            TaskStep(id="s1", name="Fetch", description="Fetch stories", agent_type="fetcher"),
        ])

        # Mock state transition
        service._status_transition_port = Mock()
        service._status_transition_port.transition = AsyncMock(return_value=Task(
            goal="Fetch HN stories", user_id="user-123",
            organization_id="org-123", steps=[], status=TaskStatus.READY,
        ))
        service._automation_scheduler_port = Mock()
        service._automation_scheduler_port.create_automation_for_task = AsyncMock()
        self._setup_bg_task_mocks(service)

        await service.create_task(
            user_id="user-123",
            organization_id="org-123",
            goal="Fetch HN stories and summarize them",
        )

        # Await background planning task
        bg_task = list(service._active_planning.values())[0]
        await bg_task

        # Verify no automation was created
        service._automation_scheduler_port.create_automation_for_task.assert_not_called()
        # But normal planning did happen
        service._workflow_planner.generate_delegation_steps.assert_called()


class TestIntentExtractorScheduleParsing:
    """Tests for IntentExtractorAgent schedule parsing."""

    @pytest.mark.asyncio
    async def test_parses_schedule_fields(self):
        """Test that schedule fields are correctly parsed from LLM output."""
        from src.agents.intent_extractor_agent import IntentExtractorAgent

        agent = IntentExtractorAgent()

        # Test the JSON parsing directly
        test_json = """{
            "rephrased_intent": "Research competitors daily",
            "workflow_steps": ["research", "report"],
            "has_loops": false,
            "requires_user_input": false,
            "complexity": "medium",
            "apis_needed": ["web_search"],
            "has_schedule": true,
            "schedule": {"cron": "0 9 * * *", "timezone": "UTC"}
        }"""

        result = agent._parse_intent_json(test_json)

        assert result["has_schedule"] is True
        assert result["schedule"]["cron"] == "0 9 * * *"
        assert result["schedule"]["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_defaults_schedule_when_missing(self):
        """Test that missing schedule fields default correctly."""
        from src.agents.intent_extractor_agent import IntentExtractorAgent

        agent = IntentExtractorAgent()

        # Test JSON without schedule fields
        test_json = """{
            "rephrased_intent": "Fetch data",
            "workflow_steps": ["fetch"],
            "has_loops": false,
            "requires_user_input": false,
            "complexity": "simple",
            "apis_needed": []
        }"""

        result = agent._parse_intent_json(test_json)

        assert result["has_schedule"] is False
        assert result["schedule"] is None
