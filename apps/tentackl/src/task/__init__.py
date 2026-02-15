# REVIEW: Module exports only some stores; consumers must know which stores
# REVIEW: are missing (e.g., checkpoint store) which can lead to inconsistent
# REVIEW: import patterns. Consider a clearer storage interface layer.
"""
Task storage module.

Provides Redis and PostgreSQL implementations for task
and preference storage.

Note: PostgresCheckpointStore is not exported here to avoid circular imports.
Prefer importing from src.infrastructure.tasks.stores.postgres_checkpoint_store.
"""

from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_preference_store import RedisPreferenceStore

__all__ = [
    "RedisTaskStore",
    "PostgresTaskStore",
    "RedisPreferenceStore",
]
