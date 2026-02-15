"""Eventing domain ports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


class EventBusOperationsPort(Protocol):
    """Port for event bus publish/subscribe/replay operations."""

    async def publish_internal_event(
        self,
        source: str,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[bool, str, datetime]:
        """Publish an internal event and return success, event id, and timestamp."""

    async def publish_user_message(
        self,
        workflow_id: str,
        message: str,
        sender_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Publish an orchestrator user-message event."""

    async def create_subscription(
        self,
        subscriber_id: str,
        event_pattern: str,
        event_filter: Optional[Dict[str, Any]] = None,
        transform: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new event subscription and return subscription id."""

    async def delete_subscription(self, subscription_id: str) -> bool:
        """Delete an event subscription."""

    async def list_subscriptions(
        self,
        subscriber_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List subscriptions in normalized dictionary shape."""

    async def replay_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Replay historical events in normalized dictionary shape."""

    def is_running(self) -> bool:
        """Return whether the underlying event bus is healthy/running."""


class OrchestratorConversationPort(Protocol):
    """Port for retrieving orchestrator conversation history."""

    async def get_conversation_history(self, workflow_id: str) -> Dict[str, Any]:
        """Return orchestrator conversation payload for the given workflow."""

