"""
Unit tests for StepExecutionUseCase.

All ports are mocked — no infrastructure or I/O involved.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from dataclasses import dataclass

from src.domain.tasks.models import TaskStep, StepStatus
from src.application.tasks.step_execution_use_case import (
    StepExecutionUseCase,
    StepExecutionResult,
    _is_transient_error,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tree():
    tree = AsyncMock()
    tree.get_step_from_tree = AsyncMock(return_value=None)
    tree.start_step = AsyncMock(return_value=True)
    tree.complete_step = AsyncMock(return_value=True)
    tree.fail_step = AsyncMock(return_value=True)
    tree.pause_step = AsyncMock(return_value=True)
    tree.reset_step = AsyncMock(return_value=True)
    tree.is_task_complete = AsyncMock(return_value=(False, None))
    tree.get_tree_metrics = AsyncMock(return_value={
        "total_nodes": 4,
        "status_counts": {"completed": 3, "failed": 0},
    })
    return tree


@pytest.fixture
def mock_plan_store():
    store = AsyncMock()
    store.update_step = AsyncMock()
    store.update_task = AsyncMock()
    return store


@pytest.fixture
def mock_task_store():
    store = AsyncMock()
    store.update_step = AsyncMock()
    store.update_task = AsyncMock()
    store.get_task = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.step_completed = AsyncMock()
    bus.step_failed = AsyncMock()
    bus.step_started = AsyncMock()
    bus.checkpoint_created = AsyncMock()
    bus.task_completed = AsyncMock()
    return bus


@pytest.fixture
def mock_scheduler():
    sched = AsyncMock()
    sched.schedule_ready_nodes = AsyncMock(return_value=1)
    return sched


@pytest.fixture
def mock_inbox():
    inbox = AsyncMock()
    inbox.add_step_message = AsyncMock()
    inbox.add_checkpoint_message = AsyncMock()
    inbox.add_completion_message = AsyncMock()
    return inbox


@pytest.fixture
def mock_plugin():
    return AsyncMock()


@pytest.fixture
def mock_model_selector():
    selector = Mock()
    selector.select_model = Mock(return_value="anthropic/claude-3.5-haiku")
    return selector


@pytest.fixture
def mock_checkpoint():
    cp = AsyncMock()
    cp.is_already_approved = AsyncMock(return_value=False)
    cp.create_checkpoint = AsyncMock()
    return cp


@pytest.fixture
def use_case(
    mock_tree,
    mock_plan_store,
    mock_task_store,
    mock_event_bus,
    mock_scheduler,
    mock_inbox,
    mock_plugin,
    mock_model_selector,
    mock_checkpoint,
):
    return StepExecutionUseCase(
        tree=mock_tree,
        plan_store=mock_plan_store,
        task_store=mock_task_store,
        event_bus=mock_event_bus,
        scheduler=mock_scheduler,
        inbox=mock_inbox,
        plugin=mock_plugin,
        model_selector=mock_model_selector,
        checkpoint=mock_checkpoint,
    )


@pytest.fixture
def sample_step():
    return TaskStep(
        id="step-1",
        name="Research",
        description="Gather AI news",
        agent_type="web_research",
        inputs={"query": "latest AI news"},
    )


@pytest.fixture
def sample_step_data():
    return {
        "id": "step-1",
        "name": "Research",
        "description": "Gather AI news",
        "agent_type": "web_research",
        "inputs": {"query": "latest AI news"},
        "user_id": "user-123",
    }


def _success_result(output=None, execution_time_ms=1500):
    r = Mock()
    r.success = True
    r.output = output or {"findings": ["AI is advancing"]}
    r.execution_time_ms = execution_time_ms
    return r


def _failure_result(error="Step execution failed", execution_time_ms=500):
    r = Mock()
    r.success = False
    r.error = error
    r.output = None
    r.execution_time_ms = execution_time_ms
    return r


# ---------------------------------------------------------------------------
# TestStepExecutionSuccess
# ---------------------------------------------------------------------------


class TestStepExecutionSuccess:
    """Verify tree operations (start→complete), dual-store sync, events,
    inbox, dependents scheduled."""

    @pytest.mark.asyncio
    async def test_happy_path(
        self, use_case, mock_tree, mock_plan_store, mock_task_store,
        mock_event_bus, mock_scheduler, mock_inbox, mock_plugin,
        sample_step, sample_step_data,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _success_result()

        result = await use_case.execute("task-1", sample_step_data)

        assert result.status == "success"
        assert result.task_id == "task-1"
        assert result.step_id == "step-1"
        assert result.output == {"findings": ["AI is advancing"]}

        # Tree operations
        mock_tree.start_step.assert_awaited_once_with("task-1", "step-1")
        mock_tree.complete_step.assert_awaited_once_with("task-1", "step-1", {"findings": ["AI is advancing"]})

        # Dual-store sync
        mock_plan_store.update_step.assert_awaited_once()
        mock_task_store.update_step.assert_awaited_once()

        # Events
        mock_event_bus.step_completed.assert_awaited_once()

        # Inbox
        mock_inbox.add_step_message.assert_awaited_once()

        # Scheduling
        mock_scheduler.schedule_ready_nodes.assert_awaited_once_with("task-1")

    @pytest.mark.asyncio
    async def test_resolved_inputs_from_step_data(
        self, use_case, mock_tree, mock_plugin, sample_step,
    ):
        """step_data inputs override tree-stored template inputs."""
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _success_result()

        step_data = {
            "id": "step-1",
            "agent_type": "web_research",
            "inputs": {"query": "resolved query", "extra": "context"},
        }
        await use_case.execute("task-1", step_data)

        # Plugin should be called with resolved inputs
        call_kwargs = mock_plugin.execute.call_args
        step_arg = call_kwargs.kwargs.get("step") or call_kwargs.args[0]
        assert step_arg.inputs == {"query": "resolved query", "extra": "context"}


# ---------------------------------------------------------------------------
# TestStepExecutionCheckpoint
# ---------------------------------------------------------------------------


class TestStepExecutionCheckpoint:
    """Verify checkpoint check, pause, early return."""

    @pytest.mark.asyncio
    async def test_pauses_for_checkpoint(
        self, use_case, mock_tree, mock_checkpoint,
        mock_plan_store, mock_task_store,
        mock_event_bus, mock_inbox,
    ):
        checkpoint_step = TaskStep(
            id="step-1",
            name="Risky Step",
            description="Needs approval",
            agent_type="processor",
            checkpoint_required=True,
        )
        mock_tree.get_step_from_tree.return_value = checkpoint_step
        mock_checkpoint.is_already_approved.return_value = False

        step_data = {"id": "step-1", "agent_type": "processor", "inputs": {}}
        result = await use_case.execute("task-1", step_data)

        assert result.status == "checkpoint"
        assert result.step_id == "step-1"

        # Tree should be paused
        mock_tree.pause_step.assert_awaited_once_with("task-1", "step-1")

        # Stores updated with checkpoint status
        mock_plan_store.update_step.assert_awaited()
        mock_task_store.update_step.assert_awaited()

        # Checkpoint created and events published
        mock_checkpoint.create_checkpoint.assert_awaited_once()
        mock_event_bus.checkpoint_created.assert_awaited_once()
        mock_inbox.add_checkpoint_message.assert_awaited_once()


class TestStepExecutionCheckpointAlreadyApproved:
    """Verify approved checkpoint proceeds with execution."""

    @pytest.mark.asyncio
    async def test_continues_after_approval(
        self, use_case, mock_tree, mock_checkpoint, mock_plugin,
    ):
        checkpoint_step = TaskStep(
            id="step-1",
            name="Risky Step",
            description="Needs approval",
            agent_type="processor",
            checkpoint_required=True,
        )
        mock_tree.get_step_from_tree.return_value = checkpoint_step
        mock_checkpoint.is_already_approved.return_value = True
        mock_plugin.execute.return_value = _success_result()

        step_data = {"id": "step-1", "agent_type": "processor", "inputs": {}}
        result = await use_case.execute("task-1", step_data)

        # Should proceed to execution
        assert result.status == "success"
        mock_plugin.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestStepExecutionFailureRetry
# ---------------------------------------------------------------------------


class TestStepExecutionFailureRetry:
    """Verify transient error triggers retry with retry_step_data."""

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(
        self, use_case, mock_tree, mock_plugin,
        mock_plan_store, mock_task_store, mock_event_bus, sample_step,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _failure_result(error="Connection timeout")

        step_data = {
            "id": "step-1",
            "agent_type": "web_research",
            "inputs": {},
            "retry_count": 0,
            "max_retries": 3,
        }
        result = await use_case.execute("task-1", step_data)

        assert result.status == "retrying"
        assert result.retry_step_data is not None
        assert result.retry_step_data["retry_count"] == 1

        # Tree should be reset
        mock_tree.reset_step.assert_awaited_once_with("task-1", "step-1")

        # Stores updated with retry info
        mock_plan_store.update_step.assert_awaited()
        mock_task_store.update_step.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_retry_at_max(
        self, use_case, mock_tree, mock_plugin, sample_step,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _failure_result(error="Connection timeout")

        step_data = {
            "id": "step-1",
            "agent_type": "web_research",
            "inputs": {},
            "retry_count": 3,
            "max_retries": 3,
        }
        result = await use_case.execute("task-1", step_data)

        assert result.status == "error"
        assert result.retry_step_data is None


# ---------------------------------------------------------------------------
# TestStepExecutionFailurePermanent
# ---------------------------------------------------------------------------


class TestStepExecutionFailurePermanent:
    """Verify permanent failure: tree fail, stores sync, events, inbox."""

    @pytest.mark.asyncio
    async def test_permanent_failure(
        self, use_case, mock_tree, mock_plugin,
        mock_plan_store, mock_task_store,
        mock_event_bus, mock_inbox, sample_step,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _failure_result(error="Invalid input")

        step_data = {"id": "step-1", "agent_type": "web_research", "inputs": {}}
        result = await use_case.execute("task-1", step_data)

        assert result.status == "error"
        assert result.error == "Invalid input"

        # Tree
        mock_tree.fail_step.assert_awaited_once_with("task-1", "step-1", "Invalid input")

        # Dual-store
        mock_plan_store.update_step.assert_awaited()
        mock_task_store.update_step.assert_awaited()

        # Events
        mock_event_bus.step_failed.assert_awaited_once()

        # Inbox
        mock_inbox.add_step_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestStepExecutionTaskFinalization
# ---------------------------------------------------------------------------


class TestStepExecutionTaskFinalization:
    """Verify task completion detection, status update, completion inbox."""

    @pytest.mark.asyncio
    async def test_finalizes_task_on_completion(
        self, use_case, mock_tree, mock_plugin,
        mock_plan_store, mock_task_store,
        mock_event_bus, mock_inbox, sample_step,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _success_result()
        mock_tree.is_task_complete.return_value = (True, "completed")
        mock_tree.get_tree_metrics.return_value = {
            "total_nodes": 4,
            "status_counts": {"completed": 4, "failed": 0},
        }

        step_data = {"id": "step-1", "agent_type": "web_research", "inputs": {}}
        result = await use_case.execute("task-1", step_data)

        assert result.status == "success"

        # Task should be finalized
        # plan_store.update_task called for step update AND task finalization
        task_update_calls = mock_plan_store.update_task.call_args_list
        assert len(task_update_calls) >= 1
        final_call = task_update_calls[-1]
        assert final_call.args[1]["status"] == "completed"

        # Task completed event
        mock_event_bus.task_completed.assert_awaited_once()

        # Inbox completion message
        mock_inbox.add_completion_message.assert_awaited_once()


class TestStepExecutionTaskFailureFinalization:
    """Verify task failure detection when step fails."""

    @pytest.mark.asyncio
    async def test_finalizes_task_on_failure(
        self, use_case, mock_tree, mock_plugin,
        mock_plan_store, mock_task_store,
        mock_event_bus, mock_inbox, sample_step,
    ):
        mock_tree.get_step_from_tree.return_value = sample_step
        mock_plugin.execute.return_value = _failure_result(error="Bad data")
        mock_tree.is_task_complete.return_value = (True, "failed")
        mock_tree.get_tree_metrics.return_value = {
            "total_nodes": 4,
            "status_counts": {"completed": 2, "failed": 1},
        }

        step_data = {"id": "step-1", "agent_type": "web_research", "inputs": {}}
        result = await use_case.execute("task-1", step_data)

        assert result.status == "error"

        # Task should be finalized as failed
        task_update_calls = mock_plan_store.update_task.call_args_list
        assert any(c.args[1].get("status") == "failed" for c in task_update_calls)

        mock_event_bus.task_completed.assert_awaited_once()
        mock_inbox.add_completion_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestStepExecutionFallback
# ---------------------------------------------------------------------------


class TestStepExecutionFallback:
    """Verify step reconstruction from step_data when tree lookup returns None."""

    @pytest.mark.asyncio
    async def test_reconstructs_from_step_data(
        self, use_case, mock_tree, mock_plugin,
    ):
        mock_tree.get_step_from_tree.return_value = None
        mock_plugin.execute.return_value = _success_result()

        step_data = {
            "id": "step-1",
            "name": "Fallback Step",
            "description": "Reconstructed",
            "agent_type": "web_research",
            "inputs": {"query": "test"},
        }
        result = await use_case.execute("task-1", step_data)

        assert result.status == "success"
        # Plugin should have been called with a reconstructed step
        call_kwargs = mock_plugin.execute.call_args
        step_arg = call_kwargs.kwargs.get("step") or call_kwargs.args[0]
        assert step_arg.id == "step-1"
        assert step_arg.name == "Fallback Step"


# ---------------------------------------------------------------------------
# TestStepInitialization
# ---------------------------------------------------------------------------


class TestStepInitialization:
    """Verify resolved inputs from step_data are used over tree's template inputs."""

    @pytest.mark.asyncio
    async def test_uses_resolved_inputs(
        self, use_case, mock_tree, mock_plugin,
    ):
        tree_step = TaskStep(
            id="step-1",
            name="Research",
            description="Template",
            agent_type="web_research",
            inputs={"query": "{{template}}"},
        )
        mock_tree.get_step_from_tree.return_value = tree_step
        mock_plugin.execute.return_value = _success_result()

        step_data = {
            "id": "step-1",
            "agent_type": "web_research",
            "inputs": {"query": "resolved value"},
        }
        await use_case.execute("task-1", step_data)

        call_kwargs = mock_plugin.execute.call_args
        step_arg = call_kwargs.kwargs.get("step") or call_kwargs.args[0]
        assert step_arg.inputs == {"query": "resolved value"}


# ---------------------------------------------------------------------------
# TestIsTransientError
# ---------------------------------------------------------------------------


class TestIsTransientError:
    def test_timeout_is_transient(self):
        assert _is_transient_error("Connection timeout") is True

    def test_rate_limit_is_transient(self):
        assert _is_transient_error("rate limit exceeded") is True

    def test_503_is_transient(self):
        assert _is_transient_error("HTTP 503 Service Unavailable") is True

    def test_invalid_input_is_not_transient(self):
        assert _is_transient_error("Invalid input data") is False

    def test_empty_is_not_transient(self):
        assert _is_transient_error("") is False

    def test_none_is_not_transient(self):
        assert _is_transient_error(None) is False
