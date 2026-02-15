"""Base class for arrow tools.

Tools are functions that the LLM can call to perform actions like starting tasks,
checking status, or querying data. This design makes it easy to add new tools and
integrate with MCP (Model Context Protocol) in the future.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ToolParameter(BaseModel):
    """Schema for a tool parameter."""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[list] = None
    properties: Optional[Dict[str, Any]] = None  # For nested objects


class ToolDefinition(BaseModel):
    """OpenAI/OpenRouter function calling tool definition."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema format


class ToolResult(BaseModel):
    """Result from tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    message: Optional[str] = None


class BaseTool(ABC):
    """Abstract base class for arrow tools.

    Each tool must implement:
    - name: Unique identifier for the tool
    - description: What the tool does (for LLM)
    - get_definition(): OpenRouter function calling schema
    - execute(): Run the tool with given arguments

    Example:
        class MyTool(BaseTool):
            @property
            def name(self) -> str:
                return "my_tool"

            @property
            def description(self) -> str:
                return "Does something useful"

            def get_definition(self) -> ToolDefinition:
                return ToolDefinition(
                    name=self.name,
                    description=self.description,
                    parameters={
                        "type": "object",
                        "properties": {
                            "arg1": {"type": "string", "description": "First argument"}
                        },
                        "required": ["arg1"]
                    }
                )

            async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
                # Tool logic here
                return ToolResult(success=True, data={"result": "done"})
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        pass

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Return OpenRouter function calling definition for this tool."""
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            arguments: Tool-specific arguments from LLM
            context: Execution context (conversation_id, user_id, injected services, etc.)

        Returns:
            ToolResult with success status and data or error
        """
        pass

    def validate_arguments(self, arguments: Dict[str, Any]) -> Optional[str]:
        """Validate arguments against the tool's schema.

        Returns:
            Error message if validation fails, None if valid
        """
        # Basic validation - can be overridden for custom logic
        definition = self.get_definition()
        required = definition.parameters.get("required", [])

        for req_field in required:
            if req_field not in arguments:
                return f"Missing required argument: {req_field}"

        return None
