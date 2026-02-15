# REVIEW:
# - Tool execution returns raw provider output without normalization; error handling is inconsistent with other agents.
from typing import Any, Dict, List
from src.agents.base import Agent, AgentConfig
from src.mcp.registry import MCPRegistry
import asyncio
import structlog

logger = structlog.get_logger()


class MCPAgent(Agent):
    """Agent that can use MCP tools"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.mcp_providers = config.metadata.get("mcp_providers", ["filesystem"])
    
    async def execute(self, task: Dict[str, Any]) -> Any:
        """Execute task using MCP tools"""
        logger.info(
            f"MCP Agent {self.id} executing task",
            task_type=task.get("type"),
            agent_name=self.config.name
        )
        
        # Get MCP tool to use
        tool_name = task.get("tool")
        provider_name = task.get("provider", "filesystem")
        parameters = task.get("parameters", {})
        
        if not tool_name:
            return {
                "status": "error",
                "error": "No tool specified in task"
            }
        
        # Get provider
        provider = MCPRegistry.get_provider(provider_name)
        if not provider:
            return {
                "status": "error",
                "error": f"Provider {provider_name} not found"
            }
        
        # Check if tool exists
        tool = provider.get_tool(tool_name)
        if not tool:
            return {
                "status": "error",
                "error": f"Tool {tool_name} not found in provider {provider_name}"
            }
        
        try:
            # Execute tool
            result = await provider.execute_tool(tool_name, parameters)
            
            logger.info(
                f"MCP Agent {self.id} completed tool execution",
                tool=tool_name,
                provider=provider_name
            )
            
            return {
                "status": "completed",
                "tool": tool_name,
                "provider": provider_name,
                "result": result
            }
            
        except Exception as e:
            logger.error(
                f"MCP Agent {self.id} tool execution failed",
                tool=tool_name,
                error=str(e)
            )
            
            return {
                "status": "error",
                "error": str(e),
                "tool": tool_name,
                "provider": provider_name
            }
