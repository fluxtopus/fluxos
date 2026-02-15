# REVIEW: This tool mixes task queries and workspace object queries in one
# REVIEW: class with ad-hoc parsing. Consider splitting task vs workspace
# REVIEW: queries into separate tools or application services.
"""Inbox tool: Query workspace tasks, objects, and data."""

import json
from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.tasks import TaskUseCases
from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases
from src.domain.tasks.models import TaskStatus

logger = structlog.get_logger(__name__)

_task_use_cases: Optional[TaskUseCases] = None


async def _get_task_use_cases() -> TaskUseCases:
    global _task_use_cases
    if _task_use_cases is None:
        _task_use_cases = await provider_get_task_use_cases()
    return _task_use_cases


class WorkspaceQueryTool(BaseTool):
    """Query tasks, workspace objects (events, contacts, files), and search."""

    @property
    def name(self) -> str:
        return "workspace_query"

    @property
    def description(self) -> str:
        return (
            "Query the user's workspace. Supports task queries (active, completed, "
            "details, search) and workspace object queries (events, contacts, notes, "
            "projects, or any custom type). Also supports full-text search across all "
            "workspace data."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "active_tasks",
                            "recent_completions",
                            "task_details",
                            "search",
                            "events",
                            "contacts",
                            "workspace_objects",
                            "workspace_search",
                        ],
                        "description": (
                            "Type of query. Task queries: active_tasks, recent_completions, "
                            "task_details, search. Workspace queries: events (calendar events), "
                            "contacts (address book), workspace_objects (any type with filters), "
                            "workspace_search (full-text search across all objects)."
                        ),
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Task ID for task_details query.",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Search text. Used by: search (task keyword search), "
                            "workspace_search (full-text across all objects)."
                        ),
                    },
                    "object_type": {
                        "type": "string",
                        "description": (
                            "Object type filter for workspace_objects query "
                            "(e.g. 'event', 'contact', 'note', 'project', or any custom type)."
                        ),
                    },
                    "where": {
                        "type": "object",
                        "description": (
                            "MongoDB-style filter for workspace_objects. "
                            "Operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $exists, $regex. "
                            "Example: {\"status\": {\"$eq\": \"confirmed\"}, \"start\": {\"$gte\": \"2026-01-01\"}}"
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter workspace objects by tags (all must match).",
                    },
                    "order_by": {
                        "type": "string",
                        "description": (
                            "Sort field for workspace queries. Use 'data.field_name' for "
                            "data fields (e.g. 'data.start'), or 'created_at'/'updated_at'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10).",
                    },
                },
                "required": ["query_type"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        query_type = arguments["query_type"]
        user_id = context.get("user_id")
        organization_id = context.get("organization_id")
        limit = arguments.get("limit", 10)

        if not user_id:
            return ToolResult(success=False, error="Missing user_id")

        try:
            # --- Task queries ---
            if query_type in ("active_tasks", "recent_completions", "task_details", "search"):
                return await self._handle_task_query(query_type, arguments, user_id, limit)

            # --- Workspace object queries ---
            if not organization_id:
                return ToolResult(success=False, error="Missing organization_id for workspace queries.")

            if query_type == "events":
                return await self._handle_workspace_query(
                    organization_id, object_type="event", arguments=arguments, limit=limit,
                )
            elif query_type == "contacts":
                return await self._handle_workspace_query(
                    organization_id, object_type="contact", arguments=arguments, limit=limit,
                )
            elif query_type == "workspace_objects":
                object_type = arguments.get("object_type")
                return await self._handle_workspace_query(
                    organization_id, object_type=object_type, arguments=arguments, limit=limit,
                )
            elif query_type == "workspace_search":
                return await self._handle_workspace_search(
                    organization_id, arguments=arguments, limit=limit,
                )
            else:
                return ToolResult(success=False, error=f"Unknown query_type: {query_type}")

        except Exception as e:
            logger.error("Workspace query failed", error=str(e), query_type=query_type)
            return ToolResult(success=False, error=f"Query failed: {str(e)}")

    # ---------------------------------------------------------------
    # Task queries (existing functionality)
    # ---------------------------------------------------------------

    async def _handle_task_query(
        self, query_type: str, arguments: Dict[str, Any], user_id: str, limit: int,
    ) -> ToolResult:
        task_use_cases = await _get_task_use_cases()
        active_statuses = {
            TaskStatus.PLANNING,
            TaskStatus.READY,
            TaskStatus.EXECUTING,
            TaskStatus.CHECKPOINT,
        }

        if query_type == "active_tasks":
            all_tasks = await task_use_cases.list_tasks(user_id=user_id, status=None, limit=200)
            tasks = [t for t in all_tasks if t.status in active_statuses][:limit]
            return ToolResult(
                success=True,
                data={
                    "tasks": [
                        {
                            "id": str(t.id),
                            "goal": t.goal,
                            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        }
                        for t in tasks
                    ]
                },
            )

        elif query_type == "recent_completions":
            all_tasks = await task_use_cases.list_tasks(user_id=user_id, status=None, limit=200)
            tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED][:limit]
            return ToolResult(
                success=True,
                data={
                    "tasks": [
                        {
                            "id": str(t.id),
                            "goal": t.goal,
                            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        }
                        for t in tasks
                    ]
                },
            )

        elif query_type == "task_details":
            task_id = arguments.get("task_id")
            if not task_id:
                return ToolResult(success=False, error="task_id required for task_details")
            task = await task_use_cases.get_task(task_id)
            if not task:
                return ToolResult(success=False, error=f"Task {task_id} not found")
            return ToolResult(
                success=True,
                data={
                    "id": str(task.id),
                    "goal": task.goal,
                    "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                    "steps": [
                        {
                            "name": s.get("name", ""),
                            "status": s.get("status", ""),
                            "outputs": s.get("outputs"),
                        }
                        for s in (task.steps or [])
                    ],
                },
            )

        elif query_type == "search":
            search_query = (arguments.get("query") or "").strip().lower()
            if not search_query:
                return ToolResult(success=False, error="query is required for task search.")
            all_tasks = await task_use_cases.list_tasks(user_id=user_id, status=None, limit=200)
            tasks = [
                t for t in all_tasks
                if search_query in (t.goal or "").lower()
            ][:limit]
            return ToolResult(
                success=True,
                data={
                    "tasks": [
                        {
                            "id": str(t.id),
                            "goal": t.goal,
                            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                        }
                        for t in tasks
                    ]
                },
            )

        return ToolResult(success=False, error=f"Unknown task query: {query_type}")

    # ---------------------------------------------------------------
    # Workspace object queries (events, contacts, notes, etc.)
    # ---------------------------------------------------------------

    async def _handle_workspace_query(
        self,
        organization_id: str,
        object_type: Optional[str],
        arguments: Dict[str, Any],
        limit: int,
    ) -> ToolResult:
        from src.interfaces.database import Database
        from src.infrastructure.workspace.workspace_service import WorkspaceService

        database = Database()
        async with database.get_session() as session:
            service = WorkspaceService(session)
            objects = await service.query(
                org_id=organization_id,
                type=object_type,
                where=arguments.get("where"),
                tags=arguments.get("tags"),
                order_by=arguments.get("order_by"),
                limit=limit,
            )

        return ToolResult(
            success=True,
            data={
                "type": object_type or "all",
                "count": len(objects),
                "objects": [_summarize_object(o) for o in objects],
            },
            message=f"Found {len(objects)} {object_type or 'workspace'} object(s).",
        )

    async def _handle_workspace_search(
        self,
        organization_id: str,
        arguments: Dict[str, Any],
        limit: int,
    ) -> ToolResult:
        query = (arguments.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="query is required for workspace_search.")

        from src.interfaces.database import Database
        from src.infrastructure.workspace.workspace_service import WorkspaceService

        database = Database()
        async with database.get_session() as session:
            service = WorkspaceService(session)
            objects = await service.search(
                org_id=organization_id,
                query=query,
                type=arguments.get("object_type"),
                limit=limit,
            )

        return ToolResult(
            success=True,
            data={
                "query": query,
                "count": len(objects),
                "objects": [_summarize_object(o) for o in objects],
            },
            message=f"Found {len(objects)} result(s) for '{query}'.",
        )


def _summarize_object(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact summary of a workspace object for the LLM."""
    data = obj.get("data", {})
    # Truncate large data fields to keep context manageable
    data_str = json.dumps(data, default=str)
    if len(data_str) > 1500:
        data_str = data_str[:1500] + "…"
        data = json.loads(data_str + "}")  # best-effort truncation
    return {
        "id": obj.get("id"),
        "type": obj.get("type"),
        "data": data,
        "tags": obj.get("tags", []),
        "created_at": obj.get("created_at"),
    }
