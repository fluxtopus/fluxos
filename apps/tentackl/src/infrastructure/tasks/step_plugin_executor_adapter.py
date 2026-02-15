"""Infrastructure adapter for step plugin execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import structlog

from src.domain.tasks.ports import StepPluginExecutorPort

logger = structlog.get_logger(__name__)


class StepPluginExecutorAdapter(StepPluginExecutorPort):
    """Wraps ``execute_step()`` from the plugin executor.

    Handles workspace plugin DB initialisation and ``ExecutionContext``
    building internally so the use case doesn't need to know about
    infrastructure details.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    async def execute(
        self,
        step: Any,
        model: str,
        task_id: Optional[str] = None,
        org_id: Optional[str] = None,
        step_id: Optional[str] = None,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        from src.plugins.workspace_plugin import set_database as set_workspace_db
        from src.plugins.workspace_csv_plugin import set_database as set_workspace_csv_db
        from src.infrastructure.execution_runtime.plugin_executor import execute_step

        set_workspace_db(self._db)
        set_workspace_csv_db(self._db)

        execution_context = self._build_execution_context(task_id, org_id, step_id)

        return await execute_step(
            step=step,
            llm_client=None,
            model=model,
            organization_id=org_id,
            context=execution_context,
            file_references=file_references,
        )

    def _build_execution_context(
        self,
        task_id: Optional[str],
        org_id: Optional[str],
        step_id: Optional[str],
    ) -> Any:
        """Build ExecutionContext if org_id is available."""
        if not org_id:
            return None
        try:
            from src.infrastructure.execution_runtime.execution_context import ExecutionContext
            return ExecutionContext(
                organization_id=org_id,
                task_id=task_id,
                step_id=step_id,
            )
        except Exception as ctx_err:
            logger.warning(
                "Failed to build ExecutionContext, proceeding without it",
                task_id=task_id,
                step_id=step_id,
                error=str(ctx_err),
            )
            return None
