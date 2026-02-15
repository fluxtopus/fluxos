"""Infrastructure wrapper for legacy task runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import structlog

from src.domain.tasks.risk_detector import RiskDetectorService
from src.infrastructure.tasks.checkpoint_manager import CheckpointManager
from src.infrastructure.tasks.preference_learning import PreferenceLearningService
from src.infrastructure.tasks.state_machine import TaskStateMachine
from src.infrastructure.tasks.stores.postgres_checkpoint_store import PostgresCheckpointStore
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore

logger = structlog.get_logger(__name__)


@dataclass
class TaskRuntimeStores:
    """Resolved task stores used by runtime composition."""

    pg_store: Optional[PostgresTaskStore]
    redis_store: RedisTaskStore


async def ensure_runtime_stores(
    *,
    pg_store: Optional[PostgresTaskStore],
    redis_store: Optional[RedisTaskStore],
) -> TaskRuntimeStores:
    """Resolve and initialize default task stores when not provided."""

    resolved_redis = redis_store
    if not resolved_redis:
        resolved_redis = RedisTaskStore()
        await resolved_redis._connect()

    resolved_pg = pg_store
    if not resolved_pg:
        try:
            from src.interfaces.database import Database

            resolved_pg = PostgresTaskStore(Database())
            logger.info("PostgresTaskStore initialized as source of truth")
        except Exception as exc:
            logger.warning("Failed to initialize PostgresTaskStore", error=str(exc))
            resolved_pg = None

    return TaskRuntimeStores(
        pg_store=resolved_pg,
        redis_store=resolved_redis,
    )


@dataclass
class TaskRuntimeComponents:
    """Default runtime components backed by current legacy implementations."""

    state_machine: Optional[TaskStateMachine]
    checkpoint_manager: CheckpointManager
    preference_service: PreferenceLearningService
    risk_detector: RiskDetectorService


def build_runtime_components(
    *,
    pg_store: Optional[PostgresTaskStore],
    redis_store: RedisTaskStore,
) -> TaskRuntimeComponents:
    """Build default runtime dependencies for task flows."""

    state_machine = None
    if pg_store:
        state_machine = TaskStateMachine(
            pg_store=pg_store,
            redis_store=redis_store,
        )

    if not pg_store:
        raise RuntimeError("PostgreSQL store required for checkpoint management")
    pg_checkpoint_store = PostgresCheckpointStore(pg_store.db)
    checkpoint_manager = CheckpointManager(
        pg_checkpoint_store=pg_checkpoint_store,
        plan_store=redis_store,
    )

    return TaskRuntimeComponents(
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        preference_service=PreferenceLearningService(),
        risk_detector=RiskDetectorService(),
    )
