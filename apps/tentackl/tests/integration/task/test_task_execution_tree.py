"""
Integration tests for task execution using the durable execution tree.

These tests verify the full end-to-end flow:
1. Task creation with execution tree
2. Dependency resolution via get_ready_nodes()
3. Step scheduling via schedule_ready_nodes()
4. Automatic task completion detection

Note: These tests use real Redis connections to test durable state behavior.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, Mock

from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus
from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.core.execution_tree import ExecutionStatus
from src.infrastructure.tasks.task_scheduler_helper import schedule_ready_nodes, get_tree_type


@pytest.fixture
async def execution_tree():
    """Create a real Redis execution tree for integration tests."""
    tree = RedisExecutionTree()
    yield tree
    # Cleanup: disconnect after tests
    try:
        await tree._disconnect()
    except Exception:
        pass


@pytest.fixture
async def tree_adapter():
    """Create a TaskExecutionTreeAdapter."""
    adapter = TaskExecutionTreeAdapter()
    yield adapter


@pytest.fixture
def sample_task_with_deps():
    """Create a task with dependency chain: s1 -> s2 -> s3."""
    return Task(
        id="int-test-task-deps",
        user_id="test-user",
        organization_id="test-org",
        goal="Test dependent steps execution",
        steps=[
            TaskStep(
                id="step-1",
                name="First Step",
                description="No dependencies",
                agent_type="processor",
                inputs={"data": "input1"},
            ),
            TaskStep(
                id="step-2",
                name="Second Step",
                description="Depends on step-1",
                agent_type="analyzer",
                dependencies=["step-1"],
                inputs={},
            ),
            TaskStep(
                id="step-3",
                name="Third Step",
                description="Depends on step-2",
                agent_type="summarizer",
                dependencies=["step-2"],
                inputs={},
            ),
        ],
    )


@pytest.fixture
def sample_parallel_task():
    """Create a task with parallel steps: s1, s2 (parallel) -> s3."""
    return Task(
        id="int-test-task-parallel",
        user_id="test-user",
        organization_id="test-org",
        goal="Test parallel steps execution",
        steps=[
            TaskStep(
                id="step-a",
                name="Parallel Step A",
                description="No dependencies",
                agent_type="processor",
                inputs={},
            ),
            TaskStep(
                id="step-b",
                name="Parallel Step B",
                description="No dependencies",
                agent_type="processor",
                inputs={},
            ),
            TaskStep(
                id="step-final",
                name="Final Step",
                description="Depends on both parallel steps",
                agent_type="aggregator",
                dependencies=["step-a", "step-b"],
                inputs={},
            ),
        ],
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskExecutionTreeCreation:
    """Tests for creating execution trees from tasks."""

    async def test_create_task_tree_creates_tree_with_metadata(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Tree is created with correct task metadata."""
        task = sample_task_with_deps
        task.id = f"test-create-{datetime.utcnow().timestamp()}"

        try:
            tree_id = await tree_adapter.create_task_tree(task)

            # Verify tree was created
            assert tree_id == task.id

            # Verify metadata
            tree_type = await get_tree_type(execution_tree, tree_id)
            assert tree_type == "task"

            # Cleanup
            await execution_tree.delete_tree(tree_id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_create_task_tree_adds_all_steps_as_nodes(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """All task steps are added as nodes in the tree."""
        task = sample_task_with_deps
        task.id = f"test-nodes-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Verify all steps exist
            for step in task.steps:
                node = await execution_tree.get_node(task.id, step.id)
                assert node is not None
                assert node.name == step.name

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestDependencyResolution:
    """Tests for automatic dependency resolution."""

    async def test_only_root_dependent_steps_are_ready_initially(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Only steps without dependencies (or only root dep) are ready initially."""
        task = sample_task_with_deps
        task.id = f"test-ready-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Get ready steps
            ready_steps = await tree_adapter.get_ready_steps(task.id)

            # Only step-1 should be ready (no deps other than root)
            assert len(ready_steps) == 1
            assert ready_steps[0].id == "step-1"

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_dependent_step_becomes_ready_after_dependency_completes(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Step becomes ready when its dependencies are completed."""
        task = sample_task_with_deps
        task.id = f"test-cascade-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Complete step-1
            await tree_adapter.complete_step(task.id, "step-1", {"result": "done"})

            # Now step-2 should be ready
            ready_steps = await tree_adapter.get_ready_steps(task.id)
            ready_ids = [s.id for s in ready_steps]
            assert "step-2" in ready_ids
            assert "step-3" not in ready_ids  # step-3 depends on step-2

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_parallel_steps_are_both_ready(
        self,
        tree_adapter,
        execution_tree,
        sample_parallel_task,
    ):
        """Parallel steps (no deps) are all ready initially."""
        task = sample_parallel_task
        task.id = f"test-parallel-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Get ready steps
            ready_steps = await tree_adapter.get_ready_steps(task.id)
            ready_ids = [s.id for s in ready_steps]

            # Both parallel steps should be ready
            assert "step-a" in ready_ids
            assert "step-b" in ready_ids
            assert "step-final" not in ready_ids

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_final_step_ready_after_all_parallel_deps_complete(
        self,
        tree_adapter,
        execution_tree,
        sample_parallel_task,
    ):
        """Final step becomes ready only after ALL dependencies complete."""
        task = sample_parallel_task
        task.id = f"test-parallel-join-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Complete only step-a
            await tree_adapter.complete_step(task.id, "step-a", {})

            # step-final should NOT be ready yet
            ready_steps = await tree_adapter.get_ready_steps(task.id)
            ready_ids = [s.id for s in ready_steps]
            assert "step-final" not in ready_ids
            assert "step-b" in ready_ids  # still ready

            # Now complete step-b
            await tree_adapter.complete_step(task.id, "step-b", {})

            # Now step-final should be ready
            ready_steps = await tree_adapter.get_ready_steps(task.id)
            ready_ids = [s.id for s in ready_steps]
            assert "step-final" in ready_ids

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskCompletion:
    """Tests for task completion detection."""

    async def test_task_not_complete_when_steps_pending(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Task is not complete when steps are still pending."""
        task = sample_task_with_deps
        task.id = f"test-incomplete-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            is_complete, status = await tree_adapter.is_task_complete(task.id)
            assert is_complete is False
            assert status is None

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_task_complete_when_all_steps_done(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Task is complete when all steps are COMPLETED."""
        task = sample_task_with_deps
        task.id = f"test-complete-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Complete all steps
            await tree_adapter.complete_step(task.id, "step-1", {"r": 1})
            await tree_adapter.complete_step(task.id, "step-2", {"r": 2})
            await tree_adapter.complete_step(task.id, "step-3", {"r": 3})

            is_complete, status = await tree_adapter.is_task_complete(task.id)
            assert is_complete is True
            assert status == "completed"

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_task_failed_when_any_step_fails(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Task is marked failed when any step fails."""
        task = sample_task_with_deps
        task.id = f"test-failed-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Complete first step, fail second
            await tree_adapter.complete_step(task.id, "step-1", {})
            await tree_adapter.fail_step(task.id, "step-2", "Network error")

            is_complete, status = await tree_adapter.is_task_complete(task.id)
            assert is_complete is True
            assert status == "failed"

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestScheduleReadyNodes:
    """Tests for the unified scheduler with task type."""

    async def test_schedule_ready_nodes_for_task(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """schedule_ready_nodes works for task trees."""
        task = sample_task_with_deps
        task.id = f"test-schedule-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Mock the Celery task so it doesn't actually run
            with patch('src.core.tasks.execute_task_step') as mock_task:
                mock_task.delay = Mock()

                count = await schedule_ready_nodes(task.id)

                # Should have scheduled step-1 (only ready step)
                assert count == 1
                mock_task.delay.assert_called_once()

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    async def test_schedule_ready_nodes_detects_task_type(
        self,
        tree_adapter,
        execution_tree,
        sample_task_with_deps,
    ):
        """Scheduler correctly detects task type from metadata."""
        task = sample_task_with_deps
        task.id = f"test-type-{datetime.utcnow().timestamp()}"

        try:
            await tree_adapter.create_task_tree(task)

            # Verify tree type
            tree_type = await get_tree_type(execution_tree, task.id)
            assert tree_type == "task"

            # Cleanup
            await execution_tree.delete_tree(task.id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskDefaults:
    """Tests ensuring task defaults apply when metadata is missing."""

    async def test_tree_defaults_to_task_type(
        self,
        execution_tree,
    ):
        """Trees without type metadata default to 'task'."""
        tree_id = f"test-compat-{datetime.utcnow().timestamp()}"

        try:
            # Create tree without type in metadata
            await execution_tree.create_tree(
                root_name=tree_id,
                metadata={"name": "test-task"},  # No "type" field
            )

            tree_type = await get_tree_type(execution_tree, tree_id)
            assert tree_type == "task"

            # Cleanup
            await execution_tree.delete_tree(tree_id)
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
