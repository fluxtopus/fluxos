# REVIEW: This tool still constructs task steps + trigger configs inline.
# REVIEW: Even with use cases, the orchestration logic lives in the tool.
# REVIEW: Consider moving this into an application-level use case (e.g.,
# REVIEW: CreateTriggeredTask) so schema, steps, and trigger registration live
# REVIEW: in one place and the tool remains thin.
"""Inbox tool: Create triggered tasks that execute automatically on events.

This tool allows Flux to create tasks that run automatically when specific
events occur, such as Discord slash commands, Slack messages, webhooks, etc.

Unlike create_task (one-time execution), triggered tasks persist and fire
whenever matching events arrive.

Example usage:
    User: "Send a joke whenever someone uses /ping on Discord"
    Flux:
        1. Calls integrations(action="list", provider="discord") to find integration
        2. Calls create_triggered_task(
            goal="Generate and send a programming joke",
            trigger_source="discord",
            integration_id="abc-123",
            event_filter={"command": "ping"},
            response_type="discord_followup"
        )
    Result: Task created with trigger auto-registered
"""

from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.tasks import TaskUseCases
from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases
from src.application.triggers import TriggerUseCases
from src.infrastructure.triggers.trigger_registry_adapter import TriggerRegistryAdapter
from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry

logger = structlog.get_logger(__name__)

_task_use_cases: Optional[TaskUseCases] = None
_trigger_registry: Optional[TaskTriggerRegistry] = None
_trigger_use_cases: Optional[TriggerUseCases] = None


async def _get_task_use_cases() -> TaskUseCases:
    global _task_use_cases
    if _task_use_cases is None:
        _task_use_cases = await provider_get_task_use_cases()
    return _task_use_cases


async def _get_trigger_use_cases() -> TriggerUseCases:
    global _trigger_registry, _trigger_use_cases
    if _trigger_use_cases is None:
        if _trigger_registry is None:
            _trigger_registry = TaskTriggerRegistry()
            await _trigger_registry.initialize()
        _trigger_use_cases = TriggerUseCases(
            registry=TriggerRegistryAdapter(_trigger_registry)
        )
    return _trigger_use_cases


