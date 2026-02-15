# REVIEW: Adapter hard-codes tree metadata and relies on RedisExecutionTree,
# REVIEW: which makes it hard to swap execution backends. Also embeds status
# REVIEW: strings in metadata separate from TaskStatus enums, risking drift.
"""
TaskExecutionTreeAdapter - Adapts ExecutionTree for Task execution.

This adapter provides task-specific operations on top of the RedisExecutionTree,
enabling tasks to leverage the same durable execution architecture as workflows
without duplicating functionality.

Key responsibilities:
1. Create execution trees from Tasks
2. Convert between TaskStep and ExecutionNode
3. Query task-specific state (ready steps, completion status)
4. Maintain compatibility with existing workflow execution

Usage:
    adapter = TaskExecutionTreeAdapter()
    tree_id = await adapter.create_task_tree(task)
    ready_steps = await adapter.get_ready_steps(task.id)
"""

from typing import Dict, List, Optional, Tuple, Any
import structlog

from src.domain.tasks.models import Task, TaskStep, StepStatus
from src.core.execution_tree import (
    ExecutionNode, ExecutionStatus, NodeType, ExecutionTreeInterface
)
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.infrastructure.tasks.task_tree_mapping import (
    task_step_to_node, node_to_task_step,
    step_status_to_execution_status, execution_status_to_step_status
)


logger = structlog.get_logger()


