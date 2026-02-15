"""Infrastructure adapter for fast-path planning."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
import time
import structlog

from src.domain.tasks.ports import FastPathPlannerPort, TaskPersistencePort
from src.domain.tasks.planning_models import DataQuery, FastPathResult, PlanningIntent, is_fast_path_eligible
from src.domain.tasks.models import Task, TaskStep, StepStatus, TaskStatus
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


logger = structlog.get_logger(__name__)


class FastPathPlannerAdapter(FastPathPlannerPort):
    """Adapter that executes fast-path queries and builds completed tasks."""

    def __init__(
        self,
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
        persistence_port: Optional[TaskPersistencePort] = None,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store
        self._persistence_port = persistence_port

    async def try_fast_path(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: Optional[PlanningIntent],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        if not is_fast_path_eligible(intent_info):
            logger.debug("Fast path not eligible", intent_info=intent_info)
            return None

        start_time = time.time()

        try:
            data_query = DataQuery.from_intent(
                intent_info.data_query if intent_info else None
            )
            if not data_query:
                logger.debug("Could not build DataQuery from intent")
                return None

            fast_result = await self.execute_query(
                organization_id=organization_id,
                data_query=data_query,
            )

            if not fast_result.success:
                logger.warning(
                    "Fast path query failed, falling back to normal path",
                    error=fast_result.error,
                )
                return None

            task = await self.create_fast_path_task(
                user_id=user_id,
                organization_id=organization_id,
                goal=goal,
                intent_info=intent_info,
                fast_result=fast_result,
                metadata=metadata,
            )

            total_time_ms = (time.time() - start_time) * 1000
            logger.info(
                "Fast path completed",
                task_id=task.id,
                object_type=data_query.object_type,
                result_count=fast_result.total_count,
                total_time_ms=total_time_ms,
            )

            return task

        except Exception as exc:
            logger.warning(
                "Fast path exception, falling back to normal path",
                error=str(exc),
                goal=goal[:100],
            )
            return None

    async def execute_query(
        self,
        organization_id: str,
        data_query: DataQuery,
    ) -> FastPathResult:
        start_time = time.time()

        try:
            from src.interfaces.database import Database
            from src.infrastructure.workspace.workspace_service import WorkspaceService

            database = Database()
            results = []

            async with database.get_session() as session:
                workspace = WorkspaceService(session)

                if data_query.search_text:
                    results = await workspace.search(
                        org_id=organization_id,
                        query=data_query.search_text,
                        type=data_query.object_type,
                        limit=data_query.limit,
                    )
                else:
                    where_clause = data_query.build_where_clause()
                    results = await workspace.query(
                        org_id=organization_id,
                        type=data_query.object_type,
                        where=where_clause,
                        order_by=data_query.order_by,
                        order_desc=data_query.order_desc,
                        limit=data_query.limit,
                    )

            query_time_ms = int((time.time() - start_time) * 1000)

            return FastPathResult(
                success=True,
                data=results,
                total_count=len(results),
                query_time_ms=query_time_ms,
                object_type=data_query.object_type,
            )

        except Exception as exc:
            query_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Fast path query execution failed",
                error=str(exc),
                org_id=organization_id,
                object_type=data_query.object_type,
            )
            return FastPathResult(
                success=False,
                query_time_ms=query_time_ms,
                object_type=data_query.object_type,
                error=str(exc),
            )

    async def create_fast_path_task(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: PlanningIntent,
        fast_result: FastPathResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        task_metadata = metadata.copy() if metadata else {}
        task_metadata["fast_path"] = True
        task_metadata["fast_path_stats"] = {
            "query_time_ms": fast_result.query_time_ms,
            "intent_time_ms": fast_result.intent_time_ms,
            "total_time_ms": fast_result.total_time_ms,
        }
        task_metadata["result_data"] = {
            "object_type": fast_result.object_type,
            "data": fast_result.data,
            "total_count": fast_result.total_count,
        }
        task_metadata["result_count"] = fast_result.total_count

        data_query = intent_info.data_query or {}
        step = TaskStep(
            id="fast_path_query",
            name="Query Data",
            description=intent_info.rephrased_intent or goal,
            agent_type="data_query",
            domain=data_query.get("object_type", "unknown"),
            inputs={
                "object_type": data_query.get("object_type"),
                "date_range": data_query.get("date_range"),
                "search_text": data_query.get("search_text"),
                "where": data_query.get("where"),
                "limit": data_query.get("limit", 100),
            },
            outputs={
                "object_type": fast_result.object_type,
                "data": fast_result.data,
                "count": fast_result.total_count,
            },
            status=StepStatus.DONE,
        )

        task = Task(
            goal=goal,
            user_id=user_id,
            organization_id=organization_id,
            steps=[step],
            status=TaskStatus.COMPLETED,
            metadata=task_metadata,
            completed_at=datetime.utcnow(),
        )

        if self._persistence_port:
            await self._persistence_port.create_task(task)
            return task

        if self._pg_store:
            await self._pg_store.create_task(task)
        await self._redis_store.create_task(task)

        return task
