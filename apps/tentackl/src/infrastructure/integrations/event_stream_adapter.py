"""Infrastructure adapter for integration SSE streaming and event publish."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict

import redis.asyncio as redis_async
import structlog

from src.core.config import settings
from src.domain.integrations import IntegrationEventStreamPort

logger = structlog.get_logger(__name__)


class RedisIntegrationEventStreamAdapter(IntegrationEventStreamPort):
    """Stream and publish integration events via Redis pub/sub."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or settings.REDIS_URL

    @staticmethod
    def _channel(integration_id: str) -> str:
        return f"tentackl:integration:events:{integration_id}"

    def stream_events(self, integration_id: str) -> AsyncGenerator[str, None]:
        channel = self._channel(integration_id)

        async def event_generator() -> AsyncGenerator[str, None]:
            redis_client = await redis_async.from_url(
                self._redis_url,
                decode_responses=True,
            )
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(channel)

            try:
                yield f"event: connected\ndata: {json.dumps({'integration_id': integration_id})}\n\n"

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
                                data = json.loads(message["data"])
                            except json.JSONDecodeError:
                                logger.warning(
                                    "Invalid JSON in integration event",
                                    integration_id=integration_id,
                                    raw_data=message["data"],
                                )
                                continue

                            event_type = data.get("type", "integration.event")
                            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        pass

                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = current_time
            except asyncio.CancelledError:
                logger.debug("Integration SSE stream cancelled", integration_id=integration_id)
                raise
            except Exception as exc:
                logger.error(
                    "Error in integration SSE stream",
                    integration_id=integration_id,
                    error=str(exc),
                )
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
                await redis_client.aclose()

        return event_generator()

    async def publish_event(self, integration_id: str, event: Dict[str, Any]) -> None:
        redis_client = await redis_async.from_url(
            self._redis_url,
            decode_responses=True,
        )
        try:
            await redis_client.publish(
                self._channel(integration_id),
                json.dumps(event),
            )
        finally:
            await redis_client.aclose()
