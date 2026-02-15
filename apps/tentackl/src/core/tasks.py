# REVIEW:
# - Celery worker init uses asyncio.get_event_loop().run_until_complete; can break if event loop already running.
# - File mixes many unrelated concerns (DB pooling, inbox messaging, scheduling), making it hard to test.
"""Celery task definitions for durable task execution."""

import os
from celery import Task
from celery.signals import worker_init, worker_shutdown
from src.core.celery_app import app
import structlog
import asyncio
from typing import Optional

logger = structlog.get_logger()

_db_instance: Optional["Database"] = None
_db_lock = asyncio.Lock()
_db_initialized = False
_db_last_health_check = 0.0
_DB_HEALTH_CHECK_INTERVAL = 60.0  # Only check every 60 seconds


@worker_init.connect
def init_worker_db(**kwargs):
    """Initialize database connection when Celery worker starts."""
    global _db_instance, _db_initialized
    try:
        from src.interfaces.database import Database
        _db_instance = Database()
        asyncio.get_event_loop().run_until_complete(_db_instance.connect())
        _db_initialized = True
        logger.info("Celery worker database connection initialized")
    except Exception as e:
        logger.error("Failed to initialize Celery worker database", error=str(e))
        _db_instance = None
        _db_initialized = False


@worker_shutdown.connect
def shutdown_worker_db(**kwargs):
    """Close database connection when Celery worker stops."""
    global _db_instance, _db_initialized
    if _db_instance:
        try:
            asyncio.get_event_loop().run_until_complete(_db_instance.disconnect())
            logger.info("Celery worker database connection closed")
        except Exception as e:
            logger.error("Failed to close Celery worker database", error=str(e))
        finally:
            _db_instance = None
            _db_initialized = False


async def get_shared_db():
    """Get the shared database connection for periodic tasks.

    This connection is initialized when the Celery worker starts and closed
    when it stops. DO NOT call db.disconnect() on the returned instance.

    If worker_init hasn't fired yet (e.g., running outside Celery), creates
    a new connection on-demand.
    """
    global _db_instance, _db_initialized, _db_last_health_check
    import time

    # Fast path: already initialized by worker_init signal
    if _db_initialized and _db_instance is not None:
        # Periodic health check: only verify every N seconds to reduce overhead
        now = time.time()
        if now - _db_last_health_check > _DB_HEALTH_CHECK_INTERVAL:
            try:
                async with _db_instance.get_session() as session:
                    from sqlalchemy import text
                    await session.execute(text("SELECT 1"))
                _db_last_health_check = now
            except Exception as e:
                logger.warning("Shared DB connection unhealthy, reconnecting", error=str(e))
                _db_initialized = False

        if _db_initialized:
            return _db_instance

    # Slow path: initialize on-demand (outside Celery or after health check failure)
    async with _db_lock:
        if _db_instance is None or not _db_initialized:
            from src.interfaces.database import Database
            if _db_instance:
                try:
                    await _db_instance.disconnect()
                except Exception:
                    pass
            _db_instance = Database()
            await _db_instance.connect()
            _db_initialized = True
            _db_last_health_check = time.time()
            logger.info("Shared database connection initialized on-demand")

    return _db_instance


