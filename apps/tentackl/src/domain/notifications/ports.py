"""Domain ports for notification delivery."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class NotificationOperationsPort(Protocol):
    """Port for sending user-facing notifications."""

    async def send_notification(
        self,
        recipient: str,
        title: str,
        message: str,
        provider: str = "email",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

