"""
Task Output Retrieval Plugin for cross-task data flow.

Enables one task to retrieve step outputs from another completed (or in-progress)
task. This bridges the gap where data produced by Task A (stored in steps[].outputs)
needs to be consumed by Task B without going through workspace.

Architecture:
    - task_output_retrieval_handler: Retrieve step outputs from a target task

Key features:
    - Organization-isolated access control
    - Retrieve all steps or a specific step by ID/name
    - Large output truncation (50KB per string value)
"""

from typing import Any, Dict, Optional

import structlog

from src.application.tasks import TaskUseCases
from src.application.tasks.providers import (
    get_task_use_cases as provider_get_task_use_cases,
)

logger = structlog.get_logger(__name__)

# Maximum size for any single string value in outputs (50KB)
MAX_OUTPUT_STRING_SIZE = 50 * 1024

_task_use_cases: Optional[TaskUseCases] = None


def set_database(db: Any) -> None:
    """Backwards-compatible no-op; runtime now comes from shared providers."""
    _ = db
    global _task_use_cases
    _task_use_cases = None


async def _get_task_use_cases() -> TaskUseCases:
    """Get shared TaskUseCases from application providers."""
    global _task_use_cases
    if _task_use_cases is None:
        _task_use_cases = await provider_get_task_use_cases()
    return _task_use_cases


def _truncate_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Truncate any string value over MAX_OUTPUT_STRING_SIZE.

    Prevents base64-encoded blobs from blowing up context windows.
    """
    if not outputs or not isinstance(outputs, dict):
        return outputs or {}

    truncated = {}
    for key, value in outputs.items():
        if isinstance(value, str) and len(value) > MAX_OUTPUT_STRING_SIZE:
            truncated[key] = value[:MAX_OUTPUT_STRING_SIZE] + "\n... [truncated]"
        else:
            truncated[key] = value
    return truncated


async def task_output_retrieval_handler(
    inputs: Dict[str, Any], context=None
) -> Dict[str, Any]:
    """
    Retrieve step outputs from a previously executed task.

    Identity fields (org_id) are taken from the ExecutionContext
    (built from the plan in DB), not from inputs.

    Inputs:
        task_id: string (required) - UUID of the task to retrieve outputs from
        step_id: string (optional) - Specific step ID to retrieve
        step_name: string (optional) - Specific step name (alternative to step_id)

    Context (from ExecutionContext):
        organization_id: Organization this execution belongs to

    Returns:
        All steps format:
        {
            task_id: string,
            task_status: string,
            task_goal: string,
            steps: [{step_id, step_name, agent_type, status, outputs}, ...],
            step_count: int
        }

        Specific step format:
        {
            task_id: string,
            step_id: string,
            step_name: string,
            agent_type: string,
            status: string,
            outputs: {...}
        }

        Error format:
        {
            status: 'error',
            error: string
        }
    """
    try:
        # Get identity from context (trusted source), not inputs
        if context is None:
            return {
                "status": "error",
                "error": "ExecutionContext is required for task output retrieval",
            }

        org_id = context.organization_id

        # Validate required field
        task_id = inputs.get("task_id")
        if not task_id:
            return {"status": "error", "error": "Missing required field: task_id"}

        # Optional filters
        step_id = inputs.get("step_id")
        step_name = inputs.get("step_name")

        # Load target task from PostgreSQL
        task_use_cases = await _get_task_use_cases()
        task = await task_use_cases.get_task(task_id)

        if not task:
            return {
                "status": "error",
                "error": f"Task not found: {task_id}",
            }

        # Access control: verify same organization
        if task.organization_id != org_id:
            logger.warning(
                "task_output_retrieval_access_denied",
                requesting_org=org_id,
                target_org=task.organization_id,
                target_task_id=task_id,
            )
            return {
                "status": "error",
                "error": "Access denied: task belongs to a different organization",
            }

        # If specific step requested, find and return it
        if step_id or step_name:
            target_step = None
            for s in task.steps:
                if step_id and s.id == step_id:
                    target_step = s
                    break
                if step_name and s.name == step_name:
                    target_step = s
                    break

            if not target_step:
                identifier = step_id or step_name
                return {
                    "status": "error",
                    "error": f"Step not found: {identifier}",
                }

            logger.debug(
                "task_output_retrieval_step",
                task_id=task_id,
                step_id=target_step.id,
                step_name=target_step.name,
            )

            return {
                "task_id": task_id,
                "step_id": target_step.id,
                "step_name": target_step.name or target_step.id,
                "agent_type": target_step.agent_type,
                "status": target_step.status.value if hasattr(target_step.status, "value") else str(target_step.status),
                "outputs": _truncate_outputs(target_step.outputs),
            }

        # Return all steps with outputs
        steps_data = []
        for s in task.steps:
            steps_data.append({
                "step_id": s.id,
                "step_name": s.name or s.id,
                "agent_type": s.agent_type,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "outputs": _truncate_outputs(s.outputs),
            })

        logger.debug(
            "task_output_retrieval_all_steps",
            task_id=task_id,
            step_count=len(steps_data),
        )

        return {
            "task_id": task_id,
            "task_status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "task_goal": task.goal,
            "steps": steps_data,
            "step_count": len(steps_data),
        }

    except Exception as e:
        logger.error(
            "task_output_retrieval_handler_failed",
            error=str(e),
            task_id=inputs.get("task_id"),
            org_id=context.organization_id if context else None,
        )
        return {
            "status": "error",
            "error": f"Failed to retrieve task outputs: {str(e)}",
        }


# Export plugin handlers
PLUGIN_HANDLERS = {
    "task_output_retrieval": task_output_retrieval_handler,
}
