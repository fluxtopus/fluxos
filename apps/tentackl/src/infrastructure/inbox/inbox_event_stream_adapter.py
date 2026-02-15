"""Infrastructure adapter for inbox SSE event streaming."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

import redis.asyncio as redis_async
import structlog

from src.core.config import settings
from src.domain.inbox.ports import InboxEventStreamPort
from src.infrastructure.tasks.event_publisher import get_task_event_publisher

logger = structlog.get_logger(__name__)


class InboxEventStreamAdapter(InboxEventStreamPort):
    """Stream inbox events from Redis pub/sub as SSE payloads."""

    def stream_events(self, user_id: str) -> AsyncGenerator[str, None]:
        publisher = get_task_event_publisher()
        channel = publisher.get_inbox_channel(user_id)

        async def event_generator() -> AsyncGenerator[str, None]:
            redis_client = await redis_async.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel)

            logger.info("Started inbox SSE stream", user_id=user_id, channel=channel)

            try:
                heartbeat_interval = 30  # seconds
                last_heartbeat = asyncio.get_event_loop().time()

                while True:
                    try:
                        message = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True),
                            timeout=1.0,
                        )

                        if message and message["type"] == "message":
                            try:
                                event = json.loads(message["data"])
                                yield f"data: {json.dumps(event)}\n\n"
                            except json.JSONDecodeError:
                                logger.warning(
                                    "Failed to parse inbox event",
                                    user_id=user_id,
                                    raw_data=message["data"],
                                )
                    except asyncio.TimeoutError:
                        pass

                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield ":ping\n\n"
                        last_heartbeat = current_time
            except asyncio.CancelledError:
                logger.info("Inbox SSE stream cancelled", user_id=user_id)
                raise
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                await redis_client.aclose()
                logger.info("Stopped inbox SSE stream", user_id=user_id)

        return event_generator()