class CreateTriggeredTaskTool(BaseTool):
    """Create a task that automatically executes when events occur."""

    @property
    def name(self) -> str:
        return "create_triggered_task"

    @property
    def description(self) -> str:
        return (
            "Create a task that runs automatically when specific events occur. "
            "Use for requests like 'whenever X happens, do Y' or 'when someone uses /command, respond with Z'."
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
                        "description": "What the task should do when triggered (e.g., 'Generate a programming joke').",
                    },
                    "trigger_source": {
                        "type": "string",
                        "enum": ["discord", "slack", "webhook", "github"],
                        "description": "Where events come from.",
                    },
                    "integration_id": {
                        "type": "string",
                        "description": "Specific integration ID (from integrations tool).",
                    },
                    "event_filter": {
                        "type": "object",
                        "description": "Optional: filter events (e.g., by command name or channel).",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Slash command name to match (e.g., 'ping', 'joke').",
                            },
                            "channel_id": {
                                "type": "string",
                                "description": "Channel ID to filter events from.",
                            },
                        },
                    },
                    "response_type": {
                        "type": "string",
                        "enum": ["discord_followup", "slack_message", "webhook", "none"],
                        "default": "none",
                        "description": (
                            "How to respond. Use 'discord_followup' for Discord interactions, "
                            "'slack_message' for Slack, 'webhook' for webhooks, or 'none' for no response."
                        ),
                    },
                },
                "required": ["goal", "trigger_source", "integration_id"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        goal = arguments["goal"]
        trigger_source = arguments["trigger_source"]
        integration_id = arguments["integration_id"]
        event_filter = arguments.get("event_filter", {})
        response_type = arguments.get("response_type", "none")

        user_id = context.get("user_id")
        organization_id = context.get("organization_id", "")
        conversation_id = context.get("conversation_id")

        if not user_id:
            return ToolResult(
                success=False,
                error="Missing user_id in context",
            )

        if not organization_id:
            return ToolResult(
                success=False,
                error="Missing organization_id in context. Triggers require organization scope.",
            )

        try:
            # Build task steps based on goal and response type
            steps = self._build_steps(goal, response_type, trigger_source)

            # Build trigger configuration
            trigger_config = self._build_trigger_config(
                integration_id=integration_id,
                event_filter=event_filter,
            )

            # Create task with trigger metadata
            task_use_cases = await _get_task_use_cases()
            task = await task_use_cases.create_task_with_steps(
                user_id=user_id,
                organization_id=organization_id,
                goal=goal,
                steps=steps,
                metadata={
                    "trigger": trigger_config,
                    "source": "inbox_triggered",
                    "integration_id": integration_id,
                    "trigger_source": trigger_source,
                    "response_type": response_type,
                },
            )

            # Register trigger in Redis so it appears in the triggers page
            # and actually fires when matching events arrive
            trigger_use_cases = await _get_trigger_use_cases()
            registered = await trigger_use_cases.register_trigger(
                task_id=task.id,
                org_id=organization_id,
                user_id=user_id,
                trigger_config=trigger_config,
            )

            if not registered:
                logger.warning(
                    "Task created but trigger registration failed",
                    task_id=task.id,
                    trigger_config=trigger_config,
                )

            # Link to conversation if available
            if conversation_id:
                await task_use_cases.link_conversation(
                    task_id=task.id,
                    conversation_id=conversation_id,
                )

            logger.info(
                "Triggered task created",
                task_id=task.id,
                trigger_source=trigger_source,
                integration_id=integration_id,
                event_pattern=trigger_config["event_pattern"],
                goal=goal[:100],
            )

            # Build user-friendly confirmation message
            trigger_desc = self._describe_trigger(trigger_source, event_filter)

            return ToolResult(
                success=True,
                data={
                    "task_id": task.id,
                    "trigger_source": trigger_source,
                    "integration_id": integration_id,
                    "event_pattern": trigger_config["event_pattern"],
                    "enabled": trigger_config["enabled"],
                },
                message=f"Triggered task created. It will run {trigger_desc}.",
            )

        except Exception as e:
            logger.error(
                "Failed to create triggered task",
                error=str(e),
                trigger_source=trigger_source,
            )
            return ToolResult(
                success=False,
                error=f"Failed to create triggered task: {str(e)}",
            )

    def _build_steps(
        self,
        goal: str,
        response_type: str,
        trigger_source: str,
    ) -> List[Dict[str, Any]]:
        """Build task steps based on goal and response type."""
        steps = [
            {
                "name": "generate_response",
                "agent_type": "compose",
                "description": f"Generate response: {goal}",
                "inputs": {
                    "topic": goal,
                    "research": "${trigger_event.data}",
                    "tone": "friendly",
                    "length": "short",
                },
            }
        ]

        # Add response step based on response_type
        if response_type == "discord_followup":
            steps.append({
                "name": "send_response",
                "agent_type": "discord_followup",
                "description": "Send response to Discord",
                "inputs": {
                    "application_id": "${trigger_event.metadata.application_id}",
                    "interaction_token": "${trigger_event.metadata.interaction_token}",
                    "content": "{{generate_response.outputs.content}}",
                },
                "dependencies": ["generate_response"],
            })
        elif response_type == "slack_message":
            steps.append({
                "name": "send_response",
                "agent_type": "slack_message",
                "description": "Send response to Slack",
                "inputs": {
                    "channel": "${trigger_event.metadata.channel_id}",
                    "thread_ts": "${trigger_event.metadata.thread_ts}",
                    "text": "{{generate_response.outputs.content}}",
                },
                "dependencies": ["generate_response"],
            })
        elif response_type == "webhook":
            steps.append({
                "name": "send_response",
                "agent_type": "http_fetch",
                "description": "Send response via webhook",
                "inputs": {
                    "url": "${trigger_event.metadata.response_url}",
                    "method": "POST",
                    "body": {
                        "response": "{{generate_response.outputs.content}}",
                    },
                },
                "dependencies": ["generate_response"],
            })

        return steps

    def _build_trigger_config(
        self,
        integration_id: str,
        event_filter: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build trigger configuration for the task metadata."""
        trigger_config: Dict[str, Any] = {
            "type": "event",
            "event_pattern": "external.integration.webhook",
            "source_filter": f"integration:{integration_id}",
            "enabled": True,
        }

        # Add command filter as JSONLogic condition if specified
        if event_filter.get("command"):
            trigger_config["condition"] = {
                "==": [{"var": "data.command"}, event_filter["command"]]
            }

        # Add channel filter if specified (AND with command if both present)
        if event_filter.get("channel_id"):
            channel_condition = {
                "==": [{"var": "data.channel_id"}, event_filter["channel_id"]]
            }

            if "condition" in trigger_config:
                # Combine with AND
                trigger_config["condition"] = {
                    "and": [trigger_config["condition"], channel_condition]
                }
            else:
                trigger_config["condition"] = channel_condition

        return trigger_config

    def _describe_trigger(
        self,
        trigger_source: str,
        event_filter: Dict[str, Any],
    ) -> str:
        """Generate a user-friendly description of when the trigger fires."""
        parts = []

        if event_filter.get("command"):
            parts.append(f"whenever someone uses /{event_filter['command']}")
        else:
            parts.append("whenever events arrive")

        parts.append(f"from {trigger_source}")

        if event_filter.get("channel_id"):
            parts.append(f"in channel {event_filter['channel_id']}")

        return " ".join(parts)
