"""Redis event bus adapter for application use cases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.events import EventBusOperationsPort
from src.interfaces.event_bus import (
    Event,
    EventSourceType,
    EventSubscription,
)


class RedisEventBusAdapter(EventBusOperationsPort):
    """Adapter that normalizes `RedisEventBus` operations for use cases."""

    def __init__(self, bus: Any):
        self._bus = bus

    async def publish_internal_event(
        self,
        source: str,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[bool, str, datetime]:
        event = Event(
            source=source,
            source_type=EventSourceType.INTERNAL,
            event_type=event_type,
            data=data,
            metadata=metadata or {},
            workflow_id=workflow_id,
            agent_id=agent_id,
        )
        success = await self._bus.publish(event)
        return success, event.id, event.timestamp

    async def publish_user_message(
        self,
        workflow_id: str,
        message: str,
        sender_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        event = Event(
            source=sender_id,
            source_type=EventSourceType.USER_INPUT,
            event_type="orchestrator.user_message",
            data={
                "message": message,
                "sender_id": sender_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            metadata=metadata or {},
            workflow_id=workflow_id,
        )
        success = await self._bus.publish(event)
        return success, event.id

    async def create_subscription(
        self,
        subscriber_id: str,
        event_pattern: str,
        event_filter: Optional[Dict[str, Any]] = None,
        transform: Optional[Dict[str, Any]] = None,
    ) -> str:
        subscription = EventSubscription(
            subscriber_id=subscriber_id,
            event_pattern=event_pattern,
            filter=event_filter,
            transform=transform,
        )
        return await self._bus.subscribe(subscription)

    async def delete_subscription(self, subscription_id: str) -> bool:
        return await self._bus.unsubscribe(subscription_id)

    async def list_subscriptions(
        self,
        subscriber_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        subscriptions = await self._bus.list_subscriptions(subscriber_id)
        return [
            {
                "id": sub.id,
                "subscriber_id": sub.subscriber_id,
                "event_pattern": sub.event_pattern,
                "active": sub.active,
                "created_at": sub.created_at.isoformat(),
            }
            for sub in subscriptions
        ]

    async def replay_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        events = await self._bus.replay_events(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            workflow_id=workflow_id,
            limit=limit,
        )
        return [
            {
                "id": event.id,
                "source": event.source,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
                "workflow_id": event.workflow_id,
                "agent_id": event.agent_id,
            }
            for event in events
        ]

    def is_running(self) -> bool:
        return bool(getattr(self._bus, "_running", False))

