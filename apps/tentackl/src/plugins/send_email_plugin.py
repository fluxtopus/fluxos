"""
Send Email Plugin - Send emails via Mimic service.

This plugin sends emails deterministically through Mimic's /api/v1/send
endpoint, routing through Mailpit in development and real providers
(Postmark/Resend) in production.
"""

import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional

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


async def send_email_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Send an email via Mimic service.

    Inputs:
        to: list[string] (required) - Recipient email addresses
        subject: string (required) - Email subject line
        body: string (required) - Email body content
        body_type: string (optional) - "text" or "html" (default: "text")
        cc: list[string] (optional) - CC recipients
        bcc: list[string] (optional) - BCC recipients
        reply_to: string (optional) - Reply-to address

    Returns:
        {
            sent: bool - Whether email was sent successfully,
            message_id: string - Delivery ID from Mimic,
            recipients: int - Number of recipients,
            tracking_id: string - Tracking identifier
        }
    """
    to = inputs.get("to")
    subject = inputs.get("subject")
    body = inputs.get("body", "")
    body_type = inputs.get("body_type", "text")
    cc = inputs.get("cc", [])
    bcc = inputs.get("bcc", [])
    reply_to = inputs.get("reply_to")

    if not to:
        return {"error": "Recipient list (to) is required", "sent": False}

    if not subject:
        return {"error": "Subject is required", "sent": False}

    if not body:
        return {"error": "Body is required", "sent": False}

    # Normalize to list
    if isinstance(to, str):
        to = [to]

    try:
        use_cases = _get_notification_use_cases()

        all_delivery_ids: List[str] = []
        failed_recipients: List[str] = []

        metadata = {
            "subject": subject,
            "body_type": body_type,
            "source": "send_email_plugin",
        }
        if cc:
            metadata["cc"] = cc
        if bcc:
            metadata["bcc"] = bcc
        if reply_to:
            metadata["reply_to"] = reply_to

        # Send to each recipient via Mimic
        all_recipients = list(to) + list(cc) + list(bcc)

        for recipient in all_recipients:
            result = await use_cases.send(
                recipient=recipient,
                title=subject,
                message=body if body_type == "html" else f"<pre>{body}</pre>",
                provider="email",
                metadata=metadata,
            )

            if result.get("success"):
                delivery_id = result.get("delivery_id", "")
                if delivery_id:
                    all_delivery_ids.append(delivery_id)
            else:
                failed_recipients.append(recipient)
                logger.warning(
                    "send_email_recipient_failed",
                    recipient=recipient,
                    error=result.get("error"),
                )

        total_recipients = len(all_recipients)
        sent_count = total_recipients - len(failed_recipients)

        if failed_recipients and sent_count == 0:
            return {
                "error": f"Failed to send to all {total_recipients} recipients",
                "sent": False,
                "recipients": 0,
            }

        return {
            "sent": True,
            "message_id": all_delivery_ids[0] if all_delivery_ids else "",
            "recipients": sent_count,
            "tracking_id": all_delivery_ids[0] if all_delivery_ids else "",
            "sent_at": datetime.utcnow().isoformat(),
            "failed_recipients": failed_recipients if failed_recipients else None,
        }

    except Exception as e:
        logger.error("send_email_plugin_failed", error=str(e), recipients=to)
        return {"error": f"Failed to send email: {str(e)}", "sent": False}


PLUGIN_DEFINITION = {
    "name": "send_email",
    "description": "Send emails via Mimic (Mailpit in dev, Postmark/Resend in prod)",
    "handler": send_email_handler,
    "inputs_schema": {
        "to": {"type": "array", "required": True, "description": "Recipient email addresses"},
        "subject": {"type": "string", "required": True, "description": "Email subject line"},
        "body": {"type": "string", "required": True, "description": "Email body content"},
        "body_type": {"type": "string", "required": False, "default": "text", "enum": ["text", "html"]},
        "cc": {"type": "array", "required": False, "description": "CC recipients"},
        "bcc": {"type": "array", "required": False, "description": "BCC recipients"},
        "reply_to": {"type": "string", "required": False, "description": "Reply-to address"},
    },
    "outputs_schema": {
        "sent": {"type": "boolean", "description": "Whether email was sent"},
        "message_id": {"type": "string", "description": "Delivery ID from Mimic"},
        "recipients": {"type": "integer", "description": "Number of recipients sent to"},
        "tracking_id": {"type": "string", "description": "Tracking identifier"},
    },
    "category": "communication",
    "requires_checkpoint": True,  # Emails require user approval
}
