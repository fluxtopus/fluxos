"""
Unit tests for TaskExecutionTreeAdapter.

Tests the adapter logic using mocked ExecutionTree to ensure correct
translation between Task/TaskStep and ExecutionNode concepts.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.domain.tasks.models import (
    Task, TaskStep, StepStatus, TaskStatus,
    CheckpointConfig, ApprovalType, CheckpointType
)
from src.core.execution_tree import (
    ExecutionNode, ExecutionStatus, NodeType, ExecutionPriority,
    ExecutionTreeSnapshot, ExecutionMetrics
)
from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter


@pytest.fixture
def mock_tree():
    """Create a mock ExecutionTree."""
    tree = AsyncMock()
    tree.create_tree = AsyncMock(return_value="test-tree-id")
    tree.add_node = AsyncMock(return_value=True)
    tree.get_node = AsyncMock(return_value=None)
    tree.update_node_status = AsyncMock(return_value=True)
    tree.get_ready_nodes = AsyncMock(return_value=[])
    tree.get_tree_snapshot = AsyncMock(return_value=None)
    tree.get_tree_metrics = AsyncMock(return_value={})
    tree.delete_tree = AsyncMock(return_value=True)
    tree.get_tree = AsyncMock(return_value=None)
    tree.health_check = AsyncMock(return_value=True)
    return tree


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="task-123",
        user_id="user-456",
        organization_id="org-789",
        goal="Research AI developments and summarize",
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
        ]
    )


@pytest.fixture
def adapter(mock_tree):
    """Create adapter with mock tree."""
    return TaskExecutionTreeAdapter(tree=mock_tree)


class TestCreateTaskTree:
    """Tests for create_task_tree method."""

    async def test_creates_tree_with_task_metadata(self, adapter, mock_tree, sample_task):
        """Tree is created with correct task metadata."""
        await adapter.create_task_tree(sample_task)

        mock_tree.create_tree.assert_called_once()
        call_args = mock_tree.create_tree.call_args
        assert call_args.kwargs["root_name"] == "task-123"
        assert call_args.kwargs["metadata"]["type"] == "task"
        assert call_args.kwargs["metadata"]["goal"] == sample_task.goal
        assert call_args.kwargs["metadata"]["user_id"] == "user-456"

    async def test_marks_root_as_completed(self, adapter, mock_tree, sample_task):
        """Root node is marked as completed immediately."""
        await adapter.create_task_tree(sample_task)

        # Check that root was marked completed
        update_calls = mock_tree.update_node_status.call_args_list
        root_update = [c for c in update_calls if c.args[1] == "root"]
        assert len(root_update) == 1
        assert root_update[0].args[2] == ExecutionStatus.COMPLETED

    async def test_adds_step_nodes(self, adapter, mock_tree, sample_task):
        """All steps are added as nodes."""
        await adapter.create_task_tree(sample_task)

        # Should be called twice (once per step)
        assert mock_tree.add_node.call_count == 2

        # Verify node IDs match step IDs
        added_nodes = [call.args[1] for call in mock_tree.add_node.call_args_list]
        node_ids = [n.id for n in added_nodes]
        assert "step-1" in node_ids
        assert "step-2" in node_ids

    async def test_returns_tree_id(self, adapter, mock_tree, sample_task):
        """Returns the tree_id (same as task.id)."""
        tree_id = await adapter.create_task_tree(sample_task)
        assert tree_id == "task-123"


class TestGetStepFromTree:
    """Tests for get_step_from_tree method."""

    async def test_returns_none_if_not_found(self, adapter, mock_tree):
        """Returns None when node doesn't exist."""
        mock_tree.get_node.return_value = None

        step = await adapter.get_step_from_tree("task-1", "step-nonexistent")

        assert step is None

    async def test_converts_node_to_step(self, adapter, mock_tree):
        """Converts ExecutionNode to TaskStep."""
        node = ExecutionNode(
            id="step-1",
            name="Research Step",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.COMPLETED,
            result_data={"findings": ["item1", "item2"]},
            metadata={
                "agent_type": "web_research",
                "description": "Gather data"
            }
        )
        mock_tree.get_node.return_value = node

        step = await adapter.get_step_from_tree("task-1", "step-1")

        assert step is not None
        assert step.id == "step-1"
        assert step.name == "Research Step"
        assert step.status == StepStatus.DONE
        assert step.outputs == {"findings": ["item1", "item2"]}


