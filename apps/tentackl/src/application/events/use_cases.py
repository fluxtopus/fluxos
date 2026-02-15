"""Application orchestration for event bus APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.events import EventBusOperationsPort, OrchestratorConversationPort


@dataclass
class EventBusUseCases:
    """Use-case facade for internal event bus routes."""

    event_bus_ops: EventBusOperationsPort
    conversation_ops: Optional[OrchestratorConversationPort] = None

    async def publish_event(
        self,
        source: str,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[bool, str, datetime]:
        return await self.event_bus_ops.publish_internal_event(
            source=source,
            event_type=event_type,
            data=data,
            metadata=metadata,
            workflow_id=workflow_id,
            agent_id=agent_id,
        )

    async def send_orchestrator_message(
        self,
        workflow_id: str,
        message: str,
        sender_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        return await self.event_bus_ops.publish_user_message(
            workflow_id=workflow_id,
            message=message,
            sender_id=sender_id,
            metadata=metadata,
        )

    async def create_subscription(
        self,
        subscriber_id: str,
        event_pattern: str,
        event_filter: Optional[Dict[str, Any]] = None,
        transform: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self.event_bus_ops.create_subscription(
            subscriber_id=subscriber_id,
            event_pattern=event_pattern,
            event_filter=event_filter,
            transform=transform,
        )

    async def delete_subscription(self, subscription_id: str) -> bool:
        return await self.event_bus_ops.delete_subscription(subscription_id)

    async def list_subscriptions(
        self,
        subscriber_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await self.event_bus_ops.list_subscriptions(subscriber_id=subscriber_id)

    async def replay_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self.event_bus_ops.replay_events(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            workflow_id=workflow_id,
            limit=limit,
        )

    async def get_orchestrator_conversation_history(self, workflow_id: str) -> Dict[str, Any]:
        if self.conversation_ops is None:
            return {"conversation_id": None, "messages": [], "total_messages": 0}
        return await self.conversation_ops.get_conversation_history(workflow_id)

    def health_snapshot(self) -> Dict[str, Any]:
        return {
            "event_bus": self.event_bus_ops.is_running(),
        }

