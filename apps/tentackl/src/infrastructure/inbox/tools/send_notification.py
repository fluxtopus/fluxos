"""Inbox tool: Send notifications via Mimic."""

from typing import Any, Dict, Optional
import structlog

from src.application.notifications import NotificationUseCases
from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.infrastructure.notifications import MimicNotificationAdapter

logger = structlog.get_logger(__name__)
_notification_use_cases: Optional[NotificationUseCases] = None


def _get_notification_use_cases() -> NotificationUseCases:
    global _notification_use_cases
    if _notification_use_cases is None:
        _notification_use_cases = NotificationUseCases(
            notification_ops=MimicNotificationAdapter()
        )
    return _notification_use_cases


class SendNotificationTool(BaseTool):
    """Send email or other notifications via the Mimic service."""

    @property
    def name(self) -> str:
        return "send_notification"

    @property
    def description(self) -> str:
        return "Send a notification (email) via the Mimic notification service."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "enum": ["email"],
                        "description": "Notification channel.",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body (plain text or HTML).",
                    },
                },
                "required": ["channel", "recipient", "subject", "body"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        channel = arguments["channel"]
        recipient = arguments["recipient"]
        subject = arguments["subject"]
        body = arguments["body"]

        if channel != "email":
            return ToolResult(
                success=False,
                error=f"Unsupported channel: {channel}. Only 'email' is supported.",
            )

        try:
            use_cases = _get_notification_use_cases()
            data = await use_cases.send(
                recipient=recipient,
                title=subject,
                message=body,
                provider=channel,
                metadata={
                    "source": "inbox_chat",
                    "user_id": context.get("user_id"),
                    "conversation_id": context.get("conversation_id"),
                    "task_id": context.get("task_id"),
                },
            )

            if not data.get("success"):
                error_message = data.get("error", "Unknown notification failure")
                return ToolResult(
                    success=False,
                    error=f"Failed to send {channel} to {recipient}: {error_message}",
                )

            return ToolResult(
                success=True,
                data={
                    "notification_id": data.get("delivery_id"),
                    "status": data.get("status", "sent"),
                },
                message=f"Email sent to {recipient}: {subject}",
            )

        except Exception as e:
            logger.error(
                "Failed to send notification",
                error=str(e),
                channel=channel,
                recipient=recipient,
            )
            return ToolResult(
                success=False,
                error=f"Failed to send {channel} to {recipient}: {str(e)}",
            )
