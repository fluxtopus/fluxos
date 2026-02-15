"""Tool for approving or rejecting task checkpoints.

Allows users to approve/reject pending checkpoints directly from Arrow chat.
"""

from __future__ import annotations
from typing import Any, Dict
import structlog

from .base import BaseTool, ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class ApproveCheckpointTool(BaseTool):
    """Approve or reject a pending task checkpoint.

    This tool allows users to approve or reject checkpoints that are
    waiting for human approval before a task can continue.
    """

    @property
    def name(self) -> str:
        return "approve_checkpoint"

    @property
    def description(self) -> str:
        return """Approve or reject a pending task checkpoint.

Use this when:
- A task is waiting for approval to proceed
- The user wants to approve a checkpoint they've reviewed
- The user wants to reject a checkpoint with feedback

After approval, the task will automatically continue execution."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "The plan/task ID containing the checkpoint",
                    },
                    "step_id": {
                        "type": "string",
                        "description": "The step ID with the pending checkpoint",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["approve", "reject"],
                        "description": "Whether to approve or reject the checkpoint",
                    },
                    "feedback": {
                        "type": "string",
                        "description": "Optional feedback (required for rejection, optional for approval)",
                    },
                    "resume_execution": {
                        "type": "boolean",
                        "description": "Whether to resume execution after approval (default: true)",
                        "default": True,
                    },
                },
                "required": ["plan_id", "step_id", "action"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        """Approve or reject a checkpoint.

        Args:
            arguments: {
                "plan_id": str,  # Plan/task ID
                "step_id": str,  # Step ID with checkpoint
                "action": str,  # "approve" or "reject"
                "feedback": str,  # Optional feedback
                "resume_execution": bool,  # Resume after approval (default: true)
            }
            context: {
                "user_id": str,  # User making the request
                "delegation_service": DelegationService,  # Injected service
            }

        Returns:
            ToolResult with checkpoint decision result
        """
        plan_id = arguments.get("plan_id")
        step_id = arguments.get("step_id")
        action = arguments.get("action")
        feedback = arguments.get("feedback")
        resume_execution = arguments.get("resume_execution", True)

        # Validate required arguments
        if not plan_id:
            return ToolResult(
                success=False,
                error="Missing required argument: plan_id",
            )

        if not step_id:
            return ToolResult(
                success=False,
                error="Missing required argument: step_id",
            )

        if not action:
            return ToolResult(
                success=False,
                error="Missing required argument: action",
            )

        if action not in ["approve", "reject"]:
            return ToolResult(
                success=False,
                error="Action must be 'approve' or 'reject'",
            )

        if action == "reject" and not feedback:
            return ToolResult(
                success=False,
                error="Feedback is required when rejecting a checkpoint",
            )

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
            logger.info(
                "Processing checkpoint decision",
                plan_id=plan_id,
                step_id=step_id,
                action=action,
                user_id=user_id,
            )

            if action == "approve":
                checkpoint = await delegation_service.approve_checkpoint(
                    plan_id=plan_id,
                    step_id=step_id,
                    user_id=user_id,
                    feedback=feedback,
                )

                result_data = {
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "decision": "approved",
                    "checkpoint_name": checkpoint.checkpoint_name,
                }

                # Resume execution if requested
                if resume_execution:
                    try:
                        execution_result = await delegation_service.execute_plan(
                            plan_id=plan_id,
                            user_id=user_id,
                            run_to_completion=False,
                        )

                        result_data["resumed"] = True
                        result_data["execution_status"] = execution_result.status
                        result_data["steps_completed"] = execution_result.steps_completed

                        if execution_result.checkpoint:
                            result_data["next_checkpoint"] = {
                                "step_id": execution_result.checkpoint.get("step_id"),
                                "name": execution_result.checkpoint.get("checkpoint_name"),
                            }

                    except Exception as exec_error:
                        logger.warning(
                            "Approved but failed to resume execution",
                            plan_id=plan_id,
                            error=str(exec_error),
                        )
                        result_data["resumed"] = False
                        result_data["resume_error"] = str(exec_error)

                return ToolResult(
                    success=True,
                    data=result_data,
                    message=f"Checkpoint approved. Task continuing execution.",
                )

            else:  # action == "reject"
                checkpoint = await delegation_service.reject_checkpoint(
                    plan_id=plan_id,
                    step_id=step_id,
                    user_id=user_id,
                    reason=feedback,
                )

                return ToolResult(
                    success=True,
                    data={
                        "plan_id": plan_id,
                        "step_id": step_id,
                        "decision": "rejected",
                        "checkpoint_name": checkpoint.checkpoint_name,
                        "reason": feedback,
                    },
                    message=f"Checkpoint rejected. Task execution stopped.",
                )

        except ValueError as e:
            return ToolResult(
                success=False,
                error=f"Checkpoint not found: {str(e)}",
            )
        except Exception as e:
            logger.error(
                "Failed to process checkpoint",
                error=str(e),
                plan_id=plan_id,
                step_id=step_id,
            )
            return ToolResult(
                success=False,
                error=f"Failed to process checkpoint: {str(e)}",
            )
