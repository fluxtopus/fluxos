# REVIEW: This publisher largely duplicates TaskEventPublisher but with a
# REVIEW: separate schema and channel format. Consider consolidating event
# REVIEW: publishing behind a shared interface to avoid parallel evolution and
# REVIEW: schema drift. Also lacks versioning/error handling.
"""
TriggerEventPublisher: Publishes trigger lifecycle events to Redis pub/sub.

Events are published when triggers match/execute/complete/fail, enabling
real-time SSE streaming to the frontend.

Event types:
- trigger.matched - Event matched pattern
- trigger.executed - Task started
- trigger.completed - Task completed
- trigger.failed - Task failed
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import structlog
import redis.asyncio as redis

from src.core.config import settings

logger = structlog.get_logger(__name__)


class TriggerEventPublisher:
    """
    Publishes trigger lifecycle events to Redis pub/sub channels.

    Each trigger has its own channel: tentackl:trigger:events:{task_id}
    Clients can subscribe via SSE to receive real-time updates.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        channel_prefix: str = "tentackl:trigger:events",
    ):
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        self._channel_prefix = channel_prefix
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        if self._initialized:
            return

        self._redis_client = await redis.from_url(
            self._redis_url,
            decode_responses=True
        )
        self._initialized = True
        logger.info("TriggerEventPublisher initialized")

    async def _ensure_initialized(self) -> None:
        """Ensure the publisher is initialized."""
        if not self._initialized:
            await self.initialize()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._redis_client:
            await self._redis_client.aclose()
        self._initialized = False
        logger.info("TriggerEventPublisher cleaned up")

    def _get_channel(self, task_id: str) -> str:
        """Get the pub/sub channel for a trigger."""
        return f"{self._channel_prefix}:{task_id}"

    async def publish_matched(
        self,
        task_id: str,
        event_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Publish a trigger.matched event.

        Args:
            task_id: The trigger's task ID
            event_id: The incoming event ID that matched
            event_type: The event type that matched
            event_data: Optional event data preview

        Returns:
            True if published successfully
        """
        return await self._publish_event(
            task_id=task_id,
            event_type="trigger.matched",
            data={
                "event_id": event_id,
                "matched_event_type": event_type,
                "preview": event_data.get("preview") if event_data else None,
            },
        )

    async def publish_executed(
        self,
        task_id: str,
        event_id: str,
        execution_id: str,
    ) -> bool:
        """
        Publish a trigger.executed event.

        Args:
            task_id: The trigger's task ID
            event_id: The event that triggered execution
            execution_id: The task execution ID

        Returns:
            True if published successfully
        """
        return await self._publish_event(
            task_id=task_id,
            event_type="trigger.executed",
            data={
                "event_id": event_id,
                "execution_id": execution_id,
            },
        )

    async def publish_completed(
        self,
        task_id: str,
        event_id: str,
        execution_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Publish a trigger.completed event.

        Args:
            task_id: The trigger's task ID
            event_id: The event that triggered execution
            execution_id: The task execution ID
            result: Optional execution result preview

        Returns:
            True if published successfully
        """
        return await self._publish_event(
            task_id=task_id,
            event_type="trigger.completed",
            data={
                "event_id": event_id,
                "execution_id": execution_id,
                "result_preview": result.get("preview") if result else None,
            },
        )

    async def publish_failed(
        self,
        task_id: str,
        event_id: str,
        execution_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Publish a trigger.failed event.

        Args:
            task_id: The trigger's task ID
            event_id: The event that triggered execution
            execution_id: The task execution ID (if execution started)
            error: Error message

        Returns:
            True if published successfully
        """
        return await self._publish_event(
            task_id=task_id,
            event_type="trigger.failed",
            data={
                "event_id": event_id,
                "execution_id": execution_id,
                "error": error,
            },
        )

    async def _publish_event(
        self,
        task_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """
        Publish an event to the trigger's channel.

        Args:
            task_id: The trigger's task ID
            event_type: The event type
            data: Event data

        Returns:
            True if published successfully
        """
        await self._ensure_initialized()

        try:
            channel = self._get_channel(task_id)
            message = {
                "id": str(uuid.uuid4()),
                "type": event_type,
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": data,
            }

            await self._redis_client.publish(channel, json.dumps(message))

            logger.debug(
                "Published trigger event",
                task_id=task_id,
                event_type=event_type,
                channel=channel,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to publish trigger event",
                task_id=task_id,
                event_type=event_type,
                error=str(e),
            )
            return False


# Shared instance
_publisher: Optional[TriggerEventPublisher] = None


async def get_trigger_event_publisher() -> TriggerEventPublisher:
    """Get or create the shared TriggerEventPublisher instance."""
    global _publisher
    if _publisher is None:
        _publisher = TriggerEventPublisher()
        await _publisher.initialize()
    return _publisher
