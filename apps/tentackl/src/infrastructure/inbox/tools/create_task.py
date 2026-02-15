# REVIEW: The tool still builds metadata and linking logic inline. Consider
# REVIEW: promoting this into a dedicated application use case to keep inbox
# REVIEW: tools thin and to centralize task creation + conversation linkage.
"""Inbox tool: Create a background task within the current conversation."""

from typing import Any, Dict, Optional

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.tasks import TaskUseCases
from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases

logger = structlog.get_logger(__name__)

_task_use_cases: Optional[TaskUseCases] = None


async def _get_task_use_cases() -> TaskUseCases:
    global _task_use_cases
    if _task_use_cases is None:
        _task_use_cases = await provider_get_task_use_cases()
    return _task_use_cases


class InboxCreateTaskTool(BaseTool):
    """Create a background task that reports progress into this conversation."""

    @property
    def name(self) -> str:
        return "create_task"

    @property
    def description(self) -> str:
        return (
            "Start a background task. The task plans and executes autonomously, "
            "reporting progress directly into this conversation thread."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Clear description of what the task should accomplish.",
                    },
                    "constraints": {
                        "type": "object",
                        "description": "Optional constraints (budget, time, etc.).",
                    },
                },
                "required": ["goal"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        goal = arguments["goal"]
        constraints = arguments.get("constraints") or {}
        user_id = context.get("user_id")
        organization_id = context.get("organization_id", "")
        conversation_id = context.get("conversation_id")

        # Forward file references from chat context so the planner knows about attached files
        file_references = context.get("file_references")
        if file_references:
            constraints["file_references"] = file_references

        if not user_id or not conversation_id:
            return ToolResult(
                success=False,
                error="Missing user_id or conversation_id in context",
            )

        try:
            task_use_cases = await _get_task_use_cases()
            task = await task_use_cases.create_task(
                user_id=user_id,
                organization_id=organization_id,
                goal=goal,
                constraints=constraints or None,
                metadata={
                    "source": "inbox_chat",
                    "conversation_id": conversation_id,
                },
                auto_start=True,
            )

            await task_use_cases.link_conversation(
                task_id=task.id,
                conversation_id=conversation_id,
            )

            logger.info(
                "Inbox task created",
                task_id=task.id,
                conversation_id=conversation_id,
                goal=goal[:100],
            )

            return ToolResult(
                success=True,
                data={
                    "task_id": task.id,
                    "status": "planning",
                    "goal": goal,
                },
                message=f"Task created and planning started: {goal}",
            )

        except Exception as e:
            logger.error("Failed to create inbox task", error=str(e))
            return ToolResult(
                success=False,
                error=f"Failed to create task: {str(e)}",
            )
