"""Registry for managing arrow tools.

The registry maintains all available tools and provides methods to:
- Register new tools
- Get tool definitions for LLM function calling
- Retrieve tool instances for execution
"""

from __future__ import annotations
from typing import Dict, List, Optional
import structlog

from .tools.base import BaseTool, ToolDefinition
from .tools.search_agents import SearchAgentsTool
from .tools.start_task import StartTaskTool
from .tools.approve_checkpoint import ApproveCheckpointTool
from .tools.get_task_status import GetTaskStatusTool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry for arrow tools.

    Manages all available tools and provides access to their definitions and instances.
    Tools can be registered dynamically, making it easy to extend functionality or
    integrate with MCP (Model Context Protocol) in the future.

    Example:
        # Get the default registry with built-in tools
        registry = ToolRegistry.get_default()

        # Register a custom tool
        registry.register(MyCustomTool())

        # Get tool definitions for LLM
        tool_defs = registry.get_tool_definitions()

        # Execute a tool
        result = await registry.execute_tool("start_task", {...}, context)
    """

    def __init__(self):
        """Initialize empty registry."""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool", tool_name=tool.name)

        self._tools[tool.name] = tool
        logger.info("Tool registered", tool_name=tool.name, description=tool.description)

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from the registry.

        Args:
            tool_name: Name of the tool to remove
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info("Tool unregistered", tool_name=tool_name)

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get a tool instance by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)

    def get_all_tools(self) -> List[BaseTool]:
        """Get all registered tools.

        Returns:
            List of all tool instances
        """
        return list(self._tools.values())

    def get_tool_definitions(self) -> List[Dict]:
        """Get OpenRouter function calling definitions for all tools.

        Returns:
            List of tool definitions in OpenRouter format
        """
        definitions = []
        for tool in self._tools.values():
            try:
                definition = tool.get_definition()
                # Convert to OpenRouter function calling format
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": definition.name,
                        "description": definition.description,
                        "parameters": definition.parameters
                    }
                })
            except Exception as e:
                logger.error("Failed to get tool definition", tool_name=tool.name, error=str(e))

        return definitions

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is registered.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is registered, False otherwise
        """
        return tool_name in self._tools

    @classmethod
    def get_default(cls) -> ToolRegistry:
        """Get a registry with all default arrow tools registered.

        Returns:
            ToolRegistry with built-in tools
        """
        registry = cls()

        # Register built-in tools (tasks + agents)
        registry.register(SearchAgentsTool())

        # Task delegation tools
        registry.register(StartTaskTool())  # Start autonomous background tasks
        registry.register(ApproveCheckpointTool())  # Approve/reject task checkpoints
        registry.register(GetTaskStatusTool())  # Check task status and progress

        # Future tools can be added here:
        # registry.register(ListTasksTool())
        # registry.register(CancelTaskTool())
        # registry.register(GetNodeDetailsTool())

        logger.info("Default tool registry initialized", tool_count=len(registry._tools))

        return registry


# Global default registry instance
_default_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global default tool registry.

    Returns:
        The default ToolRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry.get_default()
    return _default_registry
