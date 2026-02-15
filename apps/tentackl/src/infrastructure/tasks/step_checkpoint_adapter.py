"""Infrastructure adapter for step checkpoint operations."""

from __future__ import annotations

from typing import Any
import structlog

from src.domain.tasks.ports import StepCheckpointPort

logger = structlog.get_logger(__name__)


class StepCheckpointAdapter(StepCheckpointPort):
    """Wraps PostgresCheckpointStore and CheckpointManager.

    Provides two operations needed during step execution:
    - checking if a checkpoint was already approved (re-execution after approval)
    - creating a new checkpoint for user approval
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    async def is_already_approved(self, task_id: str, step_id: str) -> bool:
        from src.infrastructure.tasks.stores.postgres_checkpoint_store import PostgresCheckpointStore

        pg_checkpoint_store = PostgresCheckpointStore(self._db)
        existing = await pg_checkpoint_store.get_checkpoint(task_id, step_id)
        return bool(existing and existing.decision.value == "approved")

    async def create_checkpoint(
        self,
        task_id: str,
        step: Any,
        user_id: str,
    ) -> None:
        from src.infrastructure.tasks.stores.postgres_checkpoint_store import PostgresCheckpointStore
        from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
        from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
        from src.infrastructure.tasks.runtime_components import CheckpointManager

        pg_checkpoint_store = PostgresCheckpointStore(self._db)
        redis_store = RedisTaskStore()
        await redis_store._connect()
        pg_task_store = PostgresTaskStore(self._db)

        try:
            checkpoint_manager = CheckpointManager(
                pg_checkpoint_store=pg_checkpoint_store,
                plan_store=redis_store,
                pg_task_store=pg_task_store,
            )
            await checkpoint_manager.create_checkpoint(
                plan_id=task_id,
                step=step,
                user_id=user_id,
            )
        finally:
            await redis_store._disconnect()
