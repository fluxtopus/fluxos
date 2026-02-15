# REVIEW: NotificationResult uses a mutable default (`metadata = {}`), which
# REVIEW: can be shared across instances. Prefer `default_factory=dict`.
"""Notification provider interface"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from pydantic import BaseModel


class NotificationResult(BaseModel):
    """Result of a notification send operation"""
    success: bool
    provider: str
    message_id: str | None = None
    error: str | None = None
    metadata: Dict[str, Any] = {}


class NotificationProviderInterface(ABC):
    """Interface for notification providers (Email, SMS, Slack, etc.)"""
    
    @abstractmethod
    async def send(self, recipient: str, content: str, **kwargs) -> NotificationResult:
        """Send a notification to a recipient"""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate provider-specific configuration"""
        pass
