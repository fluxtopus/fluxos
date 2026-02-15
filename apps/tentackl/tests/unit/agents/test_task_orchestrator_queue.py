"""
Unit tests for TaskOrchestratorAgent queue-based execution.

Tests the queue execution mode where steps are enqueued to Redis
for processing by AgentWorker instances.
"""

import pytest
from unittest.mock import AsyncMock

from src.infrastructure.tasks.task_orchestrator import TaskOrchestratorAgent
from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
)


TEST_USER_ID = "test-user-123"
TEST_ORG_ID = "test-org-123"


class TestDelegationOrchestratorQueueMode:
    """Test TaskOrchestratorAgent in queue execution mode."""

    @pytest.fixture
    def mock_plan_store(self):
        """Create a mock plan store."""
        store = AsyncMock()
        store.get_task = AsyncMock()
        store.update_task = AsyncMock()
        store.update_step = AsyncMock()
        return store

    @pytest.fixture
    def sample_plan(self):
        """Create a sample plan for testing."""
        return Task(
            id="test-plan-123",
            goal="Test queue execution",
            user_id=TEST_USER_ID,
            organization_id=TEST_ORG_ID,
            status=TaskStatus.EXECUTING,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch Data",
                    description="Fetch data from API",
                    agent_type="http_fetch",
                    inputs={"url": "http://example.com/api"},
                    status=StepStatus.PENDING,
                ),
                TaskStep(
                    id="step_2",
                    name="Process Data",
                    description="Process the fetched data",
                    agent_type="llm_analysis",
                    inputs={"prompt": "Analyze this"},
                    status=StepStatus.PENDING,
                    dependencies=["step_1"],
                ),
            ],
        )

    @pytest.fixture
    def mock_step_dispatcher(self):
        dispatcher = AsyncMock()
        dispatcher.dispatch_step = AsyncMock()
        return dispatcher

    def test_queue_mode_initialization(self, mock_plan_store):
        """Orchestrator initializes with queue execution mode."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="queue",
        )

        assert orchestrator._execution_mode == "queue"

    def test_in_process_mode_initialization(self, mock_plan_store):
        """Orchestrator can still initialize with in-process mode."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="in_process",
        )

        assert orchestrator._execution_mode == "in_process"

    def test_default_mode_is_queue(self, mock_plan_store):
        """Default execution mode is queue."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
        )

        assert orchestrator._execution_mode == "queue"

    @pytest.mark.asyncio
    async def test_enqueue_step_creates_correct_payload(
        self,
        mock_plan_store,
        sample_plan,
        mock_step_dispatcher,
    ):
        """_enqueue_step dispatches through TaskStepDispatchPort."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="queue",
            step_dispatcher=mock_step_dispatcher,
        )

        step = sample_plan.steps[0]
        mock_step_dispatcher.dispatch_step.return_value = {
            "success": True,
            "step_id": "step_1",
            "celery_task_id": "celery-task-123",
        }

        result = await orchestrator._enqueue_step(sample_plan, step)

        mock_step_dispatcher.dispatch_step.assert_awaited_once()
        call_kwargs = mock_step_dispatcher.dispatch_step.call_args.kwargs
        assert call_kwargs["task_id"] == str(sample_plan.id)
        assert call_kwargs["step"] == step
        assert call_kwargs["plan"] == sample_plan

        assert result["status"] == "enqueued"
        assert result["task_id"] == "celery-task-123"
        assert result["step_id"] == "step_1"

    @pytest.mark.asyncio
    async def test_execute_step_routes_to_queue(self, mock_plan_store, sample_plan, mock_step_dispatcher):
        """_execute_step uses StepDispatcher in queue mode."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="queue",
            step_dispatcher=mock_step_dispatcher,
        )

        mock_step_dispatcher.dispatch_step.return_value = {
            "success": True,
            "step_id": "step_1",
            "celery_task_id": "celery-task-123",
        }

        step = sample_plan.steps[0]
        result = await orchestrator._execute_step(sample_plan, step)

        mock_step_dispatcher.dispatch_step.assert_awaited_once()
        call_kwargs = mock_step_dispatcher.dispatch_step.call_args.kwargs
        assert call_kwargs["task_id"] == str(sample_plan.id)
        assert call_kwargs["step"] == step
        assert call_kwargs["plan"] == sample_plan

        assert result["status"] == "enqueued"
        assert result["step_id"] == "step_1"
        assert result["celery_task_id"] == "celery-task-123"

    @pytest.mark.asyncio
    async def test_execute_step_routes_to_in_process(self, mock_plan_store, sample_plan):
        """_execute_step routes to _execute_step_in_process in in_process mode."""
        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="in_process",
        )

        # Mock the in-process method
        orchestrator._execute_step_in_process = AsyncMock(return_value={
            "status": "completed",
            "output": {"data": "result"},
        })

        step = sample_plan.steps[0]
        result = await orchestrator._execute_step(sample_plan, step)

        orchestrator._execute_step_in_process.assert_called_once()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_cycle_enqueues_ready_steps(
        self,
        mock_plan_store,
        sample_plan,
        mock_step_dispatcher,
    ):
        """execute_cycle dispatches ready steps via StepDispatcher in queue mode."""
        mock_plan_store.get_task.return_value = sample_plan

        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="queue",
            step_dispatcher=mock_step_dispatcher,
        )

        mock_step_dispatcher.dispatch_step.return_value = {
            "success": True,
            "step_id": "step_1",
            "celery_task_id": "celery-task-123",
        }

        result = await orchestrator.execute_cycle("test-plan-123")

        assert mock_step_dispatcher.dispatch_step.await_count == 1
        assert result["status"] == "step_enqueued"

    @pytest.mark.asyncio
    async def test_parallel_steps_all_enqueued(self, mock_plan_store, mock_step_dispatcher):
        """Parallel steps are all dispatched via StepDispatcher in a single cycle."""
        plan = Task(
            id="test-plan-parallel",
            goal="Test parallel queue execution",
            user_id=TEST_USER_ID,
            organization_id=TEST_ORG_ID,
            status=TaskStatus.EXECUTING,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch A",
                    description="Fetch from A",
                    agent_type="http_fetch",
                    inputs={"url": "http://a.com"},
                    status=StepStatus.PENDING,
                    parallel_group="fetch",
                ),
                TaskStep(
                    id="step_2",
                    name="Fetch B",
                    description="Fetch from B",
                    agent_type="http_fetch",
                    inputs={"url": "http://b.com"},
                    status=StepStatus.PENDING,
                    parallel_group="fetch",
                ),
                TaskStep(
                    id="step_3",
                    name="Process",
                    description="Process both",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    dependencies=["step_1", "step_2"],
                ),
            ],
        )

        mock_plan_store.get_task.return_value = plan

        orchestrator = TaskOrchestratorAgent(
            plan_store=mock_plan_store,
            execution_mode="queue",
            step_dispatcher=mock_step_dispatcher,
        )

        dispatched_steps = []

        async def mock_dispatch(task_id, step, plan=None, model=None):
            dispatched_steps.append(step.id)
            return {
                "success": True,
                "step_id": step.id,
                "celery_task_id": f"celery-task-{step.id}",
            }

        mock_step_dispatcher.dispatch_step.side_effect = mock_dispatch

        result = await orchestrator.execute_cycle("test-plan-parallel")

        assert len(dispatched_steps) == 2
        assert set(dispatched_steps) == {"step_1", "step_2"}
        assert result["status"] == "group_enqueued"
        assert result["parallel"] is True
