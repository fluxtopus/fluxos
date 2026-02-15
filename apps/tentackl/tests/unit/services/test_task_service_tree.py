"""
Unit tests for TaskService tree integration.

Tests the integration of TaskExecutionTreeAdapter into TaskService
for durable task execution via the execution tree architecture.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from types import SimpleNamespace

from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus
from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
from src.infrastructure.tasks.task_planning_store_adapter import TaskPlanningStoreAdapter
from src.application.tasks import TaskExecutionUseCase


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


@pytest.fixture
def mock_redis_store():
    """Create a mock Redis task store."""
    store = AsyncMock()
    store.create_task = AsyncMock()
    store.get_task = AsyncMock(return_value=None)
    store.update_task = AsyncMock()
    store.update_step = AsyncMock()
    store.add_finding = AsyncMock()
    store._connect = AsyncMock()
    store._disconnect = AsyncMock()
    return store


@pytest.fixture
def mock_pg_store():
    """Create a mock PostgreSQL task store."""
    store = AsyncMock()
    store.create_task = AsyncMock()
    store.get_task = AsyncMock(return_value=None)
    store.update_task = AsyncMock()
    store.db = Mock()
    return store


@pytest.fixture
def mock_tree_adapter():
    """Create a mock tree adapter."""
    adapter = AsyncMock(spec=TaskExecutionTreeAdapter)
    adapter.create_task_tree = AsyncMock(return_value="tree-123")
    adapter.get_ready_steps = AsyncMock(return_value=[])
    adapter.is_task_complete = AsyncMock(return_value=(False, None))
    return adapter


@pytest.fixture
def mock_state_machine():
    """Create a mock state machine."""
    machine = AsyncMock()
    machine.transition = AsyncMock()
    return machine


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    orchestrator = AsyncMock()
    orchestrator.execute_cycle = AsyncMock(return_value={"status": "completed"})
    orchestrator.initialize = AsyncMock()
    orchestrator.cleanup = AsyncMock()
    return orchestrator


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="task-123",
        user_id="user-456",
        organization_id="org-789",
        goal="Research AI developments",
        steps=[
            TaskStep(
                id="step-1",
                name="Research",
                description="Gather AI news",
                agent_type="web_research",
                inputs={"query": "latest AI news"}
            ),
            TaskStep(
                id="step-2",
                name="Summarize",
                description="Create summary",
                agent_type="summarizer",
                dependencies=["step-1"],
                inputs={}
            )
        ],
        status=TaskStatus.READY,
    )


@pytest.fixture
def service_with_mocks(
    mock_redis_store,
    mock_pg_store,
    mock_tree_adapter,
    mock_state_machine,
    mock_orchestrator,
):
    """Create TaskService with mocked dependencies."""
    service = TaskService(
        redis_store=mock_redis_store,
        pg_store=mock_pg_store,
        tree_adapter=mock_tree_adapter,
        state_machine=mock_state_machine,
        orchestrator=mock_orchestrator,
    )
    service._checkpoint_manager = AsyncMock()
    service._execution_event_bus = Mock()
    service._execution_event_bus.task_started = AsyncMock()
    service._execution_event_bus.checkpoint_created = AsyncMock()
    service._execution_event_bus.checkpoint_auto_approved = AsyncMock()
    service._conversation_port = Mock()
    service._conversation_port.ensure_conversation = AsyncMock()
    service._conversation_port.add_checkpoint_resolution_message = AsyncMock()
    service._scheduler_port = Mock()
    service._scheduler_port.schedule_ready_nodes = AsyncMock()
    service._plan_store_port = mock_redis_store
    service._planning_store = TaskPlanningStoreAdapter(
        pg_store=mock_pg_store,
        redis_store=mock_redis_store,
    )
    service._status_transition_port = Mock()
    service._status_transition_port.transition = AsyncMock()
    service._execution_use_case = TaskExecutionUseCase(
        orchestrator=mock_orchestrator,
        plan_store=service._plan_store_port,
        task_store=service._planning_store,
        status_transition=service._status_transition_port,
        scheduler=service._scheduler_port,
        event_bus=service._execution_event_bus,
        conversation_port=service._conversation_port,
        checkpoint_manager=service._checkpoint_manager,
        preference_service=None,
    )
    service._initialized = True
    return service


class TestTaskServiceTreeInitialization:
    """Tests for tree adapter initialization."""

    async def test_tree_adapter_initialized_when_not_provided(self):
        """Tree adapter is auto-initialized if not provided."""
        service = TaskService()
        service._redis_store = AsyncMock()
        service._redis_store._connect = AsyncMock()
        service._pg_store = AsyncMock()
        service._pg_store.db = Mock()

        runtime_components = SimpleNamespace(
            state_machine=AsyncMock(),
            checkpoint_manager=AsyncMock(),
            preference_service=AsyncMock(),
            risk_detector=Mock(),
        )
        with patch("src.application.tasks.runtime.build_runtime_components", return_value=runtime_components):
            with patch("src.application.tasks.runtime.TaskOrchestratorAdapter") as mock_orch:
                mock_orch.return_value.initialize = AsyncMock()
                with patch("src.application.tasks.runtime.TaskObserverAdapter") as mock_obs:
                    mock_obs.return_value.initialize = AsyncMock()
                    with patch("src.application.tasks.runtime.TaskPlannerAdapter") as mock_planner:
                        mock_planner.return_value.initialize = AsyncMock()
                        with patch("src.application.tasks.runtime.TaskExecutionTreeAdapter") as mock_adapter:
                            mock_adapter.return_value = AsyncMock()
                            await service.initialize()
                            mock_adapter.assert_called_once()

    async def test_tree_adapter_used_when_provided(self, mock_tree_adapter):
        """Provided tree adapter is used without creating new one."""
        service = TaskService(tree_adapter=mock_tree_adapter)
        assert service._tree_adapter is mock_tree_adapter


class TestTaskServiceTreeCreation:
    """Tests for tree creation in task creation methods."""

    def _setup_bg_mocks(self, service, mock_pg_store):
        """Set up mocks needed for _plan_task_async to run end-to-end."""
        service._plan_cancellation_port = Mock()
        service._plan_cancellation_port.is_cancelled = AsyncMock(return_value=False)
        service._planning_intent_port = Mock()
        service._planning_intent_port.extract_intent = AsyncMock(return_value=None)
        service._fast_path_planner_port = Mock()
        service._fast_path_planner_port.try_fast_path = AsyncMock(return_value=None)
        service._planning_event_bus = _mock_planning_event_bus()
        service._auto_start_task = AsyncMock()

        # get_task is called during tree creation
        created_task = Task(
            id="task-new",
            user_id="user-1",
            organization_id="org-1",
            goal="Test goal",
            steps=[TaskStep(id="s1", name="Step 1", description="Process data", agent_type="processor")],
        )
        service._planning_store = TaskPlanningStoreAdapter(
            pg_store=mock_pg_store,
            redis_store=service._redis_store,
        )
        mock_pg_store.get_task = AsyncMock(return_value=created_task)
        service._redis_store.get_task = AsyncMock(return_value=created_task)

    async def test_create_task_creates_execution_tree(
        self,
        service_with_mocks,
        mock_tree_adapter,
        mock_pg_store,
    ):
        """create_task creates execution tree after storing task."""
        self._setup_bg_mocks(service_with_mocks, mock_pg_store)

        with patch.object(service_with_mocks, '_workflow_planner') as mock_planner:
            mock_planner.generate_delegation_steps = AsyncMock(return_value=[
                TaskStep(id="s1", name="Step 1", description="Process data", agent_type="processor")
            ])
            mock_planner.start_conversation = AsyncMock()
            mock_planner.end_conversation = AsyncMock()

            with patch.object(service_with_mocks, '_risk_detector') as mock_risk:
                mock_risk.assess_plan = Mock(return_value={})

                service_with_mocks._status_transition_port = Mock()
                service_with_mocks._status_transition_port.transition = AsyncMock(return_value=Task(
                    id="task-new", user_id="user-1", organization_id="org-1",
                    goal="Test goal", steps=[], status=TaskStatus.READY,
                ))

                task = await service_with_mocks.create_task(
                    user_id="user-1",
                    organization_id="org-1",
                    goal="Test goal",
                    auto_start=False,
                )

                # Await the background planning task
                bg_task = list(service_with_mocks._active_planning.values())[0]
                await bg_task

                # Verify tree adapter was called
                mock_tree_adapter.create_task_tree.assert_called_once()
                # Verify tree_id was updated in PG
                mock_pg_store.update_task.assert_called()

    async def test_create_task_marks_failed_on_tree_creation_failure(
        self,
        service_with_mocks,
        mock_tree_adapter,
        mock_pg_store,
    ):
        """Task planning is marked failed when tree creation fails."""
        # Make tree creation fail
        mock_tree_adapter.create_task_tree = AsyncMock(side_effect=Exception("Redis unavailable"))
        self._setup_bg_mocks(service_with_mocks, mock_pg_store)

        with patch.object(service_with_mocks, '_workflow_planner') as mock_planner:
            mock_planner.generate_delegation_steps = AsyncMock(return_value=[
                TaskStep(id="s1", name="Step 1", description="Process data", agent_type="processor")
            ])
            mock_planner.start_conversation = AsyncMock()
            mock_planner.end_conversation = AsyncMock()

            with patch.object(service_with_mocks, '_risk_detector') as mock_risk:
                mock_risk.assess_plan = Mock(return_value={})

                service_with_mocks._status_transition_port = Mock()
                service_with_mocks._status_transition_port.transition = AsyncMock(return_value=Task(
                    id="task-new", user_id="user-1", organization_id="org-1",
                    goal="Test goal", steps=[], status=TaskStatus.READY,
                ))

                task = await service_with_mocks.create_task(
                    user_id="user-1",
                    organization_id="org-1",
                    goal="Test goal",
                    auto_start=False,
                )

                # Await the background planning task
                bg_task = list(service_with_mocks._active_planning.values())[0]
                await bg_task

                assert task is not None
                status_calls = service_with_mocks._status_transition_port.transition.await_args_list
                assert any(
                    call.args[1] == TaskStatus.FAILED
                    for call in status_calls
                )


class TestTaskServiceStartPlanAsync:
    """Tests for start_plan_async with execution tree."""

    async def test_start_plan_uses_scheduler_when_tree_exists(
        self,
        service_with_mocks,
        sample_task,
        mock_redis_store,
    ):
        """start_plan_async uses schedule_ready_nodes when tree_id exists."""
        # Task has tree_id
        sample_task.tree_id = "tree-123"
        sample_task.status = TaskStatus.READY
        mock_redis_store.get_task = AsyncMock(return_value=sample_task)

        # Mock state machine transition
        transitioned_task = Task(**sample_task.__dict__)
        transitioned_task.status = TaskStatus.EXECUTING
        service_with_mocks._status_transition_port.transition = AsyncMock(return_value=transitioned_task)

        service_with_mocks._scheduler_port.schedule_ready_nodes = AsyncMock(return_value=2)

        result = await service_with_mocks.start_plan_async(
            plan_id="task-123",
            user_id="user-456",
        )

        # Verify scheduler was called
        service_with_mocks._scheduler_port.schedule_ready_nodes.assert_called_once_with("task-123")
        assert result["status"] == "started"
        assert result["scheduled_steps"] == 2

    async def test_start_plan_errors_when_no_tree(
        self,
        service_with_mocks,
        sample_task,
        mock_redis_store,
        mock_orchestrator,
    ):
        """start_plan_async returns error when tree_id is missing."""
        # Task has no tree_id
        sample_task.tree_id = None
        sample_task.status = TaskStatus.READY
        mock_redis_store.get_task = AsyncMock(return_value=sample_task)

        # Mock state machine transition
        transitioned_task = Task(**sample_task.__dict__)
        transitioned_task.status = TaskStatus.EXECUTING
        service_with_mocks._status_transition_port.transition = AsyncMock(return_value=transitioned_task)

        result = await service_with_mocks.start_plan_async(
            plan_id="task-123",
            user_id="user-456",
        )

        mock_orchestrator.execute_cycle.assert_not_called()
        assert result["status"] == "error"
        assert "missing execution tree" in result["error"].lower()

    async def test_start_plan_errors_on_scheduler_failure(
        self,
        service_with_mocks,
        sample_task,
        mock_redis_store,
        mock_orchestrator,
    ):
        """start_plan_async returns error when scheduler fails."""
        # Task has tree_id
        sample_task.tree_id = "tree-123"
        sample_task.status = TaskStatus.READY
        mock_redis_store.get_task = AsyncMock(return_value=sample_task)

        # Mock state machine transition
        transitioned_task = Task(**sample_task.__dict__)
        transitioned_task.status = TaskStatus.EXECUTING
        service_with_mocks._status_transition_port.transition = AsyncMock(return_value=transitioned_task)

        service_with_mocks._scheduler_port.schedule_ready_nodes = AsyncMock(
            side_effect=Exception("Redis error")
        )

        result = await service_with_mocks.start_plan_async(
            plan_id="task-123",
            user_id="user-456",
        )

        mock_orchestrator.execute_cycle.assert_not_called()
        assert result["status"] == "error"
        assert "redis error" in result["error"].lower()


class TestTaskServiceTreeIdPropagation:
    """Tests for tree_id propagation through task lifecycle."""

    async def test_tree_id_stored_in_postgresql(
        self,
        service_with_mocks,
        mock_tree_adapter,
        mock_pg_store,
    ):
        """tree_id is updated in PostgreSQL after tree creation."""
        mock_tree_adapter.create_task_tree = AsyncMock(return_value="tree-xyz")

        # Setup bg mocks
        service_with_mocks._plan_cancellation_port = Mock()
        service_with_mocks._plan_cancellation_port.is_cancelled = AsyncMock(return_value=False)
        service_with_mocks._planning_intent_port = Mock()
        service_with_mocks._planning_intent_port.extract_intent = AsyncMock(return_value=None)
        service_with_mocks._fast_path_planner_port = Mock()
        service_with_mocks._fast_path_planner_port.try_fast_path = AsyncMock(return_value=None)
        service_with_mocks._planning_event_bus = _mock_planning_event_bus()
        service_with_mocks._auto_start_task = AsyncMock()

        created_task = Task(
            id="task-new", user_id="user-1", organization_id="org-1",
            goal="Test", steps=[],
        )
        service_with_mocks._planning_store = TaskPlanningStoreAdapter(
            pg_store=mock_pg_store,
            redis_store=service_with_mocks._redis_store,
        )
        mock_pg_store.get_task = AsyncMock(return_value=created_task)
        service_with_mocks._redis_store.get_task = AsyncMock(return_value=created_task)

        with patch.object(service_with_mocks, '_workflow_planner') as mock_planner:
            mock_planner.generate_delegation_steps = AsyncMock(return_value=[
                TaskStep(id="s1", name="Step", description="Process", agent_type="processor")
            ])
            mock_planner.start_conversation = AsyncMock()
            mock_planner.end_conversation = AsyncMock()

            with patch.object(service_with_mocks, '_risk_detector') as mock_risk:
                mock_risk.assess_plan = Mock(return_value={})

                service_with_mocks._status_transition_port = Mock()
                service_with_mocks._status_transition_port.transition = AsyncMock(return_value=created_task)

                await service_with_mocks.create_task(
                    user_id="user-1",
                    organization_id="org-1",
                    goal="Test",
                    auto_start=False,
                )

                # Await the background planning task
                bg_task = list(service_with_mocks._active_planning.values())[0]
                await bg_task

                # Verify update was called with tree_id
                update_calls = mock_pg_store.update_task.call_args_list
                tree_id_update = [c for c in update_calls if c[1].get("tree_id") == "tree-xyz"]
                assert len(tree_id_update) > 0 or any(
                    "tree_id" in str(c) for c in update_calls
                )


class TestCreateTaskWithStepsDependencyResolution:
    """Tests for name-to-ID dependency resolution in create_task_with_steps."""

    async def test_resolves_name_based_dependencies_to_step_ids(
        self, service_with_mocks, mock_redis_store, mock_tree_adapter,
    ):
        """Dependencies referencing step names are resolved to step IDs."""
        with patch.object(service_with_mocks, '_risk_detector') as mock_risk:
            mock_risk.assess_plan = Mock(return_value={})

            task = await service_with_mocks.create_task_with_steps(
                user_id="user-1",
                organization_id="org-1",
                goal="Test dependency resolution",
                steps=[
                    {
                        "name": "generate_response",
                        "agent_type": "compose",
                        "inputs": {"topic": "joke"},
                    },
                    {
                        "name": "send_response",
                        "agent_type": "discord_followup",
                        "inputs": {"content": "test"},
                        "dependencies": ["generate_response"],
                    },
                ],
            )

            # step_1 = generate_response, step_2 = send_response
            assert task.steps[0].id == "step_1"
            assert task.steps[0].name == "generate_response"
            assert task.steps[1].id == "step_2"
            assert task.steps[1].dependencies == ["step_1"]

    async def test_preserves_id_based_dependencies(
        self, service_with_mocks, mock_redis_store, mock_tree_adapter,
    ):
        """Dependencies already using step IDs are left unchanged."""
        with patch.object(service_with_mocks, '_risk_detector') as mock_risk:
            mock_risk.assess_plan = Mock(return_value={})

            task = await service_with_mocks.create_task_with_steps(
                user_id="user-1",
                organization_id="org-1",
                goal="Test ID deps",
                steps=[
                    {
                        "id": "s1",
                        "name": "First",
                        "agent_type": "processor",
                        "inputs": {},
                    },
                    {
                        "id": "s2",
                        "name": "Second",
                        "agent_type": "processor",
                        "inputs": {},
                        "dependencies": ["s1"],
                    },
                ],
            )

            # Explicit IDs preserved, deps stay as-is (no matching name)
            assert task.steps[1].dependencies == ["s1"]
