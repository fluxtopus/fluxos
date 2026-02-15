"""Inbox tool: Get status of a task (reused from Arrow)."""

from src.infrastructure.flux_runtime.tools.get_task_status import GetTaskStatusTool

# Re-export directly — same tool works in inbox context.
__all__ = ["GetTaskStatusTool"]
