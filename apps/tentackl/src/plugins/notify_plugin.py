"""
Notification Plugin - Send notifications via Mimic service.

This plugin handles email and push notifications through the Mimic
notification service.
"""

import structlog
from datetime import datetime
from typing import Any, Dict, Optional

from src.application.notifications import NotificationUseCases
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


async def notify_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Send a notification via Mimic service.

    Inputs:
        to: string (required) - Recipient email or push token
        subject: string (optional) - Email subject line
        body: string (required) - Message body content
        channel: string (optional) - Channel: email, push (default: email)

    Returns:
        {
            notification_id: string - Delivery ID from Mimic,
            status: string - "sent" or "failed",
            channel: string - Channel used,
            recipient: string - Recipient address
        }
    """
    to = inputs.get("to")
    subject = inputs.get("subject", "Notification from Tentackl")
    body = inputs.get("body", "")
    channel = inputs.get("channel", "email")

    if not to:
        return {"error": "Recipient (to) is required", "status": "failed"}

    if not body:
        return {"error": "Message body is required", "status": "failed"}

    try:
        use_cases = _get_notification_use_cases()
        result = await use_cases.send(
            recipient=to,
            title=subject,
            message=body,
            provider=channel,
            metadata={"source": "plugin_executor"},
        )

        if result.get("status") == "sent":
            return {
                "notification_id": result.get("delivery_id"),
                "status": "sent",
                "channel": channel,
                "recipient": to,
                "sent_at": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "error": result.get("message", "Failed to send notification"),
                "status": "failed",
            }

    except Exception as e:
        logger.error("notify_plugin_failed", error=str(e), recipient=to)
        return {"error": f"Failed to send notification: {str(e)}", "status": "failed"}


PLUGIN_DEFINITION = {
    "name": "notify",
    "description": "Send notifications via email or push",
    "handler": notify_handler,
    "inputs_schema": {
        "to": {"type": "string", "required": True, "description": "Recipient email or push token"},
        "subject": {"type": "string", "required": False, "default": "Notification", "description": "Email subject"},
        "body": {"type": "string", "required": True, "description": "Message body content"},
        "channel": {"type": "string", "required": False, "default": "email", "enum": ["email", "push"]},
    },
    "outputs_schema": {
        "notification_id": {"type": "string", "description": "Delivery ID"},
        "status": {"type": "string", "description": "sent or failed"},
        "channel": {"type": "string", "description": "Channel used"},
        "recipient": {"type": "string", "description": "Recipient address"},
    },
    "category": "communication",
    "requires_checkpoint": True,  # Notifications require user approval
}