@app.task(name='src.core.tasks.execute_task_step', bind=True, max_retries=3)
def execute_task_step(self, task_id: str, step_data: dict):
    """Execute a task step via Celery worker using durable execution tree.

    This is a thin composition root that builds infrastructure adapters,
    wires them into ``StepExecutionUseCase``, and delegates all business
    logic to the application layer.

    Args:
        task_id: The task ID (also the execution tree ID)
        step_data: Serialized step data including id, agent_type, inputs, etc.
    """
    async def _execute():
        from src.interfaces.database import Database
        import src.database.models  # noqa: F401 — register ORM models
        from src.domain.tasks.models import StepStatus
        from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
        from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
        from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
        from src.infrastructure.tasks.event_publisher import TaskEventPublisher
        from src.infrastructure.tasks.task_scheduler_adapter import TaskSchedulerAdapter
        from src.infrastructure.tasks.step_inbox_messaging_adapter import StepInboxMessagingAdapter
        from src.infrastructure.tasks.step_plugin_executor_adapter import StepPluginExecutorAdapter
        from src.infrastructure.tasks.step_checkpoint_adapter import StepCheckpointAdapter
        from src.infrastructure.tasks.step_model_selector_adapter import StepModelSelectorAdapter
        from src.application.tasks.step_execution_use_case import StepExecutionUseCase
        from src.llm.openrouter_client import OpenRouterClient
        from src.infrastructure.inbox.summary_service import SummaryGenerationService

        step_id = step_data.get("id")

        # 1. Create infrastructure
        db = Database()
        tree_adapter = None
        redis_store = None
        publisher = None
        pg_store = None

        try:
            await db.connect()

            tree_adapter = TaskExecutionTreeAdapter()
            redis_store = RedisTaskStore()
            await redis_store._connect()
            pg_store = PostgresTaskStore(db)
            publisher = TaskEventPublisher()

            # 2. Build adapters
            summary_llm = OpenRouterClient()
            summary_service = SummaryGenerationService(llm_client=summary_llm)
            inbox_adapter = StepInboxMessagingAdapter(db, publisher, summary_service=summary_service)
            plugin_adapter = StepPluginExecutorAdapter(db)
            checkpoint_adapter = StepCheckpointAdapter(db)
            model_adapter = StepModelSelectorAdapter()
            scheduler_adapter = TaskSchedulerAdapter()

            # 3. Build use case
            use_case = StepExecutionUseCase(
                tree=tree_adapter,
                plan_store=redis_store,
                task_store=pg_store,
                event_bus=publisher,
                scheduler=scheduler_adapter,
                inbox=inbox_adapter,
                plugin=plugin_adapter,
                model_selector=model_adapter,
                checkpoint=checkpoint_adapter,
            )

            # 4. Execute
            result = await use_case.execute(task_id, step_data)

            # 5. Handle retry re-dispatch (Celery-specific concern)
            if result.status == "retrying" and result.retry_step_data:
                execute_task_step.delay(task_id=task_id, step_data=result.retry_step_data)

            return {
                "status": result.status,
                "task_id": result.task_id,
                "step_id": result.step_id,
                "output": result.output,
                "error": result.error,
            }

        except Exception as e:
            logger.error(
                "Task step execution error",
                task_id=task_id,
                step_id=step_id,
                error=str(e),
            )

            # Best-effort failure recording
            try:
                if tree_adapter:
                    await tree_adapter.fail_step(task_id, step_id, str(e))
            except Exception:
                pass

            updates = {
                "status": StepStatus.FAILED.value,
                "error_message": str(e),
            }
            try:
                if redis_store:
                    await redis_store.update_step(task_id, step_id, updates)
                if pg_store:
                    await pg_store.update_step(task_id, step_id, updates)
            except Exception:
                pass

            raise

        finally:
            # Clean up all connections before asyncio.run() closes the event loop
            try:
                if publisher:
                    await publisher.close()
            except Exception:
                pass
            try:
                if tree_adapter and tree_adapter._tree:
                    await tree_adapter._tree._disconnect()
            except Exception:
                pass
            try:
                if redis_store:
                    await redis_store._disconnect()
            except Exception:
                pass
            try:
                await db.disconnect()
            except Exception:
                pass

    return asyncio.run(_execute())


@app.task(name='src.core.tasks.cleanup_expired_agents')
def cleanup_expired_agents():
    """Clean up expired or stuck agents"""
    logger.info("Running agent cleanup")
    
    # Implementation would check for stuck agents
    # and clean them up
    return {'cleaned': 0}


@app.task(name='src.core.tasks.check_agent_heartbeats')
def check_agent_heartbeats():
    """Check agent heartbeats"""
    logger.info("Checking agent heartbeats")
    
    # Implementation would check agent health
    return {'checked': 0}


