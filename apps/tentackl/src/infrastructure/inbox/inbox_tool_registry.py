# REVIEW: Tool registry is hard-coded here, making tool availability static
# REVIEW: and compile-time. Consider config/feature-flagged registration or
# REVIEW: per-org tool policies to avoid shipping unused tools everywhere.
"""Inbox-specific tool registry.

Registers tools available to the inbox chat agent. Reuses Arrow's
ToolRegistry class but with a curated set of inbox tools.
"""

import structlog

from src.infrastructure.flux_runtime.tool_registry import ToolRegistry
from src.infrastructure.inbox.tools.create_task import InboxCreateTaskTool
from src.infrastructure.inbox.tools.workspace_query import WorkspaceQueryTool
from src.infrastructure.inbox.tools.web_search import WebSearchTool
from src.infrastructure.inbox.tools.send_notification import SendNotificationTool
from src.infrastructure.inbox.tools.task_capabilities import TaskCapabilitiesTool
from src.infrastructure.inbox.tools.create_agent import CreateAgentTool
from src.infrastructure.inbox.tools.integrations import IntegrationsTool
from src.infrastructure.inbox.tools.create_triggered_task import CreateTriggeredTaskTool
from src.infrastructure.inbox.tools.memory_search import MemoryTool
from src.infrastructure.flux_runtime.tools.get_task_status import GetTaskStatusTool
from src.infrastructure.flux_runtime.tools.approve_checkpoint import ApproveCheckpointTool

logger = structlog.get_logger(__name__)


def get_inbox_tool_registry() -> ToolRegistry:
    """Build a ToolRegistry with inbox-specific tools."""
    registry = ToolRegistry()

    # Core inbox tools
    registry.register(InboxCreateTaskTool())
    registry.register(GetTaskStatusTool())
    registry.register(ApproveCheckpointTool())

    # Extended tools
    registry.register(WorkspaceQueryTool())
    registry.register(WebSearchTool())
    registry.register(SendNotificationTool())
    registry.register(TaskCapabilitiesTool())
    registry.register(CreateAgentTool())
    registry.register(IntegrationsTool())
    registry.register(CreateTriggeredTaskTool())
    registry.register(MemoryTool())

    logger.info("Inbox tool registry initialized", tool_count=len(registry.get_all_tools()))
    return registry
