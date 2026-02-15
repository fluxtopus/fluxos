"""Application use cases for notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.domain.notifications import NotificationOperationsPort


@dataclass
class NotificationUseCases:
    """Application-layer orchestration for notification sends."""

    notification_ops: NotificationOperationsPort

    async def send(
        self,
        recipient: str,
        title: str,
        message: str,
        provider: str = "email",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self.notification_ops.send_notification(
            recipient=recipient,
            title=title,
            message=message,
            provider=provider,
            metadata=metadata,
        )

