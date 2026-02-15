# REVIEW: This client mixes HTTP transport with HTML templating and branding
# REVIEW: logic. Consider separating template rendering from transport and
# REVIEW: centralizing HTTP client configuration (timeouts, retries, auth).
"""Mimic notification client for Tentackl.

Provides notification capabilities for task events:
- Checkpoint approvals needed
- Task completions
- Task failures
- Task progress updates
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
import os
import httpx
import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


class NotificationType(str, Enum):
    """Types of notifications Tentackl can send."""
    CHECKPOINT = "checkpoint"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"


class TentacklMimicClient:
    """Mimic client configured for Tentackl task notifications.

    Sends notifications to users about task events via Mimic service.
    Uses Mimic's multi-channel support (email, slack, webhook, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize Tentackl Mimic client.

        Args:
            api_key: Mimic API key (from env MIMIC_API_KEY if not provided)
            base_url: Mimic API URL (from env MIMIC_URL or default localhost)
        """
        self.api_key = api_key or os.getenv("MIMIC_API_KEY")
        self.base_url = (base_url or os.getenv("MIMIC_URL", "http://mimic:8000")).rstrip("/")

        self.headers = {}
        if self.api_key:
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

        logger.info(
            "TentacklMimicClient initialized",
            has_api_key=bool(self.api_key),
            base_url=self.base_url,
        )

    @property
    def is_configured(self) -> bool:
        """Check if client is properly configured."""
        return bool(self.api_key)

    async def send_notification(
        self,
        recipient: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        plan_id: Optional[str] = None,
        step_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        provider: str = "email",
        action_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a task notification.

        Args:
            recipient: Email or recipient identifier
            notification_type: Type of notification
            title: Notification title
            message: Notification body
            plan_id: Associated plan/task ID
            step_id: Associated step ID (for checkpoints)
            metadata: Additional metadata
            provider: Delivery provider (email, slack, webhook)
            action_url: URL for action button (e.g., approve checkpoint)
            organization_id: Organization ID for brand settings (defaults to platform)

        Returns:
            Delivery result with delivery_id and status
        """
        if not self.is_configured:
            logger.warning("Mimic client not configured, skipping notification")
            return {"success": False, "error": "Not configured"}

        # Load organization-specific brand settings
        brand_settings = await self._get_brand_settings(organization_id)

        # Build HTML content based on notification type
        content = self._build_notification_content(
            notification_type=notification_type,
            title=title,
            message=message,
            plan_id=plan_id,
            step_id=step_id,
            action_url=action_url,
            brand_settings=brand_settings,
        )

        # Build metadata
        full_metadata = {
            "subject": title,
            "notification_type": notification_type.value,
            "source": "tentackl",
            "plan_id": plan_id,
            "step_id": step_id,
            "from_name": brand_settings.brand_name,
            "html_body": content,
            **(metadata or {}),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/send",
                    headers=self.headers,
                    json={
                        "recipient": recipient,
                        "content": content,
                        "provider": provider,
                        "metadata": full_metadata,
                    },
                )
                response.raise_for_status()
                result = response.json()

                logger.info(
                    "Notification sent",
                    notification_type=notification_type.value,
                    recipient=recipient,
                    delivery_id=result.get("delivery_id"),
                )

                return {
                    "success": True,
                    "delivery_id": result.get("delivery_id"),
                    "status": result.get("status"),
                }

        except httpx.HTTPError as e:
            logger.error(
                "Failed to send notification",
                error=str(e),
                notification_type=notification_type.value,
                recipient=recipient,
            )
            return {
                "success": False,
                "error": str(e),
            }
        except Exception as e:
            logger.error(
                "Unexpected error sending notification",
                error=str(e),
                notification_type=notification_type.value,
            )
            return {
                "success": False,
                "error": str(e),
            }

    async def _get_brand_settings(self, organization_id: Optional[str] = None):
        """Load brand settings for an organization.

        Args:
            organization_id: Organization ID (defaults to platform)

        Returns:
            BrandSettings instance
        """
        try:
            from src.infrastructure.notifications.brand_settings import (
                BrandSettings,
                get_brand_settings,
            )

            org_id = organization_id or "aios-platform"
            return await get_brand_settings(org_id)
        except Exception as e:
            logger.warning(
                "Failed to load brand settings, using defaults",
                organization_id=organization_id,
                error=str(e),
            )
            # Return default settings
            from src.infrastructure.notifications.brand_settings import BrandSettings
            return BrandSettings.platform_defaults()

    def _build_notification_content(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        plan_id: Optional[str] = None,
        step_id: Optional[str] = None,
        action_url: Optional[str] = None,
        brand_settings=None,
    ) -> str:
        """Build HTML notification content.

        Args:
            notification_type: Type of notification
            title: Notification title
            message: Notification body
            plan_id: Associated plan ID
            step_id: Associated step ID
            action_url: Action button URL
            brand_settings: Organization brand settings

        Returns:
            HTML content string
        """
        # Emoji and color based on type
        type_config = {
            NotificationType.CHECKPOINT: {
                "emoji": "⏸️",
                "color": "#f59e0b",  # amber
                "action_text": "Review Checkpoint",
            },
            NotificationType.TASK_COMPLETED: {
                "emoji": "✅",
                "color": "#10b981",  # green
                "action_text": "View Results",
            },
            NotificationType.TASK_FAILED: {
                "emoji": "❌",
                "color": "#ef4444",  # red
                "action_text": "View Details",
            },
            NotificationType.TASK_STARTED: {
                "emoji": "🚀",
                "color": "#3b82f6",  # blue
                "action_text": "Track Progress",
            },
            NotificationType.TASK_PROGRESS: {
                "emoji": "📊",
                "color": "#8b5cf6",  # purple
                "action_text": "View Progress",
            },
        }

        config = type_config.get(
            notification_type,
            {"emoji": "📢", "color": "#6b7280", "action_text": "View"},
        )

        # Build action button if URL provided
        action_html = ""
        if action_url:
            action_html = f"""
                <div style="margin-top: 20px;">
                    <a href="{action_url}"
                       style="display: inline-block; padding: 12px 24px;
                              background-color: {config['color']};
                              color: white; text-decoration: none;
                              border-radius: 6px; font-weight: bold;">
                        {config['action_text']}
                    </a>
                </div>
            """

        # Build reference info
        ref_html = ""
        if plan_id:
            ref_html += f'<p style="color: #6b7280; font-size: 12px; margin: 4px 0;">Plan ID: <code>{plan_id}</code></p>'
        if step_id:
            ref_html += f'<p style="color: #6b7280; font-size: 12px; margin: 4px 0;">Step ID: <code>{step_id}</code></p>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                     background-color: #f3f4f6; padding: 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white;
                        border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background-color: {config['color']}; padding: 20px; text-align: center;">
                    <span style="font-size: 48px;">{config['emoji']}</span>
                    <h1 style="color: white; margin: 10px 0 0 0; font-size: 24px;">{title}</h1>
                </div>

                <!-- Content -->
                <div style="padding: 24px;">
                    <div style="color: #374151; font-size: 16px; line-height: 1.6;">
                        {message}
                    </div>

                    {action_html}

                    <!-- Reference Info -->
                    <div style="margin-top: 20px; padding-top: 20px;
                                border-top: 1px solid #e5e7eb;">
                        {ref_html}
                    </div>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9fafb; padding: 16px; text-align: center;
                            border-top: 1px solid #e5e7eb;">
                    <p style="color: #6b7280; font-size: 12px; margin: 0;">
                        {brand_settings.footer_text if brand_settings else settings.BRAND_FOOTER_TEXT}
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    async def notify_checkpoint(
        self,
        recipient: str,
        plan_id: str,
        step_id: str,
        checkpoint_name: str,
        description: str,
        preview_data: Optional[Dict[str, Any]] = None,
        approval_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send checkpoint approval notification.

        Args:
            recipient: Email/recipient
            plan_id: Plan ID
            step_id: Step ID with checkpoint
            checkpoint_name: Name of the checkpoint
            description: Checkpoint description
            preview_data: Preview data to show
            approval_url: URL to approve the checkpoint
            organization_id: Organization ID for brand settings

        Returns:
            Delivery result
        """
        # Format preview data if provided
        preview_html = ""
        if preview_data:
            preview_items = []
            for k, v in list(preview_data.items())[:5]:
                if isinstance(v, str) and len(v) > 100:
                    v = v[:100] + "..."
                elif isinstance(v, (list, dict)):
                    v = f"({type(v).__name__})"
                preview_items.append(f"<li><strong>{k}:</strong> {v}</li>")
            if preview_items:
                preview_html = f"<ul style='margin: 10px 0; padding-left: 20px;'>{''.join(preview_items)}</ul>"

        message = f"""
            <p>A task is waiting for your approval to continue.</p>
            <h3 style="margin: 16px 0 8px 0;">{checkpoint_name}</h3>
            <p style="color: #6b7280;">{description}</p>
            {preview_html}
            <p style="margin-top: 16px;">
                <strong>Please review and approve or reject this checkpoint to continue the task.</strong>
            </p>
        """

        return await self.send_notification(
            recipient=recipient,
            notification_type=NotificationType.CHECKPOINT,
            title=f"Checkpoint: {checkpoint_name}",
            message=message,
            plan_id=plan_id,
            step_id=step_id,
            action_url=approval_url,
            organization_id=organization_id,
        )

    async def notify_task_completed(
        self,
        recipient: str,
        plan_id: str,
        goal: str,
        steps_completed: int,
        outputs: Optional[Dict[str, Any]] = None,
        results_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send task completion notification.

        Args:
            recipient: Email/recipient
            plan_id: Plan ID
            goal: Original task goal
            steps_completed: Number of steps completed
            outputs: Task outputs/results
            results_url: URL to view results
            organization_id: Organization ID for brand settings

        Returns:
            Delivery result
        """
        # Format outputs if provided
        outputs_html = ""
        if outputs:
            output_items = []
            for k, v in list(outputs.items())[:5]:
                if isinstance(v, str) and len(v) > 100:
                    v = v[:100] + "..."
                output_items.append(f"<li><strong>{k}:</strong> {v}</li>")
            if output_items:
                outputs_html = f"""
                    <h4 style="margin: 16px 0 8px 0;">Results:</h4>
                    <ul style='margin: 10px 0; padding-left: 20px;'>{''.join(output_items)}</ul>
                """

        message = f"""
            <p>Your task has been completed successfully!</p>
            <h3 style="margin: 16px 0 8px 0;">Goal:</h3>
            <p style="color: #374151; background-color: #f3f4f6; padding: 12px;
                      border-radius: 6px;">{goal}</p>
            <p><strong>{steps_completed}</strong> steps completed.</p>
            {outputs_html}
        """

        return await self.send_notification(
            recipient=recipient,
            notification_type=NotificationType.TASK_COMPLETED,
            title="Task Completed",
            message=message,
            plan_id=plan_id,
            action_url=results_url,
            organization_id=organization_id,
        )

    async def notify_task_failed(
        self,
        recipient: str,
        plan_id: str,
        goal: str,
        error_message: str,
        failed_step: Optional[str] = None,
        retry_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send task failure notification.

        Args:
            recipient: Email/recipient
            plan_id: Plan ID
            goal: Original task goal
            error_message: Error that caused failure
            failed_step: Name of failed step
            retry_url: URL to retry
            organization_id: Organization ID for brand settings

        Returns:
            Delivery result
        """
        failed_step_html = ""
        if failed_step:
            failed_step_html = f'<p><strong>Failed at:</strong> {failed_step}</p>'

        message = f"""
            <p>Unfortunately, your task encountered an error and could not be completed.</p>
            <h3 style="margin: 16px 0 8px 0;">Goal:</h3>
            <p style="color: #374151; background-color: #f3f4f6; padding: 12px;
                      border-radius: 6px;">{goal}</p>
            {failed_step_html}
            <h4 style="margin: 16px 0 8px 0; color: #ef4444;">Error:</h4>
            <p style="color: #ef4444; background-color: #fef2f2; padding: 12px;
                      border-radius: 6px;">{error_message}</p>
            <p style="margin-top: 16px;">
                You can retry the task or modify the goal and try again.
            </p>
        """

        return await self.send_notification(
            recipient=recipient,
            notification_type=NotificationType.TASK_FAILED,
            title="Task Failed",
            message=message,
            plan_id=plan_id,
            action_url=retry_url,
            organization_id=organization_id,
        )


# Singleton instance for convenience
_client: Optional[TentacklMimicClient] = None


def get_mimic_client() -> TentacklMimicClient:
    """Get or create the singleton Mimic client.

    Returns:
        TentacklMimicClient instance
    """
    global _client
    if _client is None:
        _client = TentacklMimicClient()
    return _client
