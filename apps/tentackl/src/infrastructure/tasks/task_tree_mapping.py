# REVIEW: The mapping relies on duplicated status translation tables and
# REVIEW: metadata dictionaries, which can drift from TaskStep/ExecutionNode
# REVIEW: schemas. Consider centralizing mapping definitions or using a
# REVIEW: serialization layer with explicit versioning.
"""
Task ↔ ExecutionTree Mapping Functions

This module provides bidirectional mapping between Task/TaskStep models
and ExecutionNode/ExecutionTree structures. This enables tasks to leverage
the durable execution tree architecture used by workflows.

Key mappings:
- TaskStep.status (StepStatus) ↔ ExecutionNode.status (ExecutionStatus)
- TaskStep.dependencies (List[str]) ↔ ExecutionNode.dependencies (Set[str])
- TaskStep metadata ↔ ExecutionNode.metadata/task_data
"""

from typing import Optional

from src.domain.tasks.models import TaskStep, StepStatus, CheckpointConfig, FallbackConfig
from src.core.execution_tree import ExecutionNode, ExecutionStatus, NodeType, ExecutionPriority


# Status mappings: StepStatus → ExecutionStatus
STEP_TO_EXECUTION_STATUS = {
    StepStatus.PENDING: ExecutionStatus.PENDING,
    StepStatus.RUNNING: ExecutionStatus.RUNNING,
    StepStatus.DONE: ExecutionStatus.COMPLETED,
    StepStatus.FAILED: ExecutionStatus.FAILED,
    StepStatus.CHECKPOINT: ExecutionStatus.PAUSED,
    StepStatus.SKIPPED: ExecutionStatus.CANCELLED,
}

# Status mappings: ExecutionStatus → StepStatus
EXECUTION_TO_STEP_STATUS = {
    ExecutionStatus.PENDING: StepStatus.PENDING,
    ExecutionStatus.RUNNING: StepStatus.RUNNING,
    ExecutionStatus.COMPLETED: StepStatus.DONE,
    ExecutionStatus.FAILED: StepStatus.FAILED,
    ExecutionStatus.PAUSED: StepStatus.CHECKPOINT,
    ExecutionStatus.CANCELLED: StepStatus.SKIPPED,
    ExecutionStatus.TIMEOUT: StepStatus.FAILED,
    ExecutionStatus.WAITING: StepStatus.PENDING,
    ExecutionStatus.EXPANDED: StepStatus.DONE,
}


def step_status_to_execution_status(step_status: StepStatus) -> ExecutionStatus:
    """Convert TaskStep status to ExecutionNode status."""
    return STEP_TO_EXECUTION_STATUS.get(step_status, ExecutionStatus.PENDING)


def execution_status_to_step_status(exec_status: ExecutionStatus) -> StepStatus:
    """Convert ExecutionNode status to TaskStep status."""
    return EXECUTION_TO_STEP_STATUS.get(exec_status, StepStatus.PENDING)


def task_step_to_node(
    step: TaskStep,
    parent_id: str = "root"
) -> ExecutionNode:
    """
    Convert a TaskStep to an ExecutionNode for execution tree storage.

    Args:
        step: The TaskStep to convert
        parent_id: Parent node ID in the execution tree (defaults to "root")

    Returns:
        ExecutionNode with step data mapped to node fields
    """
    # Convert dependencies from List[str] to Set[str]
    dependencies = set(step.dependencies) if step.dependencies else set()

    # If no explicit dependencies and not root, depend on root
    if not dependencies and parent_id:
        dependencies = {parent_id}

    # Build metadata for reconstruction
    metadata = {
        "agent_type": step.agent_type,
        "domain": step.domain,
        "description": step.description,
        "inputs": step.inputs,
        "parallel_group": step.parallel_group,
        "failure_policy": step.failure_policy.value if step.failure_policy else None,
        "checkpoint_required": step.checkpoint_required,
        "checkpoint_config": step.checkpoint_config.to_dict() if step.checkpoint_config else None,
        "fallback_config": step.fallback_config.to_dict() if step.fallback_config else None,
        "is_critical": step.is_critical,
        "max_retries": step.max_retries,
    }

    # Map step status to execution status
    exec_status = step_status_to_execution_status(step.status)

    node = ExecutionNode(
        id=step.id,
        name=step.name,
        node_type=NodeType.AGENT,
        status=exec_status,
        priority=ExecutionPriority.NORMAL,
        parent_id=parent_id,
        dependencies=dependencies,
        task_data=step.inputs,
        result_data=step.outputs or {},
        error_data={"error": step.error_message} if step.error_message else None,
        retry_count=step.retry_count,
        max_retries=step.max_retries,
        metadata=metadata,
    )

    # Set timing if available
    if step.started_at:
        node.metrics.start_time = step.started_at
    if step.completed_at:
        node.metrics.end_time = step.completed_at
        node.metrics.calculate_duration()

    return node


def node_to_task_step(node: ExecutionNode) -> TaskStep:
    """
    Convert an ExecutionNode back to a TaskStep.

    Args:
        node: The ExecutionNode to convert

    Returns:
        TaskStep with node data mapped to step fields
    """
    metadata = node.metadata or {}

    # Extract checkpoint config if present
    checkpoint_config = None
    if metadata.get("checkpoint_config"):
        checkpoint_config = CheckpointConfig.from_dict(metadata["checkpoint_config"])

    # Extract fallback config if present
    fallback_config = None
    if metadata.get("fallback_config"):
        fallback_config = FallbackConfig.from_dict(metadata["fallback_config"])

    # Convert dependencies from Set[str] to List[str]
    dependencies = list(node.dependencies) if node.dependencies else []
    # Remove "root" from dependencies as it's implicit
    dependencies = [d for d in dependencies if d != "root"]

    # Map execution status to step status
    step_status = execution_status_to_step_status(node.status)

    # Extract error message from error_data
    error_message = None
    if node.error_data:
        error_message = node.error_data.get("error") or node.error_data.get("message")

    # Parse failure_policy if present
    from src.domain.tasks.models import ParallelFailurePolicy
    failure_policy = ParallelFailurePolicy.ALL_OR_NOTHING
    if metadata.get("failure_policy"):
        try:
            failure_policy = ParallelFailurePolicy(metadata["failure_policy"])
        except ValueError:
            pass

    step = TaskStep(
        id=node.id,
        name=node.name,
        description=metadata.get("description", ""),
        agent_type=metadata.get("agent_type", node.node_type.value),
        domain=metadata.get("domain"),
        inputs=node.task_data or metadata.get("inputs", {}),
        outputs=node.result_data or {},
        dependencies=dependencies,
        status=step_status,
        parallel_group=metadata.get("parallel_group"),
        failure_policy=failure_policy,
        checkpoint_required=metadata.get("checkpoint_required", False),
        checkpoint_config=checkpoint_config,
        fallback_config=fallback_config,
        is_critical=metadata.get("is_critical", True),
        retry_count=node.retry_count,
        max_retries=node.max_retries,
        error_message=error_message,
        started_at=node.metrics.start_time,
        completed_at=node.metrics.end_time,
        execution_time_ms=int(node.metrics.duration.total_seconds() * 1000) if node.metrics.duration else None,
    )

    return step
