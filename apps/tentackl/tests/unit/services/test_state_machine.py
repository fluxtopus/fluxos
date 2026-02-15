"""
Unit tests for TaskStateMachine.

Tests the state transition logic including terminal status enforcement
and pause/resume transitions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.infrastructure.tasks.state_machine import (
    TaskStateMachine,
    InvalidTransitionError,
    can_transition,
    is_terminal_status,
    VALID_TRANSITIONS,
)
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus


class TestValidTransitions:
    """Tests for the VALID_TRANSITIONS constant and can_transition function."""

    def test_completed_has_no_transitions(self):
        """COMPLETED is terminal — no transitions allowed."""
        assert VALID_TRANSITIONS[TaskStatus.COMPLETED] == []
        assert not can_transition(TaskStatus.COMPLETED, TaskStatus.READY)

    def test_failed_to_ready_is_valid(self):
        """FAILED tasks can transition to READY for retry."""
        assert TaskStatus.READY in VALID_TRANSITIONS[TaskStatus.FAILED]
        assert can_transition(TaskStatus.FAILED, TaskStatus.READY)

    def test_cancelled_to_ready_is_valid(self):
        """CANCELLED tasks can transition to READY for retry."""
        assert TaskStatus.READY in VALID_TRANSITIONS[TaskStatus.CANCELLED]
        assert can_transition(TaskStatus.CANCELLED, TaskStatus.READY)

    def test_superseded_has_no_transitions(self):
        """SUPERSEDED is terminal with no allowed transitions."""
        assert VALID_TRANSITIONS[TaskStatus.SUPERSEDED] == []
        assert not can_transition(TaskStatus.SUPERSEDED, TaskStatus.READY)

    def test_planning_to_ready_is_valid(self):
        """PLANNING can transition to READY after plan generation."""
        assert can_transition(TaskStatus.PLANNING, TaskStatus.READY)

    def test_ready_to_executing_is_valid(self):
        """READY can transition to EXECUTING when started."""
        assert can_transition(TaskStatus.READY, TaskStatus.EXECUTING)

    def test_executing_to_completed_is_valid(self):
        """EXECUTING can transition to COMPLETED when all steps done."""
        assert can_transition(TaskStatus.EXECUTING, TaskStatus.COMPLETED)

    def test_executing_to_checkpoint_is_valid(self):
        """EXECUTING can transition to CHECKPOINT."""
        assert can_transition(TaskStatus.EXECUTING, TaskStatus.CHECKPOINT)

    def test_checkpoint_to_executing_is_valid(self):
        """CHECKPOINT can return to EXECUTING on approval."""
        assert can_transition(TaskStatus.CHECKPOINT, TaskStatus.EXECUTING)

    def test_invalid_completed_to_executing(self):
        """COMPLETED cannot directly transition to EXECUTING."""
        assert not can_transition(TaskStatus.COMPLETED, TaskStatus.EXECUTING)

    def test_invalid_ready_to_completed(self):
        """READY cannot directly skip to COMPLETED."""
        assert not can_transition(TaskStatus.READY, TaskStatus.COMPLETED)


class TestIsTerminalStatus:
    """Tests for the is_terminal_status function."""

    def test_completed_is_terminal(self):
        """COMPLETED is a terminal status."""
        assert is_terminal_status(TaskStatus.COMPLETED)

    def test_failed_is_terminal(self):
        """FAILED is a terminal status."""
        assert is_terminal_status(TaskStatus.FAILED)

    def test_cancelled_is_terminal(self):
        """CANCELLED is a terminal status."""
        assert is_terminal_status(TaskStatus.CANCELLED)

    def test_superseded_is_terminal(self):
        """SUPERSEDED is a terminal status."""
        assert is_terminal_status(TaskStatus.SUPERSEDED)

    def test_planning_is_not_terminal(self):
        """PLANNING is not a terminal status."""
        assert not is_terminal_status(TaskStatus.PLANNING)

    def test_ready_is_not_terminal(self):
        """READY is not a terminal status."""
        assert not is_terminal_status(TaskStatus.READY)

    def test_executing_is_not_terminal(self):
        """EXECUTING is not a terminal status."""
        assert not is_terminal_status(TaskStatus.EXECUTING)


@pytest.fixture
def mock_pg_store():
    """Create a mock PostgreSQL task store."""
    store = AsyncMock()
    store.get_task = AsyncMock()
    store.update_task = AsyncMock()
    return store


@pytest.fixture
def mock_redis_store():
    """Create a mock Redis task store."""
    store = AsyncMock()
    store._get_redis = AsyncMock()
    store._plan_key = MagicMock(return_value="task:test-123")
    store._serialize_plan = MagicMock(return_value='{"id": "test-123"}')
    return store


@pytest.fixture
def completed_task():
    """Create a completed task for testing rerun transitions."""
    return Task(
        id="test-123",
        user_id="user-456",
        organization_id="org-789",
        goal="Test goal",
        status=TaskStatus.COMPLETED,
        steps=[
            TaskStep(
                id="step-1",
                name="Test step",
                description="Test description",
                agent_type="test",
                status=StepStatus.DONE,
            )
        ],
        completed_at=datetime.utcnow(),
    )


@pytest.fixture
def failed_task():
    """Create a failed task for testing retry transitions."""
    return Task(
        id="test-456",
        user_id="user-456",
        organization_id="org-789",
        goal="Test goal",
        status=TaskStatus.FAILED,
        steps=[
            TaskStep(
                id="step-1",
                name="Test step",
                description="Test description",
                agent_type="test",
                status=StepStatus.FAILED,
                error_message="Test error",
            )
        ],
    )


class TestTaskStateMachineTransition:
    """Tests for TaskStateMachine.transition method."""

    @pytest.mark.asyncio
    async def test_transition_completed_to_ready_fails(
        self, mock_pg_store, completed_task
    ):
        """COMPLETED → READY transition is rejected."""
        mock_pg_store.get_task.return_value = completed_task
        state_machine = TaskStateMachine(mock_pg_store)
        with pytest.raises(InvalidTransitionError):
            await state_machine.transition(completed_task.id, TaskStatus.READY)

    @pytest.mark.asyncio
    async def test_transition_failed_to_ready(
        self, mock_pg_store, mock_redis_store, failed_task
    ):
        """Test transitioning a failed task to ready for retry."""
        mock_pg_store.get_task.return_value = failed_task
        ready_task = Task(
            id=failed_task.id,
            user_id=failed_task.user_id,
            organization_id=failed_task.organization_id,
            goal=failed_task.goal,
            status=TaskStatus.READY,
            steps=failed_task.steps,
        )
        mock_pg_store.get_task.side_effect = [failed_task, ready_task]

        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_redis_store._get_redis.return_value = mock_client

        state_machine = TaskStateMachine(mock_pg_store, mock_redis_store)

        result = await state_machine.transition(failed_task.id, TaskStatus.READY)

        assert result.status == TaskStatus.READY

    @pytest.mark.asyncio
    async def test_transition_completed_to_executing_fails(
        self, mock_pg_store, completed_task
    ):
        """Test that direct COMPLETED -> EXECUTING transition is rejected."""
        mock_pg_store.get_task.return_value = completed_task

        state_machine = TaskStateMachine(mock_pg_store)

        with pytest.raises(InvalidTransitionError) as exc_info:
            await state_machine.transition(completed_task.id, TaskStatus.EXECUTING)

        assert exc_info.value.task_id == completed_task.id
        assert exc_info.value.current_status == TaskStatus.COMPLETED
        assert exc_info.value.target_status == TaskStatus.EXECUTING

    @pytest.mark.asyncio
    async def test_transition_task_not_found(self, mock_pg_store):
        """Test that transitioning non-existent task raises error."""
        mock_pg_store.get_task.return_value = None

        state_machine = TaskStateMachine(mock_pg_store)

        from src.domain.tasks.models import TaskNotFoundError
        with pytest.raises(TaskNotFoundError):
            await state_machine.transition("nonexistent-id", TaskStatus.READY)

    @pytest.mark.asyncio
    async def test_transition_sets_completed_at(self, mock_pg_store, mock_redis_store):
        """Test that transitioning to COMPLETED sets completed_at timestamp."""
        executing_task = Task(
            id="test-123",
            user_id="user-456",
            goal="Test goal",
            status=TaskStatus.EXECUTING,
            steps=[],
        )
        completed_task = Task(
            id="test-123",
            user_id="user-456",
            goal="Test goal",
            status=TaskStatus.COMPLETED,
            steps=[],
            completed_at=datetime.utcnow(),
        )
        mock_pg_store.get_task.side_effect = [executing_task, completed_task]

        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_redis_store._get_redis.return_value = mock_client

        state_machine = TaskStateMachine(mock_pg_store, mock_redis_store)

        await state_machine.transition("test-123", TaskStatus.COMPLETED)

        call_args = mock_pg_store.update_task.call_args
        assert "completed_at" in call_args[0][1]


class TestTaskStateMachineValidation:
    """Tests for TaskStateMachine validation methods."""

    def test_validate_transition_returns_true_for_valid(self, mock_pg_store):
        """validate_transition returns True for valid transitions."""
        state_machine = TaskStateMachine(mock_pg_store)

        assert state_machine.validate_transition(TaskStatus.FAILED, TaskStatus.READY)
        assert state_machine.validate_transition(TaskStatus.READY, TaskStatus.EXECUTING)

    def test_validate_transition_returns_false_for_invalid(self, mock_pg_store):
        """validate_transition returns False for invalid transitions."""
        state_machine = TaskStateMachine(mock_pg_store)

        assert not state_machine.validate_transition(TaskStatus.COMPLETED, TaskStatus.EXECUTING)
        assert not state_machine.validate_transition(TaskStatus.READY, TaskStatus.COMPLETED)
        assert not state_machine.validate_transition(TaskStatus.SUPERSEDED, TaskStatus.READY)

    def test_get_allowed_transitions(self, mock_pg_store):
        """get_allowed_transitions returns correct list for each status."""
        state_machine = TaskStateMachine(mock_pg_store)

        # COMPLETED is terminal — no transitions
        allowed = state_machine.get_allowed_transitions(TaskStatus.COMPLETED)
        assert allowed == []

        # READY can go to EXECUTING or CANCELLED
        allowed = state_machine.get_allowed_transitions(TaskStatus.READY)
        assert TaskStatus.EXECUTING in allowed
        assert TaskStatus.CANCELLED in allowed

        # SUPERSEDED has no allowed transitions
        allowed = state_machine.get_allowed_transitions(TaskStatus.SUPERSEDED)
        assert allowed == []


class TestPauseTransitions:
    """Tests for pause/resume state transitions."""

    def test_executing_to_paused_is_valid(self):
        """EXECUTING tasks can transition to PAUSED."""
        assert can_transition(TaskStatus.EXECUTING, TaskStatus.PAUSED)

    def test_paused_to_executing_is_valid(self):
        """PAUSED tasks can transition back to EXECUTING (resume)."""
        assert can_transition(TaskStatus.PAUSED, TaskStatus.EXECUTING)

    def test_paused_to_cancelled_is_valid(self):
        """PAUSED tasks can be cancelled."""
        assert can_transition(TaskStatus.PAUSED, TaskStatus.CANCELLED)

    def test_ready_to_paused_is_invalid(self):
        """READY tasks cannot be paused (must be executing first)."""
        assert not can_transition(TaskStatus.READY, TaskStatus.PAUSED)

    def test_completed_to_paused_is_invalid(self):
        """COMPLETED tasks cannot be paused."""
        assert not can_transition(TaskStatus.COMPLETED, TaskStatus.PAUSED)

    def test_paused_to_completed_is_invalid(self):
        """PAUSED tasks cannot complete directly (must execute first)."""
        assert not can_transition(TaskStatus.PAUSED, TaskStatus.COMPLETED)


@pytest.fixture
def executing_task():
    """Create an executing task for testing pause transitions."""
    return Task(
        id="test-789",
        user_id="user-456",
        organization_id="org-789",
        goal="Test goal",
        status=TaskStatus.EXECUTING,
        tree_id="test-789",
        steps=[
            TaskStep(
                id="step-1",
                name="Test step",
                description="Test description",
                agent_type="test",
                status=StepStatus.RUNNING,
            )
        ],
    )


@pytest.fixture
def paused_task():
    """Create a paused task for testing resume transitions."""
    return Task(
        id="test-pause-123",
        user_id="user-456",
        organization_id="org-789",
        goal="Test goal",
        status=TaskStatus.PAUSED,
        tree_id="test-pause-123",
        steps=[
            TaskStep(
                id="step-1",
                name="Test step",
                description="Test description",
                agent_type="test",
                status=StepStatus.PENDING,
            )
        ],
    )


class TestPauseStateMachineTransitions:
    """Tests for TaskStateMachine pause/resume transitions."""

    @pytest.mark.asyncio
    async def test_transition_executing_to_paused(
        self, mock_pg_store, mock_redis_store, executing_task
    ):
        """Test transitioning an executing task to paused."""
        mock_pg_store.get_task.return_value = executing_task
        paused_task = Task(
            id=executing_task.id,
            user_id=executing_task.user_id,
            organization_id=executing_task.organization_id,
            goal=executing_task.goal,
            status=TaskStatus.PAUSED,
            tree_id=executing_task.tree_id,
            steps=executing_task.steps,
        )
        mock_pg_store.get_task.side_effect = [executing_task, paused_task]

        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_redis_store._get_redis.return_value = mock_client

        state_machine = TaskStateMachine(mock_pg_store, mock_redis_store)

        result = await state_machine.transition(executing_task.id, TaskStatus.PAUSED)

        assert result.status == TaskStatus.PAUSED
        mock_pg_store.update_task.assert_called_once()
        call_args = mock_pg_store.update_task.call_args
        assert call_args[0][0] == executing_task.id
        assert call_args[0][1]["status"] == TaskStatus.PAUSED

    @pytest.mark.asyncio
    async def test_transition_paused_to_executing(
        self, mock_pg_store, mock_redis_store, paused_task
    ):
        """Test transitioning a paused task back to executing (resume)."""
        mock_pg_store.get_task.return_value = paused_task
        executing_task = Task(
            id=paused_task.id,
            user_id=paused_task.user_id,
            organization_id=paused_task.organization_id,
            goal=paused_task.goal,
            status=TaskStatus.EXECUTING,
            tree_id=paused_task.tree_id,
            steps=paused_task.steps,
        )
        mock_pg_store.get_task.side_effect = [paused_task, executing_task]

        mock_client = AsyncMock()
        mock_client.set = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_redis_store._get_redis.return_value = mock_client

        state_machine = TaskStateMachine(mock_pg_store, mock_redis_store)

        result = await state_machine.transition(paused_task.id, TaskStatus.EXECUTING)

        assert result.status == TaskStatus.EXECUTING

    @pytest.mark.asyncio
    async def test_transition_ready_to_paused_fails(
        self, mock_pg_store
    ):
        """Test that READY -> PAUSED transition is rejected."""
        ready_task = Task(
            id="test-ready",
            user_id="user-456",
            goal="Test goal",
            status=TaskStatus.READY,
            steps=[],
        )
        mock_pg_store.get_task.return_value = ready_task

        state_machine = TaskStateMachine(mock_pg_store)

        with pytest.raises(InvalidTransitionError) as exc_info:
            await state_machine.transition(ready_task.id, TaskStatus.PAUSED)

        assert exc_info.value.current_status == TaskStatus.READY
        assert exc_info.value.target_status == TaskStatus.PAUSED
