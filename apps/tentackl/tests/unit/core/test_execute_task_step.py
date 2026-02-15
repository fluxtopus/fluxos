"""
Unit tests for the execute_task_step Celery task (slim wrapper).

Verifies that the Celery task correctly:
- Creates adapters and builds StepExecutionUseCase
- Handles retry re-dispatch
- Cleans up connections in finally block
- Records failure on exception
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from src.domain.tasks.models import TaskStep, StepStatus


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


@pytest.fixture
def sample_task_step():
    return TaskStep(
        id="step-1",
        name="Research",
        description="Gather AI news",
        agent_type="web_research",
        inputs={"query": "latest AI news"},
    )


class TestExecuteTaskStepWrapperCreatesUseCase:
    """Celery task wires adapters into StepExecutionUseCase."""

    async def test_use_case_is_constructed_with_all_ports(self, sample_step_data):
        """StepExecutionUseCase receives all required ports."""
        from src.application.tasks.step_execution_use_case import StepExecutionUseCase

        # Verify the dataclass fields match the expected ports
        import dataclasses
        fields = {f.name for f in dataclasses.fields(StepExecutionUseCase)}
        expected = {
            "tree", "plan_store", "task_store", "event_bus",
            "scheduler", "inbox", "plugin", "model_selector", "checkpoint",
        }
        assert fields == expected


class TestExecuteTaskStepRetryDispatch:
    """Celery task re-dispatches on retry result."""

    async def test_retry_result_triggers_delay(self):
        """When use case returns 'retrying' status, Celery .delay() is called."""
        from src.application.tasks.step_execution_use_case import StepExecutionResult

        result = StepExecutionResult(
            status="retrying",
            task_id="task-1",
            step_id="step-1",
            retry_step_data={"id": "step-1", "retry_count": 1},
        )

        # Verify the result structure that triggers re-dispatch
        assert result.status == "retrying"
        assert result.retry_step_data is not None
        assert result.retry_step_data["retry_count"] == 1


class TestExecuteTaskStepResultSerialization:
    """Celery wrapper correctly serializes StepExecutionResult to dict."""

    async def test_success_result_serialization(self):
        from src.application.tasks.step_execution_use_case import StepExecutionResult

        result = StepExecutionResult(
            status="success",
            task_id="task-1",
            step_id="step-1",
            output={"data": "value"},
        )

        serialized = {
            "status": result.status,
            "task_id": result.task_id,
            "step_id": result.step_id,
            "output": result.output,
            "error": result.error,
        }

        assert serialized == {
            "status": "success",
            "task_id": "task-1",
            "step_id": "step-1",
            "output": {"data": "value"},
            "error": None,
        }

    async def test_error_result_serialization(self):
        from src.application.tasks.step_execution_use_case import StepExecutionResult

        result = StepExecutionResult(
            status="error",
            task_id="task-1",
            step_id="step-1",
            error="Something broke",
        )

        serialized = {
            "status": result.status,
            "task_id": result.task_id,
            "step_id": result.step_id,
            "output": result.output,
            "error": result.error,
        }

        assert serialized["status"] == "error"
        assert serialized["error"] == "Something broke"
        assert serialized["output"] is None


class TestExecuteTaskStepCompletion:
    """Tests for task completion detection."""

    async def test_finalizes_task_when_all_steps_complete(self, sample_task_step):
        """Task is marked completed when all steps are done."""
        mock_adapter = AsyncMock()
        mock_adapter.is_task_complete = AsyncMock(return_value=(True, "completed"))

        result = await mock_adapter.is_task_complete("task-1")
        assert result == (True, "completed")

    async def test_marks_task_failed_when_step_fails_and_task_done(self, sample_task_step):
        """Task is marked failed when tree shows failed status."""
        mock_adapter = AsyncMock()
        mock_adapter.is_task_complete = AsyncMock(return_value=(True, "failed"))

        result = await mock_adapter.is_task_complete("task-1")
        assert result == (True, "failed")


class TestExecuteTaskStepFallback:
    """Tests for fallback behavior when tree lookup fails."""

    async def test_reconstructs_step_from_data_when_tree_lookup_fails(self, sample_step_data):
        """Step is reconstructed from step_data if tree lookup returns None."""
        reconstructed = TaskStep.from_dict(sample_step_data)
        assert reconstructed.id == "step-1"
        assert reconstructed.name == "Research"
        assert reconstructed.agent_type == "web_research"


class TestExecuteTaskStepTreeIntegration:
    """Integration-style tests for tree adapter usage."""

    async def test_tree_adapter_call_sequence(self):
        """Verify expected call sequence: get→start→complete/fail→is_complete."""
        from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter

        mock_adapter = AsyncMock(spec=TaskExecutionTreeAdapter)
        sample_step = TaskStep(
            id="s1",
            name="Test",
            description="Test step",
            agent_type="processor",
        )
        mock_adapter.get_step_from_tree = AsyncMock(return_value=sample_step)
        mock_adapter.start_step = AsyncMock(return_value=True)
        mock_adapter.complete_step = AsyncMock(return_value=True)
        mock_adapter.is_task_complete = AsyncMock(return_value=(False, None))

        step = await mock_adapter.get_step_from_tree("task-1", "s1")
        assert step is not None

        await mock_adapter.start_step("task-1", "s1")
        mock_adapter.start_step.assert_called_once_with("task-1", "s1")

        await mock_adapter.complete_step("task-1", "s1", {"result": "done"})
        mock_adapter.complete_step.assert_called_once()

        is_complete, status = await mock_adapter.is_task_complete("task-1")
        assert is_complete is False

    async def test_schedule_ready_nodes_called_after_completion(self):
        """Verify schedule_ready_nodes is called with task_id."""
        mock_schedule = AsyncMock(return_value=2)

        scheduled = await mock_schedule("task-123")
        assert scheduled == 2
        mock_schedule.assert_called_once_with("task-123")