class TestUpdateStepStatus:
    """Tests for step status update methods."""

    async def test_update_step_status_maps_correctly(self, adapter, mock_tree):
        """StepStatus is correctly mapped to ExecutionStatus."""
        await adapter.update_step_status("task-1", "step-1", StepStatus.RUNNING)

        mock_tree.update_node_status.assert_called_once_with(
            tree_id="task-1",
            node_id="step-1",
            status=ExecutionStatus.RUNNING,
            result_data=None,
            error_data=None
        )

    async def test_complete_step_with_outputs(self, adapter, mock_tree):
        """complete_step passes outputs as result_data."""
        outputs = {"summary": "AI is advancing rapidly"}

        await adapter.complete_step("task-1", "step-1", outputs)

        mock_tree.update_node_status.assert_called_once_with(
            tree_id="task-1",
            node_id="step-1",
            status=ExecutionStatus.COMPLETED,
            result_data=outputs
        )

    async def test_fail_step_with_error(self, adapter, mock_tree):
        """fail_step passes error as error_data."""
        await adapter.fail_step("task-1", "step-1", "Connection timeout")

        mock_tree.update_node_status.assert_called_once_with(
            tree_id="task-1",
            node_id="step-1",
            status=ExecutionStatus.FAILED,
            error_data={"error": "Connection timeout"}
        )

    async def test_pause_step(self, adapter, mock_tree):
        """pause_step marks node as PAUSED."""
        await adapter.pause_step("task-1", "step-1")

        mock_tree.update_node_status.assert_called_once_with(
            tree_id="task-1",
            node_id="step-1",
            status=ExecutionStatus.PAUSED
        )

    async def test_start_step(self, adapter, mock_tree):
        """start_step marks node as RUNNING."""
        await adapter.start_step("task-1", "step-1")

        mock_tree.update_node_status.assert_called_once_with(
            tree_id="task-1",
            node_id="step-1",
            status=ExecutionStatus.RUNNING
        )


class TestGetReadySteps:
    """Tests for get_ready_steps method."""

    async def test_excludes_root_node(self, adapter, mock_tree):
        """Root node is filtered out from ready steps."""
        root_node = ExecutionNode(id="root", name="Root", node_type=NodeType.ROOT)
        step_node = ExecutionNode(
            id="step-1",
            name="Step 1",
            node_type=NodeType.AGENT,
            metadata={"agent_type": "processor", "description": ""}
        )
        mock_tree.get_ready_nodes.return_value = [root_node, step_node]

        ready = await adapter.get_ready_steps("task-1")

        assert len(ready) == 1
        assert ready[0].id == "step-1"

    async def test_returns_empty_list_when_no_ready(self, adapter, mock_tree):
        """Returns empty list when no nodes are ready."""
        mock_tree.get_ready_nodes.return_value = []

        ready = await adapter.get_ready_steps("task-1")

        assert ready == []

    async def test_converts_all_ready_nodes_to_steps(self, adapter, mock_tree):
        """All ready nodes are converted to TaskSteps."""
        nodes = [
            ExecutionNode(
                id=f"step-{i}",
                name=f"Step {i}",
                node_type=NodeType.AGENT,
                metadata={"agent_type": "processor", "description": ""}
            )
            for i in range(3)
        ]
        mock_tree.get_ready_nodes.return_value = nodes

        ready = await adapter.get_ready_steps("task-1")

        assert len(ready) == 3
        assert all(isinstance(s, TaskStep) for s in ready)


