"""Infrastructure adapter for planning cancellation."""

from __future__ import annotations

import structlog

from src.domain.tasks.ports import PlanCancellationPort


logger = structlog.get_logger(__name__)


class PlanCancellationAdapter(PlanCancellationPort):
    """Adapter that checks cancellation flags in Redis."""

    async def is_cancelled(self, task_id: str) -> bool:
        try:
            import redis.asyncio as redis_async
            from src.core.config import settings

            client = await redis_async.from_url(settings.REDIS_URL, decode_responses=True)
            result = await client.get(f"tentackl:task:cancel:{task_id}")
            await client.aclose()
            return result is not None
        except Exception as exc:
            logger.debug("Failed to check planning cancellation", error=str(exc))
            return False

    async def cancel(self, task_id: str) -> None:
        try:
            import redis.asyncio as redis_async
            from src.core.config import settings

            client = await redis_async.from_url(settings.REDIS_URL, decode_responses=True)
            await client.set(f"tentackl:task:cancel:{task_id}", "1", ex=3600)
            await client.aclose()
        except Exception as exc:
            logger.debug("Failed to set planning cancellation", task_id=task_id, error=str(exc))