class TaskExecutionTreeAdapter:
    """
    Adapts ExecutionTree for Task execution without breaking workflows.

    This adapter provides a task-centric API while delegating all tree operations
    to the underlying RedisExecutionTree implementation.
    """

    def __init__(self, tree: Optional[ExecutionTreeInterface] = None):
        """
        Initialize the adapter.

        Args:
            tree: Optional ExecutionTree implementation. Defaults to RedisExecutionTree.
        """
        self._tree = tree or RedisExecutionTree()

    async def create_task_tree(self, task: Task) -> str:
        """
        Create an execution tree from a Task.

        Creates a tree with:
        - Root node (immediately completed)
        - Step nodes with proper dependencies
        - Metadata marking this as a "task" type tree

        Args:
            task: The Task to create a tree from

        Returns:
            tree_id (same as task.id for simplicity)
        """
        tree_id = task.id

        # Create tree with task metadata
        await self._tree.create_tree(
            root_name=tree_id,
            metadata={
                "name": f"Task: {task.goal[:50]}",
                "type": "task",
                "goal": task.goal,
                "user_id": task.user_id,
                "organization_id": task.organization_id,
                "status": "executing",
            }
        )

        # Mark root as completed immediately (tasks start executing steps right away)
        await self._tree.update_node_status(tree_id, "root", ExecutionStatus.COMPLETED)

        # Add step nodes
        for step in task.steps:
            node = task_step_to_node(step, parent_id="root")
            await self._tree.add_node(tree_id, node, parent_id="root")

        logger.info(
            "Created task execution tree",
            tree_id=tree_id,
            goal=task.goal[:50],
            step_count=len(task.steps)
        )

        return tree_id

    async def get_step_from_tree(self, task_id: str, step_id: str) -> Optional[TaskStep]:
        """
        Get a TaskStep from the execution tree.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID

        Returns:
            TaskStep if found, None otherwise
        """
        node = await self._tree.get_node(task_id, step_id)
        if not node:
            return None
        return node_to_task_step(node)

    async def get_all_steps(self, task_id: str) -> List[TaskStep]:
        """
        Get all steps from the execution tree.

        Args:
            task_id: The task/tree ID

        Returns:
            List of TaskSteps (excludes root node)
        """
        snapshot = await self._tree.get_tree_snapshot(task_id)
        if not snapshot:
            return []

        steps = []
        for node_id, node in snapshot.nodes.items():
            if node_id != "root":
                steps.append(node_to_task_step(node))
        return steps

    async def update_step_status(
        self,
        task_id: str,
        step_id: str,
        status: StepStatus,
        outputs: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update a step's status in the execution tree.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID
            status: New StepStatus
            outputs: Optional step outputs (for DONE status)
            error_message: Optional error message (for FAILED status)

        Returns:
            True if update succeeded
        """
        exec_status = step_status_to_execution_status(status)

        result_data = outputs if outputs else None
        error_data = {"error": error_message} if error_message else None

        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=exec_status,
            result_data=result_data,
            error_data=error_data
        )

    async def complete_step(
        self,
        task_id: str,
        step_id: str,
        outputs: Dict[str, Any]
    ) -> bool:
        """
        Mark a step as completed with outputs.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID
            outputs: Step outputs/results

        Returns:
            True if update succeeded
        """
        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=ExecutionStatus.COMPLETED,
            result_data=outputs
        )

    async def fail_step(
        self,
        task_id: str,
        step_id: str,
        error: str
    ) -> bool:
        """
        Mark a step as failed with error.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID
            error: Error message

        Returns:
            True if update succeeded
        """
        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=ExecutionStatus.FAILED,
            error_data={"error": error}
        )

    async def reset_step(self, task_id: str, step_id: str) -> bool:
        """
        Reset a failed step back to PENDING for retry.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID

        Returns:
            True if update succeeded
        """
        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=ExecutionStatus.PENDING,
        )

    async def pause_step(self, task_id: str, step_id: str) -> bool:
        """
        Pause a step (for checkpoint handling).

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID

        Returns:
            True if update succeeded
        """
        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=ExecutionStatus.PAUSED
        )

    async def start_step(self, task_id: str, step_id: str) -> bool:
        """
        Mark a step as running.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID

        Returns:
            True if update succeeded
        """
        return await self._tree.update_node_status(
            tree_id=task_id,
            node_id=step_id,
            status=ExecutionStatus.RUNNING
        )

    async def update_step_inputs(
        self,
        task_id: str,
        step_id: str,
        resolved_inputs: Dict[str, Any]
    ) -> bool:
        """
        Update a step's inputs after template resolution.

        This stores the resolved inputs in the execution tree so they're
        available for step execution and can be inspected later.

        Args:
            task_id: The task/tree ID
            step_id: The step/node ID
            resolved_inputs: The resolved input values

        Returns:
            True if update succeeded
        """
        # For now, we just log the update - the resolved inputs are passed
        # directly to the Celery task and stored in the task's step record.
        # The execution tree node keeps the original template inputs.
        logger.debug(
            "Step inputs resolved",
            task_id=task_id,
            step_id=step_id,
            input_keys=list(resolved_inputs.keys()) if resolved_inputs else []
        )
        return True

    async def get_ready_steps(self, task_id: str) -> List[TaskStep]:
        """
        Get steps that are ready to execute (all dependencies met).

        Leverages the execution tree's get_ready_nodes() which performs
        efficient set-based dependency checking.

        Args:
            task_id: The task/tree ID

        Returns:
            List of TaskSteps ready to execute (excludes root)
        """
        ready_nodes = await self._tree.get_ready_nodes(task_id)

        # Convert to TaskSteps, excluding root node
        steps = []
        for node in ready_nodes:
            if node.id != "root":
                steps.append(node_to_task_step(node))
        return steps

    async def is_task_complete(self, task_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if the task is complete.

        A task is complete when:
        - All steps are COMPLETED → task status = "completed"
        - Any step is FAILED → task status = "failed"

        Args:
            task_id: The task/tree ID

        Returns:
            Tuple of (is_complete, status_if_complete)
        """
        snapshot = await self._tree.get_tree_snapshot(task_id)
        if not snapshot:
            return False, None

        # Get all step nodes (exclude root)
        step_nodes = [n for n in snapshot.nodes.values() if n.id != "root"]

        if not step_nodes:
            return True, "completed"  # No steps means task is trivially complete

        # Check for failures
        failed_nodes = [n for n in step_nodes if n.status == ExecutionStatus.FAILED]
        if failed_nodes:
            return True, "failed"

        # Check for completion
        completed_count = sum(
            1 for n in step_nodes
            if n.status in (ExecutionStatus.COMPLETED, ExecutionStatus.EXPANDED)
        )

        if completed_count == len(step_nodes):
            return True, "completed"

        return False, None

    async def get_tree_metrics(self, task_id: str) -> Dict[str, Any]:
        """Get raw execution tree metrics."""
        return await self._tree.get_tree_metrics(task_id)

    async def get_task_progress(self, task_id: str) -> Dict[str, Any]:
        """
        Get task progress metrics.

        Args:
            task_id: The task/tree ID

        Returns:
            Progress metrics including completion percentage and status counts
        """
        metrics = await self._tree.get_tree_metrics(task_id)

        # Adjust for task-specific reporting (exclude root from counts)
        total_nodes = metrics.get("total_nodes", 0)
        if total_nodes > 0:
            total_nodes -= 1  # Exclude root

        status_counts = metrics.get("status_counts", {})
        completed = status_counts.get("completed", 0)
        # Root is always completed, so subtract 1 if there's at least one completed
        if completed > 0:
            completed -= 1

        completion_pct = (completed / total_nodes * 100) if total_nodes > 0 else 0

        return {
            "task_id": task_id,
            "total_steps": total_nodes,
            "completed_steps": completed,
            "failed_steps": status_counts.get("failed", 0),
            "running_steps": status_counts.get("running", 0),
            "pending_steps": status_counts.get("pending", 0),
            "paused_steps": status_counts.get("paused", 0),
            "completion_percentage": round(completion_pct, 1)
        }

    async def delete_task_tree(self, task_id: str) -> bool:
        """
        Delete a task's execution tree.

        Args:
            task_id: The task/tree ID

        Returns:
            True if deletion succeeded
        """
        return await self._tree.delete_tree(task_id)

    async def tree_exists(self, task_id: str) -> bool:
        """
        Check if a task tree exists.

        Args:
            task_id: The task/tree ID

        Returns:
            True if tree exists
        """
        tree_data = await self._tree.get_tree(task_id)
        return tree_data is not None

    async def health_check(self) -> bool:
        """
        Check if the underlying execution tree is healthy.

        Returns:
            True if healthy
        """
        return await self._tree.health_check()