class TestIsTaskComplete:
    """Tests for is_task_complete method."""

    async def test_returns_false_when_no_tree(self, adapter, mock_tree):
        """Returns (False, None) when tree doesn't exist."""
        mock_tree.get_tree_snapshot.return_value = None

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is False
        assert status is None

    async def test_returns_completed_when_all_steps_done(self, adapter, mock_tree):
        """Returns (True, 'completed') when all steps are COMPLETED."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(id="step-1", status=ExecutionStatus.COMPLETED),
                "step-2": ExecutionNode(id="step-2", status=ExecutionStatus.COMPLETED),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is True
        assert status == "completed"

    async def test_returns_failed_when_any_step_failed(self, adapter, mock_tree):
        """Returns (True, 'failed') when any step is FAILED."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(id="step-1", status=ExecutionStatus.COMPLETED),
                "step-2": ExecutionNode(id="step-2", status=ExecutionStatus.FAILED),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is True
        assert status == "failed"

    async def test_returns_false_when_steps_pending(self, adapter, mock_tree):
        """Returns (False, None) when some steps are still PENDING."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(id="step-1", status=ExecutionStatus.COMPLETED),
                "step-2": ExecutionNode(id="step-2", status=ExecutionStatus.PENDING),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is False
        assert status is None

    async def test_returns_false_when_steps_running(self, adapter, mock_tree):
        """Returns (False, None) when some steps are still RUNNING."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(id="step-1", status=ExecutionStatus.RUNNING),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is False
        assert status is None

    async def test_empty_task_is_complete(self, adapter, mock_tree):
        """Task with no steps is trivially complete."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        is_complete, status = await adapter.is_task_complete("task-1")

        assert is_complete is True
        assert status == "completed"


class TestGetTaskProgress:
    """Tests for get_task_progress method."""

    async def test_returns_correct_metrics(self, adapter, mock_tree):
        """Progress metrics are calculated correctly."""
        mock_tree.get_tree_metrics.return_value = {
            "total_nodes": 4,  # root + 3 steps
            "status_counts": {
                "completed": 2,  # root + 1 step
                "running": 1,
                "pending": 1,
                "failed": 0,
                "paused": 0,
            }
        }

        progress = await adapter.get_task_progress("task-1")

        assert progress["total_steps"] == 3  # Excludes root
        assert progress["completed_steps"] == 1  # Excludes root
        assert progress["running_steps"] == 1
        assert progress["pending_steps"] == 1
        assert progress["completion_percentage"] == pytest.approx(33.3, rel=0.1)


class TestTreeOperations:
    """Tests for tree lifecycle operations."""

    async def test_delete_task_tree(self, adapter, mock_tree):
        """delete_task_tree delegates to tree.delete_tree."""
        result = await adapter.delete_task_tree("task-1")

        mock_tree.delete_tree.assert_called_once_with("task-1")
        assert result is True

    async def test_tree_exists_returns_true_when_found(self, adapter, mock_tree):
        """tree_exists returns True when tree data exists."""
        mock_tree.get_tree.return_value = {"tree_id": "task-1"}

        exists = await adapter.tree_exists("task-1")

        assert exists is True

    async def test_tree_exists_returns_false_when_not_found(self, adapter, mock_tree):
        """tree_exists returns False when tree data is None."""
        mock_tree.get_tree.return_value = None

        exists = await adapter.tree_exists("task-1")

        assert exists is False

    async def test_health_check(self, adapter, mock_tree):
        """health_check delegates to tree.health_check."""
        result = await adapter.health_check()

        mock_tree.health_check.assert_called_once()
        assert result is True


class TestGetAllSteps:
    """Tests for get_all_steps method."""

    async def test_returns_empty_list_when_no_tree(self, adapter, mock_tree):
        """Returns empty list when tree doesn't exist."""
        mock_tree.get_tree_snapshot.return_value = None

        steps = await adapter.get_all_steps("task-1")

        assert steps == []

    async def test_excludes_root_node(self, adapter, mock_tree):
        """Root node is not included in returned steps."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(
                    id="step-1",
                    name="Step 1",
                    status=ExecutionStatus.PENDING,
                    metadata={"agent_type": "processor", "description": ""}
                ),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        steps = await adapter.get_all_steps("task-1")

        assert len(steps) == 1
        assert steps[0].id == "step-1"

    async def test_returns_all_steps(self, adapter, mock_tree):
        """Returns all step nodes as TaskSteps."""
        snapshot = ExecutionTreeSnapshot(
            tree_id="task-1",
            root_node_id="root",
            nodes={
                "root": ExecutionNode(id="root", status=ExecutionStatus.COMPLETED),
                "step-1": ExecutionNode(
                    id="step-1",
                    name="Step 1",
                    status=ExecutionStatus.COMPLETED,
                    metadata={"agent_type": "analyzer", "description": ""}
                ),
                "step-2": ExecutionNode(
                    id="step-2",
                    name="Step 2",
                    status=ExecutionStatus.PENDING,
                    metadata={"agent_type": "summarizer", "description": ""}
                ),
            }
        )
        mock_tree.get_tree_snapshot.return_value = snapshot

        steps = await adapter.get_all_steps("task-1")

        assert len(steps) == 2
        step_ids = {s.id for s in steps}
        assert step_ids == {"step-1", "step-2"}
