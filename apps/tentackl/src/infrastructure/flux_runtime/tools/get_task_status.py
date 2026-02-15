"""Tool for checking the status of tasks.

Allows users to query the status of active and completed tasks
from Arrow chat.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import structlog

from .base import BaseTool, ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class GetTaskStatusTool(BaseTool):
    """Get the current status of tasks.

    This tool allows users to check on the progress of their
    background tasks and see pending checkpoints.
    """

    @property
    def name(self) -> str:
        return "get_task_status"

    @property
    def description(self) -> str:
        return """Get the current status of one or more tasks.

Use this to:
- Check the progress of a specific task
- List all active tasks
- See pending checkpoints that need approval
- View recently completed tasks

If no task_id is provided, shows all active tasks and pending checkpoints."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Specific plan/task ID to check. If omitted, returns all active tasks.",
                    },
                    "include_completed": {
                        "type": "boolean",
                        "description": "Include recently completed tasks (default: false)",
                        "default": False,
                    },
                    "include_checkpoints": {
                        "type": "boolean",
                        "description": "Include pending checkpoint details (default: true)",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        """Get task status.

        Args:
            arguments: {
                "plan_id": str,  # Optional specific task ID
                "include_completed": bool,  # Include completed tasks
                "include_checkpoints": bool,  # Include checkpoint details
                "limit": int,  # Max tasks to return
            }
            context: {
                "user_id": str,  # User making the request
                "delegation_service": DelegationService,  # Injected service
            }

        Returns:
            ToolResult with task status information
        """
        plan_id = arguments.get("plan_id")
        include_completed = arguments.get("include_completed", False)
        include_checkpoints = arguments.get("include_checkpoints", True)
        limit = arguments.get("limit", 10)

        # Get required context
        user_id = context.get("user_id")
        delegation_service = context.get("delegation_service")

        if not user_id:
            return ToolResult(
                success=False,
                error="User context not available",
            )

        if not delegation_service:
            return ToolResult(
                success=False,
                error="Delegation service not available",
            )

        try:
            # If specific plan requested
            if plan_id:
                plan = await delegation_service.get_plan(plan_id)

                if not plan:
                    return ToolResult(
                        success=False,
                        error=f"Task not found: {plan_id}",
                    )

                if plan.user_id != user_id:
                    return ToolResult(
                        success=False,
                        error="Access denied to this task",
                    )

                result_data = self._format_plan(plan)

                # Add checkpoint info if pending
                if include_checkpoints:
                    checkpoints = await delegation_service.get_pending_checkpoints(user_id)
                    plan_checkpoints = [c for c in checkpoints if c.plan_id == plan_id]
                    if plan_checkpoints:
                        result_data["pending_checkpoints"] = [
                            self._format_checkpoint(c) for c in plan_checkpoints
                        ]

                return ToolResult(
                    success=True,
                    data=result_data,
                    message=f"Task '{plan.goal[:50]}...' is {plan.status.value}",
                )

            # List all tasks
            from src.domain.tasks.models import TaskStatus

            # Get active tasks
            active_plans = await delegation_service.get_user_plans(
                user_id=user_id,
                status=None,  # All statuses initially
                limit=limit,
            )

            # Filter to active statuses
            active_statuses = {
                TaskStatus.PLANNING,
                TaskStatus.READY,
                TaskStatus.EXECUTING,
                TaskStatus.CHECKPOINT,
            }

            active_tasks = [p for p in active_plans if p.status in active_statuses]
            completed_tasks = []

            if include_completed:
                completed_tasks = [
                    p for p in active_plans
                    if p.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
                ][:5]  # Limit completed to 5

            # Get pending checkpoints
            pending_checkpoints = []
            if include_checkpoints:
                checkpoints = await delegation_service.get_pending_checkpoints(user_id)
                pending_checkpoints = [self._format_checkpoint(c) for c in checkpoints]

            result_data = {
                "active_tasks": [self._format_plan(p) for p in active_tasks],
                "active_count": len(active_tasks),
            }

            if include_completed:
                result_data["completed_tasks"] = [
                    self._format_plan(p) for p in completed_tasks
                ]
                result_data["completed_count"] = len(completed_tasks)

            if include_checkpoints:
                result_data["pending_checkpoints"] = pending_checkpoints
                result_data["checkpoint_count"] = len(pending_checkpoints)

            # Build summary message
            summary_parts = []
            if active_tasks:
                summary_parts.append(f"{len(active_tasks)} active task(s)")
            if pending_checkpoints:
                summary_parts.append(f"{len(pending_checkpoints)} checkpoint(s) pending approval")
            if completed_tasks:
                summary_parts.append(f"{len(completed_tasks)} recently completed")

            if not summary_parts:
                message = "No active tasks"
            else:
                message = ", ".join(summary_parts)

            return ToolResult(
                success=True,
                data=result_data,
                message=message,
            )

        except Exception as e:
            logger.error(
                "Failed to get task status",
                error=str(e),
                plan_id=plan_id,
            )
            return ToolResult(
                success=False,
                error=f"Failed to get task status: {str(e)}",
            )

    def _format_plan(self, plan) -> Dict[str, Any]:
        """Format a plan for display."""
        completed_steps = sum(
            1 for s in plan.steps if s.status.value == "completed"
        )
        failed_steps = sum(
            1 for s in plan.steps if s.status.value == "failed"
        )

        return {
            "plan_id": plan.id,
            "goal": plan.goal,
            "status": plan.status.value,
            "progress": plan.get_progress_percentage(),
            "steps_total": len(plan.steps),
            "steps_completed": completed_steps,
            "steps_failed": failed_steps,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        }

    def _format_checkpoint(self, checkpoint) -> Dict[str, Any]:
        """Format a checkpoint for display."""
        return {
            "plan_id": checkpoint.plan_id,
            "step_id": checkpoint.step_id,
            "name": checkpoint.checkpoint_name,
            "description": checkpoint.description,
            "preview": checkpoint.preview_data,
            "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
            "expires_at": checkpoint.expires_at.isoformat() if checkpoint.expires_at else None,
        }
