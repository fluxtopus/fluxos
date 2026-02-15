"""Tool for starting autonomous background tasks.

Bridges Arrow chat to the delegation system, allowing users to
start tasks with natural language goals.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
import structlog

from .base import BaseTool, ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class StartTaskTool(BaseTool):
    """Start an autonomous task that runs in the background.

    This tool creates a delegation plan from a natural language goal
    and optionally starts executing it immediately.
    """

    @property
    def name(self) -> str:
        return "start_task"

    @property
    def description(self) -> str:
        return """Start an autonomous task that runs in the background.

Use this when the user wants to delegate a task to be handled autonomously.
The task will be planned and executed with checkpoints for human approval when needed.

Examples:
- "Monitor HN for AI agent posts and summarize top 3"
- "Research competitor pricing and create a comparison report"
- "Scrape the latest product reviews from Amazon"

Returns the task/plan ID for tracking progress."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Natural language description of what to accomplish",
                        "minLength": 10,
                    },
                    "constraints": {
                        "type": "object",
                        "description": "Optional constraints for the task (e.g., time limits, resources to use)",
                        "additionalProperties": True,
                    },
                    "start_immediately": {
                        "type": "boolean",
                        "description": "Whether to start executing immediately (default: true)",
                        "default": True,
                    },
                    "notify_on_complete": {
                        "type": "boolean",
                        "description": "Whether to notify when the task completes (default: true)",
                        "default": True,
                    },
                },
                "required": ["goal"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        """Start an autonomous task.

        Args:
            arguments: {
                "goal": str,  # Natural language goal
                "constraints": dict,  # Optional constraints
                "start_immediately": bool,  # Start executing (default: true)
                "notify_on_complete": bool,  # Notify on completion (default: true)
            }
            context: {
                "user_id": str,  # User making the request
                "organization_id": str,  # Organization ID
                "delegation_service": DelegationService,  # Injected service
            }

        Returns:
            ToolResult with task/plan ID and status
        """
        goal = arguments.get("goal")
        constraints = arguments.get("constraints", {})
        start_immediately = arguments.get("start_immediately", True)
        notify_on_complete = arguments.get("notify_on_complete", True)

        if not goal:
            return ToolResult(
                success=False,
                error="Missing required argument: goal",
            )

        if len(goal) < 10:
            return ToolResult(
                success=False,
                error="Goal must be at least 10 characters",
            )

        # Get required context
        user_id = context.get("user_id")
        organization_id = context.get("organization_id")
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
            logger.info(
                "Starting autonomous task",
                user_id=user_id,
                goal=goal[:50],
                start_immediately=start_immediately,
            )

            # Add notification preference to metadata
            metadata = {
                "notify_on_complete": notify_on_complete,
                "source": "arrow_chat",
            }

            # Create the delegation plan
            plan = await delegation_service.create_plan(
                user_id=user_id,
                organization_id=organization_id,
                goal=goal,
                constraints=constraints,
                metadata=metadata,
            )

            result_data = {
                "plan_id": plan.id,
                "goal": plan.goal,
                "status": plan.status.value,
                "steps_count": len(plan.steps),
                "steps_preview": [
                    {"name": s.name, "agent_type": s.agent_type}
                    for s in plan.steps[:5]  # Preview first 5 steps
                ],
            }

            # Start execution immediately if requested
            if start_immediately:
                try:
                    execution_result = await delegation_service.execute_plan(
                        plan_id=plan.id,
                        user_id=user_id,
                        run_to_completion=False,  # Stop at checkpoints
                    )

                    result_data["execution_status"] = execution_result.status
                    result_data["steps_completed"] = execution_result.steps_completed

                    if execution_result.checkpoint:
                        result_data["pending_checkpoint"] = {
                            "step_id": execution_result.checkpoint.get("step_id"),
                            "name": execution_result.checkpoint.get("checkpoint_name"),
                            "description": execution_result.checkpoint.get("description"),
                        }

                    logger.info(
                        "Task execution started",
                        plan_id=plan.id,
                        status=execution_result.status,
                        steps_completed=execution_result.steps_completed,
                    )

                except Exception as exec_error:
                    logger.warning(
                        "Task created but execution failed to start",
                        plan_id=plan.id,
                        error=str(exec_error),
                    )
                    result_data["execution_error"] = str(exec_error)
                    result_data["note"] = "Task was created but execution failed to start"

            return ToolResult(
                success=True,
                data=result_data,
                message=f"Task '{goal[:50]}...' started with {len(plan.steps)} steps. Plan ID: {plan.id}",
            )

        except Exception as e:
            logger.error(
                "Failed to start task",
                error=str(e),
                goal=goal[:50],
            )
            return ToolResult(
                success=False,
                error=f"Failed to start task: {str(e)}",
            )