@app.task(name='src.core.tasks.check_automations')
def check_automations():
    """Poll the automations table and fire any due schedules.

    For each automation where enabled=True and next_run_at <= now():
    1. Atomically advance next_run_at to prevent double-fire
    2. Clone the template task and start execution
    3. Update last_run_at

    Errors in one automation do not block others.
    """
    async def _execute():
        from datetime import datetime
        from sqlalchemy import select, update as sa_update, and_
        from src.database.automation_models import Automation
        from src.core.cron_utils import calculate_next_run

        db = await get_shared_db()
        now = datetime.utcnow()

        # Find due automations
        async with db.get_session() as session:
            result = await session.execute(
                select(Automation).where(
                    and_(
                        Automation.enabled == True,
                        Automation.next_run_at <= now,
                    )
                )
            )
            due = result.scalars().all()

        if not due:
            return {"checked": 0, "fired": 0}

        logger.info("Found due automations", count=len(due))
        fired = 0

        for auto in due:
            try:
                is_one_time = auto.execute_at is not None and auto.cron is None

                if is_one_time:
                    # One-time: disable immediately (CAS guard on next_run_at)
                    async with db.get_session() as session:
                        res = await session.execute(
                            sa_update(Automation)
                            .where(
                                and_(
                                    Automation.id == auto.id,
                                    Automation.next_run_at <= now,
                                )
                            )
                            .values(enabled=False, next_run_at=None)
                        )
                        await session.commit()

                        if res.rowcount == 0:
                            logger.debug("Automation already advanced", automation_id=str(auto.id))
                            continue
                else:
                    # Recurring: advance next_run_at (prevents double-fire)
                    # Convert to UTC-naive for storage in DateTime column
                    new_next = calculate_next_run(auto.cron, auto.timezone or "UTC")
                    if new_next.tzinfo is not None:
                        import pytz as _pytz
                        new_next = new_next.astimezone(_pytz.UTC).replace(tzinfo=None)
                    async with db.get_session() as session:
                        res = await session.execute(
                            sa_update(Automation)
                            .where(
                                and_(
                                    Automation.id == auto.id,
                                    Automation.next_run_at <= now,  # CAS guard
                                )
                            )
                            .values(next_run_at=new_next)
                        )
                        await session.commit()

                        if res.rowcount == 0:
                            logger.debug("Automation already advanced", automation_id=str(auto.id))
                            continue

                # Clone and execute
                from src.application.tasks.providers import (
                    get_task_use_cases as provider_get_task_use_cases,
                )

                task_use_cases = await provider_get_task_use_cases()
                await task_use_cases.clone_and_execute_from_automation(
                    automation_id=str(auto.id),
                    template_task_id=str(auto.task_id),
                    user_id=auto.owner_id,
                    organization_id=auto.organization_id,
                )

                # Update last_run_at
                async with db.get_session() as session:
                    await session.execute(
                        sa_update(Automation)
                        .where(Automation.id == auto.id)
                        .values(last_run_at=datetime.utcnow())
                    )
                    await session.commit()

                fired += 1
                logger.info(
                    "Automation fired",
                    automation_id=str(auto.id),
                    one_time=is_one_time,
                    next_run_at=str(None if is_one_time else new_next),
                )

            except Exception as e:
                logger.error(
                    "Automation execution failed",
                    automation_id=str(auto.id),
                    error=str(e),
                    exc_info=True,
                )

        return {"checked": len(due), "fired": fired}

    return asyncio.run(_execute())


#
# DEPRECATED: Calendar assistant now uses the automations/task system.


@app.task(name='src.core.tasks.generate_capability_embedding', bind=True, max_retries=3)
def generate_capability_embedding(self, capability_id: str):
    """
    Generate embedding for a single capability (background task).

    This task is triggered when a capability is created or updated.
    It generates a semantic embedding for the capability's description
    and stores it in the database for semantic search.

    Args:
        capability_id: UUID of the capability to generate embedding for

    Returns:
        dict with status and details
    """
    async def _execute():
        from src.infrastructure.capabilities.capability_embedding_adapter import (
            CapabilityEmbeddingAdapter,
        )

        logger.info(
            "Generating capability embedding",
            capability_id=capability_id,
        )

        service = CapabilityEmbeddingAdapter()

        if not service.is_enabled:
            logger.warning(
                "Capability embedding skipped - service not enabled",
                capability_id=capability_id,
            )
            return {
                "ok": False,
                "capability_id": capability_id,
                "error": "Embedding service not enabled (OPENAI_API_KEY not set)",
            }

        try:
            success = await service.generate_and_store_embedding(capability_id)

            if success:
                logger.info(
                    "Capability embedding generated successfully",
                    capability_id=capability_id,
                )
                return {
                    "ok": True,
                    "capability_id": capability_id,
                }
            else:
                logger.warning(
                    "Capability embedding generation failed",
                    capability_id=capability_id,
                )
                return {
                    "ok": False,
                    "capability_id": capability_id,
                    "error": "Embedding generation failed",
                }

        except Exception as e:
            logger.error(
                "Error generating capability embedding",
                capability_id=capability_id,
                error=str(e),
                exc_info=True,
            )
            # Retry with exponential backoff
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))

    return asyncio.run(_execute())


