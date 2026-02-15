"""Executor for arrow tool calls.

Handles dispatching tool calls from LLM responses and managing execution context.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import json
import structlog

from .tools.base import ToolResult
from .tool_registry import ToolRegistry, get_registry

logger = structlog.get_logger(__name__)


class ToolCall(dict):
    """Represents a tool call from the LLM.

    OpenRouter/OpenAI format:
    {
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "tool_name",
            "arguments": "{\"arg1\": \"value1\"}"  # JSON string
        }
    }
    """

    @property
    def call_id(self) -> str:
        """Get the tool call ID."""
        return self.get("id", "")

    @property
    def function_name(self) -> str:
        """Get the function name."""
        func = self.get("function", {})
        return func.get("name", "") if isinstance(func, dict) else ""

    @property
    def arguments(self) -> Dict[str, Any]:
        """Get the parsed arguments."""
        func = self.get("function", {})
        if not isinstance(func, dict):
            return {}

        args_str = func.get("arguments", "{}")
        if isinstance(args_str, str):
            try:
                return json.loads(args_str)
            except json.JSONDecodeError:
                logger.error("Failed to parse tool arguments", arguments=args_str)
                return {}
        return args_str if isinstance(args_str, dict) else {}


class ToolExecutor:
    """Executes tool calls from LLM responses.

    Handles:
    - Validating tool calls
    - Injecting execution context
    - Dispatching to appropriate tool implementations
    - Formatting results for LLM

    Example:
        executor = ToolExecutor(registry=get_registry())

        # Execute a single tool call
        result = await executor.execute_tool_call(
            tool_call={"id": "call_1", "function": {"name": "start_task", "arguments": "..."}},
            context={"task_service": task_service, ...}
        )

        # Execute multiple tool calls
        results = await executor.execute_tool_calls(tool_calls_list, context)
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """Initialize the executor.

        Args:
            registry: ToolRegistry to use (defaults to global registry)
        """
        self.registry = registry or get_registry()

    async def execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single tool call.

        Args:
            tool_call: Tool call object from LLM response
            context: Execution context with injected services

        Returns:
            Tool response in OpenRouter format:
            {
                "tool_call_id": "call_abc123",
                "role": "tool",
                "name": "tool_name",
                "content": "JSON string with result"
            }
        """
        tc = ToolCall(tool_call)

        # Get tool instance
        tool = self.registry.get_tool(tc.function_name)

        if not tool:
            error_result = ToolResult(
                success=False,
                error=f"Tool '{tc.function_name}' not found"
            )
            return self._format_tool_response(tc.call_id, tc.function_name, error_result)

        # Validate arguments
        validation_error = tool.validate_arguments(tc.arguments)
        if validation_error:
            error_result = ToolResult(
                success=False,
                error=f"Invalid arguments: {validation_error}"
            )
            return self._format_tool_response(tc.call_id, tc.function_name, error_result)

        # Execute tool
        try:
            logger.info(
                "Executing tool",
                tool_name=tc.function_name,
                call_id=tc.call_id,
                arguments=tc.arguments
            )

            result = await tool.execute(tc.arguments, context)

            logger.info(
                "Tool execution completed",
                tool_name=tc.function_name,
                call_id=tc.call_id,
                success=result.success
            )

            return self._format_tool_response(tc.call_id, tc.function_name, result)

        except Exception as e:
            logger.error(
                "Tool execution failed with exception",
                tool_name=tc.function_name,
                call_id=tc.call_id,
                error=str(e)
            )

            error_result = ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}"
            )
            return self._format_tool_response(tc.call_id, tc.function_name, error_result)

    async def execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute multiple tool calls.

        Args:
            tool_calls: List of tool call objects from LLM
            context: Execution context

        Returns:
            List of tool responses in OpenRouter format
        """
        # Add tool_executor to context so tools can access it
        context_with_executor = {**context, "tool_executor": self}
        
        results = []

        for tool_call in tool_calls:
            result = await self.execute_tool_call(tool_call, context_with_executor)
            results.append(result)

        return results

    def _format_tool_response(
        self,
        call_id: str,
        tool_name: str,
        result: ToolResult
    ) -> Dict[str, Any]:
        """Format tool result for LLM consumption.

        Args:
            call_id: Tool call ID
            tool_name: Name of the tool
            result: Tool execution result

        Returns:
            OpenRouter tool response format:
            {
                "role": "tool",
                "tool_call_id": "call_abc123",
                "content": "JSON string with result"
            }
        """
        # Format the content as JSON string
        content = json.dumps({
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "message": result.message
        })

        # OpenRouter expects: role, tool_call_id, content (no "name" field)
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": content
        }

    def get_tool_definitions(self) -> List[Dict]:
        """Get all tool definitions for LLM function calling.

        Returns:
            List of tool definitions in OpenRouter format
        """
        return self.registry.get_tool_definitions()
