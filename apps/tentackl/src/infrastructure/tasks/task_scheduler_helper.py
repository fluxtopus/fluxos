"""Task scheduler helper for scheduling ready nodes."""

import structlog

logger = structlog.get_logger()


async def _finalize_task_if_terminal(
    tree,
    task_id: str,
    dispatch_failures: list,
) -> None:
    """
    Finalize a task if all remaining paths are dead after dispatch failures.

    When a step cannot be dispatched, we mark it failed in the tree. If that
    failure makes the task terminal, update stores and emit completion events
    so UI + downstream consumers reflect the terminal state.
    """
    try:
        from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
        from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
        from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
        from src.interfaces.database import Database
        from src.infrastructure.tasks.event_publisher import TaskEventPublisher
        from datetime import datetime

        adapter = TaskExecutionTreeAdapter(tree=tree)
        is_complete, final_status = await adapter.is_task_complete(task_id)

        if not is_complete:
            return

        redis_store = RedisTaskStore()
        await redis_store._connect()

        db = Database()
        await db.connect()
        pg_store = PostgresTaskStore(db)

        status_value = "completed" if final_status == "completed" else "failed"
        now = datetime.utcnow()

        await redis_store.update_task(task_id, {
            "status": status_value,
            "completed_at": now,
        })
        await pg_store.update_task(task_id, {
            "status": status_value,
            "completed_at": now,
        })

        publisher = TaskEventPublisher()
        metrics = await tree.get_tree_metrics(task_id)
        steps_completed = max(0, metrics.get("status_counts", {}).get("completed", 1) - 1)
        await publisher.task_completed(task_id=task_id, steps_completed=steps_completed)

        error_summary = "; ".join(f"{nid}: {err}" for nid, err in dispatch_failures[:3])
        logger.info(
            "Task finalized after dispatch failure",
            task_id=task_id,
            final_status=status_value,
            dispatch_failures=len(dispatch_failures),
            error_summary=error_summary,
        )

        await redis_store._disconnect()
        await db.disconnect()

    except Exception as e:
        logger.error(
            "Failed to finalize task after dispatch failure",
            task_id=task_id,
            error=str(e),
        )


async def schedule_ready_nodes(task_id: str) -> int:
    """
    Schedule ready nodes for execution via Celery.

    This function examines the execution tree for a task and schedules
    any nodes that are ready to execute (all dependencies completed).

    Uses StepDispatcher to ensure proper context injection (plan_id, user_id, etc.)
    for plugins that need task context.

    PAUSE-AWARE: Blocks scheduling if the task is paused to prevent new
    work from being dispatched while paused.

    Args:
        task_id: The task ID (also the execution tree ID)

    Returns:
        Number of nodes scheduled
    """
    from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
    from src.core.execution_tree import ExecutionStatus
    from src.domain.tasks.models import TaskStep, TaskStatus, StepStatus
    from src.infrastructure.tasks.step_dispatcher import StepDispatcher
    from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
    from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
    from src.interfaces.database import Database
    from src.core.config import settings
    import redis.asyncio as redis_async

    exec_tree = RedisExecutionTree()
    dispatcher = StepDispatcher()
    scheduled_count = 0
    dispatch_failures = []
    redis_client = None
    scheduled_key = f"tentackl:run:{task_id}:scheduled"

    try:
        # Check if task is paused before scheduling any work
        # This prevents race conditions where pause happens during scheduling
        redis_store = RedisTaskStore()
        await redis_store._connect()
        task = await redis_store.get_task(task_id)

        if not task:
            # Try PostgreSQL as fallback
            db = Database()
            await db.connect()
            pg_store = PostgresTaskStore(db)
            task = await pg_store.get_task(task_id)
            await db.disconnect()

        if task and task.status == TaskStatus.PAUSED:
            logger.info(
                "Skipping node scheduling - task is paused",
                task_id=task_id,
                task_status=task.status.value,
            )
            await redis_store._disconnect()
            return 0

        await redis_store._disconnect()

        # Get tree data
        tree = await exec_tree.get_tree(task_id)
        if not tree:
            logger.warning("Task tree not found", task_id=task_id)
            return 0

        # Get nodes that are ready to execute (dependencies satisfied)
        ready_nodes = await exec_tree.get_ready_nodes(task_id)
        if not ready_nodes:
            logger.debug("No ready nodes in task tree", task_id=task_id)
            return 0

        redis_client = await redis_async.from_url(settings.REDIS_URL, decode_responses=True)

        # Schedule each ready node via StepDispatcher
        for node in ready_nodes:
            # Skip root node
            if node.id == "root":
                continue

            # Only pending nodes
            if node.status != ExecutionStatus.PENDING:
                continue

            # Deduplicate scheduling
            already = await redis_client.sismember(scheduled_key, node.id)
            if already:
                continue
            await redis_client.sadd(scheduled_key, node.id)
            await redis_client.expire(scheduled_key, 86400)

            # Mark as running in tree (before dispatching to Celery)
            await exec_tree.update_node_status(task_id, node.id, ExecutionStatus.RUNNING)

            # Build TaskStep from node metadata
            agent_type = node.metadata.get("agent_type") if node.metadata else None
            step = TaskStep(
                id=node.id,
                name=node.name or node.id,
                description=node.metadata.get("description", "") if node.metadata else "",
                agent_type=agent_type or "unknown",
                inputs=node.task_data or (node.metadata.get("inputs", {}) if node.metadata else {}),
                outputs=node.metadata.get("outputs", {}) if node.metadata else {},
                status=StepStatus.PENDING,
            )

            # Dispatch via StepDispatcher (handles context injection)
            result = await dispatcher.dispatch_step(task_id, step)

            if result.success:
                scheduled_count += 1
                logger.info(
                    "Scheduled node for execution",
                    task_id=task_id,
                    node_id=node.id,
                    node_name=node.name,
                )
            else:
                logger.error(
                    "Failed to dispatch node",
                    task_id=task_id,
                    node_id=node.id,
                    error=result.error,
                )
                # Mark node as failed in tree
                await exec_tree.update_node_status(
                    task_id, node.id, ExecutionStatus.FAILED,
                    error_data={"error": result.error},
                )
                dispatch_failures.append((node.id, result.error))

        if dispatch_failures:
            await _finalize_task_if_terminal(exec_tree, task_id, dispatch_failures)

        return scheduled_count

    except Exception as e:
        logger.error(
            "Failed to schedule ready nodes",
            task_id=task_id,
            error=str(e),
            exc_info=True,
        )
        return scheduled_count
    finally:
        try:
            await exec_tree._disconnect()
        except Exception:
            pass
        if redis_client:
            try:
                await redis_client.aclose()
            except Exception:
                pass


async def get_tree_type(exec_tree, tree_id: str) -> str:
    """Return the tree type from metadata; defaults to 'task'."""
    tree = await exec_tree.get_tree(tree_id)
    if not tree:
        return "task"

    metadata = tree.get("metadata", {})
    tree_type = metadata.get("type") or tree.get("type")
    return tree_type or "task"