@app.task(name='src.core.tasks.backfill_capability_embeddings')
def backfill_capability_embeddings(batch_size: int = 50, organization_id: Optional[str] = None):
    """
    Backfill embeddings for capabilities that don't have them yet.

    This task can be run periodically or on-demand to generate embeddings
    for capabilities with embedding_status='pending' or 'failed'.

    Args:
        batch_size: Number of capabilities to process in this batch
        organization_id: Optional org ID to limit scope

    Returns:
        dict with statistics about processed capabilities
    """
    async def _execute():
        from src.infrastructure.capabilities.capability_embedding_adapter import (
            CapabilityEmbeddingAdapter,
        )

        logger.info(
            "Starting capability embedding backfill",
            batch_size=batch_size,
            organization_id=organization_id,
        )

        service = CapabilityEmbeddingAdapter()

        if not service.is_enabled:
            logger.warning("Capability embedding backfill skipped - service not enabled")
            return {
                "ok": False,
                "error": "Embedding service not enabled (OPENAI_API_KEY not set)",
            }

        try:
            stats = await service.backfill_embeddings(
                batch_size=batch_size,
                organization_id=organization_id,
            )

            logger.info(
                "Capability embedding backfill complete",
                stats=stats,
            )

            return {
                "ok": True,
                **stats,
            }

        except Exception as e:
            logger.error(
                "Error during capability embedding backfill",
                error=str(e),
                exc_info=True,
            )
            return {
                "ok": False,
                "error": str(e),
            }

    return asyncio.run(_execute())


@app.task(name='src.core.tasks.retry_failed_memory_embeddings')
def retry_failed_memory_embeddings(batch_size: int = 50):
    """
    Retry embedding generation for memories with embedding_status='failed'.

    Runs periodically via Celery Beat to recover from transient OpenAI failures.

    Args:
        batch_size: Number of failed memories to process per run

    Returns:
        dict with statistics about retried memories
    """
    async def _execute():
        from src.infrastructure.memory.memory_store import MemoryStore
        from src.llm import OpenAIEmbeddingClient

        logger.info(
            "Starting failed memory embedding retry",
            batch_size=batch_size,
        )

        if not _db_instance:
            logger.warning("retry_failed_memory_embeddings skipped - database not initialized")
            return {"ok": False, "error": "Database not initialized"}

        store = MemoryStore(_db_instance)
        embedding_client = OpenAIEmbeddingClient()

        if not embedding_client.is_configured:
            logger.warning("retry_failed_memory_embeddings skipped - embedding client not configured")
            return {"ok": False, "error": "Embedding client not configured (OPENAI_API_KEY not set)"}

        failed_memories = await store.list_failed_embeddings(batch_size=batch_size)

        if not failed_memories:
            logger.debug("No failed memory embeddings to retry")
            return {"ok": True, "retried": 0, "succeeded": 0, "failed": 0}

        succeeded = 0
        failed = 0

        for memory_id, key in failed_memories:
            try:
                # Load current version body
                version = await store.get_current_version(memory_id)
                if not version or not version.body:
                    logger.warning(
                        "retry_embedding_skip_no_body",
                        memory_id=memory_id,
                        key=key,
                    )
                    failed += 1
                    continue

                # Generate embedding
                async with embedding_client as client:
                    result = await client.create_embedding(version.body)

                # Store the embedding
                success = await store.update_embedding(
                    memory_id=memory_id,
                    embedding=result.embedding,
                    status="completed",
                )

                if success:
                    succeeded += 1
                    logger.info(
                        "retry_embedding_succeeded",
                        memory_id=memory_id,
                        key=key,
                    )
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                logger.error(
                    "retry_embedding_failed",
                    memory_id=memory_id,
                    key=key,
                    error=str(e),
                )

        logger.info(
            "Failed memory embedding retry complete",
            retried=len(failed_memories),
            succeeded=succeeded,
            failed=failed,
        )

        return {
            "ok": True,
            "retried": len(failed_memories),
            "succeeded": succeeded,
            "failed": failed,
        }

    return asyncio.run(_execute())
