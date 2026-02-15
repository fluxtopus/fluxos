# REVIEW: This tool embeds integration business logic (auto-resolve, pre-checks,
# REVIEW: payload mapping) directly in the tool handler. That logic likely belongs
# REVIEW: in an integration service layer so it can be reused outside inbox and
# REVIEW: tested independently.
"""Inbox tool: Manage and use integrations (Discord, Slack, GitHub, etc.).

Allows Flux to discover the user's connected integrations and execute
outbound actions (send messages, create issues, etc.) without the user
needing to know integration IDs.
"""

from typing import Any, Dict, Optional

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.integrations import IntegrationUseCases
from src.infrastructure.integrations import MimicIntegrationAdapter

logger = structlog.get_logger(__name__)

_integration_use_cases: Optional[IntegrationUseCases] = None


def _get_integration_use_cases() -> IntegrationUseCases:
    global _integration_use_cases
    if _integration_use_cases is None:
        _integration_use_cases = IntegrationUseCases(
            integration_ops=MimicIntegrationAdapter()
        )
    return _integration_use_cases


class IntegrationsTool(BaseTool):
    """List integrations and execute outbound actions."""

    @property
    def name(self) -> str:
        return "integrations"

    @property
    def description(self) -> str:
        return (
            "Manage external service integrations (Discord, Slack, GitHub, Stripe, "
            "custom webhooks). List connected integrations, send messages, create "
            "issues, or execute any outbound action."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "send", "status"],
                        "description": (
                            "Action to perform. "
                            "'list': show connected integrations. "
                            "'send': execute an outbound action (message, embed, issue). "
                            "'status': get details of a specific integration."
                        ),
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["discord", "slack", "github", "stripe", "custom_webhook"],
                        "description": (
                            "Filter by provider when listing, or target provider when "
                            "sending. If sending without integration_id, the tool will "
                            "auto-resolve the first matching integration for this provider."
                        ),
                    },
                    "integration_id": {
                        "type": "string",
                        "description": (
                            "Specific integration ID. Required for 'status'. "
                            "Optional for 'send' (auto-resolved from provider if omitted)."
                        ),
                    },
                    "action_type": {
                        "type": "string",
                        "description": (
                            "Outbound action type for 'send'. Examples: "
                            "send_message, send_embed, send_blocks, create_issue, post."
                        ),
                        "default": "send_message",
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content for send_message.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for embeds or issues.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description for embeds.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Custom payload for webhook actions.",
                    },
                },
                "required": ["action"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        action = arguments["action"]
        user_token = context.get("user_token")

        if not user_token:
            return ToolResult(
                success=False,
                error="Authentication token not available for integration access.",
            )

        try:
            if action == "list":
                return await self._list_integrations(arguments, user_token)
            elif action == "send":
                return await self._send_action(arguments, context, user_token)
            elif action == "status":
                return await self._get_status(arguments, user_token)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error("Integration tool failed", error=str(e), action=action)
            return ToolResult(success=False, error=f"Integration operation failed: {str(e)}")

    async def _list_integrations(
        self, arguments: Dict[str, Any], token: str,
    ) -> ToolResult:
        use_cases = _get_integration_use_cases()
        provider = arguments.get("provider")

        result = await use_cases.list_integrations(
            token=token,
            provider=provider,
        )

        integrations = [
            {
                "id": item.id,
                "name": item.name,
                "provider": item.provider,
                "direction": item.direction,
                "status": item.status,
            }
            for item in result.items
        ]

        if not integrations:
            provider_msg = f" for {provider}" if provider else ""
            return ToolResult(
                success=True,
                data={"integrations": [], "total": 0},
                message=f"No integrations found{provider_msg}.",
            )

        return ToolResult(
            success=True,
            data={"integrations": integrations, "total": result.total},
            message=f"Found {result.total} integration(s).",
        )

    async def _send_action(
        self, arguments: Dict[str, Any], context: Dict[str, Any], token: str,
    ) -> ToolResult:
        use_cases = _get_integration_use_cases()
        integration_id = arguments.get("integration_id")
        provider = arguments.get("provider")
        action_type = arguments.get("action_type", "send_message")

        # Auto-resolve integration_id from provider if not given
        if not integration_id:
            if not provider:
                return ToolResult(
                    success=False,
                    error="Either integration_id or provider is required for 'send'.",
                )

            result = await use_cases.list_integrations(
                token=token, provider=provider,
            )

            # Find first active outbound-capable integration
            candidates = [
                item for item in result.items
                if item.status == "active"
                and item.direction in ("outbound", "bidirectional")
            ]

            if not candidates:
                return ToolResult(
                    success=False,
                    error=f"No active outbound {provider} integration found. "
                    f"The user needs to set up a {provider} integration first.",
                )

            integration_id = candidates[0].id
            logger.info(
                "Auto-resolved integration",
                provider=provider,
                integration_id=integration_id,
                name=candidates[0].name,
            )

        # Pre-check: verify integration has outbound config and credentials
        try:
            detail = await use_cases.get_integration(
                integration_id=integration_id, token=token,
            )
            if not detail.outbound_config:
                return ToolResult(
                    success=False,
                    error=(
                        f"The {detail.provider} integration '{detail.name}' exists but "
                        f"outbound actions are not configured yet. The user needs to "
                        f"configure outbound settings (webhook URL or bot token) at "
                        f"Settings → Integrations → {detail.name} → Outbound Configuration."
                    ),
                )
            if not detail.credentials:
                return ToolResult(
                    success=False,
                    error=(
                        f"The {detail.provider} integration '{detail.name}' has outbound "
                        f"config but no credentials (webhook URL or API key). The user "
                        f"needs to add credentials at Settings → Integrations → "
                        f"{detail.name} → Credentials."
                    ),
                )
        except Exception as e:
            logger.warning(
                "Failed to pre-check integration",
                integration_id=integration_id,
                error=str(e),
            )
            # Continue anyway — the execute call will give its own error

        # Build action params
        params = {}
        for key in ("content", "title", "description", "color", "fields", "blocks", "payload"):
            if arguments.get(key) is not None:
                params[key] = arguments[key]

        result = await use_cases.execute_action(
            integration_id=integration_id,
            action_type=action_type,
            params=params,
            token=token,
        )

        return ToolResult(
            success=result.success,
            data={
                "integration_id": integration_id,
                "action_type": action_type,
                "result": result.model_dump() if hasattr(result, "model_dump") else {},
            },
            message=(
                f"Action '{action_type}' executed successfully."
                if result.success
                else f"Action '{action_type}' failed."
            ),
        )

    async def _get_status(
        self, arguments: Dict[str, Any], token: str,
    ) -> ToolResult:
        use_cases = _get_integration_use_cases()
        integration_id = arguments.get("integration_id")
        if not integration_id:
            return ToolResult(success=False, error="integration_id is required for 'status'.")

        detail = await use_cases.get_integration(
            integration_id=integration_id,
            token=token,
        )

        return ToolResult(
            success=True,
            data={
                "id": detail.id,
                "name": detail.name,
                "provider": detail.provider,
                "direction": detail.direction,
                "status": detail.status,
                "has_credentials": len(detail.credentials) > 0,
                "has_inbound": detail.inbound_config is not None,
                "has_outbound": detail.outbound_config is not None,
            },
            message=f"Integration '{detail.name}' ({detail.provider}) — {detail.status}.",
        )
