"""Infrastructure adapter for Mimic-backed notifications."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.notifications import NotificationOperationsPort
from src.infrastructure.notifications.mimic_client import (
    NotificationType,
    TentacklMimicClient,
)


class MimicNotificationAdapter(NotificationOperationsPort):
    """Adapter exposing TentacklMimicClient through notification port."""

    def __init__(self) -> None:
        self._client = TentacklMimicClient()

    async def send_notification(
        self,
        recipient: str,
        title: str,
        message: str,
        provider: str = "email",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._client.send_notification(
            recipient=recipient,
            notification_type=NotificationType.TASK_PROGRESS,
            title=title,
            message=message,
            provider=provider,
            metadata=metadata,
        )
