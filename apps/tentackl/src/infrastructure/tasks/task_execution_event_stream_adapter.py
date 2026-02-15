"""Infrastructure adapter for task execution event streaming."""

from __future__ import annotations

from typing import Optional, Dict, Any
import asyncio
import json
import structlog

from src.domain.tasks.ports import (
    TaskExecutionEventStreamPort,
    TaskExecutionEventSubscription,
)
from src.infrastructure.tasks.event_publisher import (
    TaskEventPublisher,
    get_task_event_publisher,
)

logger = structlog.get_logger(__name__)


class TaskExecutionEventSubscriptionAdapter(TaskExecutionEventSubscription):
    """Subscription wrapper around Redis pub/sub for task events."""

    def __init__(self, redis_client, pubsub, channel: str) -> None:
        self._redis_client = redis_client
        self._pubsub = pubsub
        self._channel = channel
        self._closed = False

    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        if self._closed:
            return None

        try:
            message = await asyncio.wait_for(
                self._pubsub.get_message(ignore_subscribe_messages=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None

        if not message:
            return None

        data = message.get("data")
        if not data:
            return None

        try:
            return json.loads(data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse task event payload", raw_data=data)
            return None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        try:
            await self._pubsub.unsubscribe(self._channel)
            await self._pubsub.aclose()
        except Exception:
            pass
        try:
            await self._redis_client.aclose()
        except Exception:
            pass


class TaskExecutionEventStreamAdapter(TaskExecutionEventStreamPort):
    """Adapter exposing TaskEventPublisher event stream methods."""

    def __init__(self, publisher: Optional[TaskEventPublisher] = None) -> None:
        self._publisher = publisher or get_task_event_publisher()

    async def get_recent_events(
        self,
        task_id: str,
        count: int = 100,
    ) -> list[Dict[str, Any]]:
        return await self._publisher.get_recent_events(task_id, count=count)

    async def subscribe(self, task_id: str) -> TaskExecutionEventSubscription:
        import redis.asyncio as redis_async

        channel = await self._publisher.get_channel(task_id)
        redis_client = await redis_async.from_url(self._publisher.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        return TaskExecutionEventSubscriptionAdapter(redis_client, pubsub, channel)
