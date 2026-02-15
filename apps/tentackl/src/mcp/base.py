from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class MCPToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class MCPTool(BaseModel):
    name: str
    description: str
    parameters: List[MCPToolParameter]
    category: str = "general"


class MCPProvider(ABC):
    """Base class for MCP (Model Context Protocol) providers"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._tools: Dict[str, MCPTool] = {}
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the MCP provider"""
        pass
    
    @abstractmethod
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool with given parameters"""
        pass
    
    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool with this provider"""
        self._tools[tool.name] = tool
        logger.info(f"Registered MCP tool", provider=self.name, tool=tool.name)
    
    def get_tools(self) -> List[MCPTool]:
        """Get all available tools"""
        return list(self._tools.values())
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a specific tool by name"""
        return self._tools.get(name)