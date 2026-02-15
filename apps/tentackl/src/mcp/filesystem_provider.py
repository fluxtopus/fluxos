import os
import json
from pathlib import Path
from typing import Any, Dict, List
from src.mcp.base import MCPProvider, MCPTool, MCPToolParameter
import structlog

logger = structlog.get_logger()


class FileSystemProvider(MCPProvider):
    """MCP provider for filesystem operations"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("filesystem", config)
        self.base_path = Path(config.get("base_path", "/tmp/tentackl")).resolve()
    
    async def initialize(self) -> None:
        """Initialize filesystem provider"""
        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Register tools
        self._register_tools()
        
        logger.info(f"FileSystem provider initialized", base_path=str(self.base_path))
    
    def _register_tools(self) -> None:
        """Register filesystem tools"""
        
        # Read file tool
        self.register_tool(MCPTool(
            name="read_file",
            description="Read contents of a file",
            parameters=[
                MCPToolParameter(
                    name="path",
                    type="string",
                    description="File path relative to base directory"
                )
            ],
            category="filesystem"
        ))
        
        # Write file tool
        self.register_tool(MCPTool(
            name="write_file",
            description="Write content to a file",
            parameters=[
                MCPToolParameter(
                    name="path",
                    type="string",
                    description="File path relative to base directory"
                ),
                MCPToolParameter(
                    name="content",
                    type="string",
                    description="Content to write"
                )
            ],
            category="filesystem"
        ))
        
        # List directory tool
        self.register_tool(MCPTool(
            name="list_directory",
            description="List contents of a directory",
            parameters=[
                MCPToolParameter(
                    name="path",
                    type="string",
                    description="Directory path relative to base directory",
                    required=False,
                    default="."
                )
            ],
            category="filesystem"
        ))
        
        # Create directory tool
        self.register_tool(MCPTool(
            name="create_directory",
            description="Create a new directory",
            parameters=[
                MCPToolParameter(
                    name="path",
                    type="string",
                    description="Directory path relative to base directory"
                )
            ],
            category="filesystem"
        ))
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a filesystem tool"""
        
        if tool_name == "read_file":
            return await self._read_file(parameters["path"])
        
        elif tool_name == "write_file":
            return await self._write_file(parameters["path"], parameters["content"])
        
        elif tool_name == "list_directory":
            return await self._list_directory(parameters.get("path", "."))
        
        elif tool_name == "create_directory":
            return await self._create_directory(parameters["path"])
        
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _resolve_safe_path(self, path: str) -> Path:
        """Resolve a user path and enforce base-path confinement."""
        requested = (self.base_path / path).resolve()
        try:
            requested.relative_to(self.base_path)
        except ValueError as exc:
            raise ValueError("Path escapes configured base directory") from exc
        return requested
    
    async def _read_file(self, path: str) -> Dict[str, Any]:
        """Read file contents"""
        try:
            file_path = self._resolve_safe_path(path)
            
            if not file_path.exists():
                return {"success": False, "error": "File not found"}
            
            with open(file_path, 'r', encoding="utf-8") as f:
                content = f.read()
            
            return {"success": True, "content": content}
            
        except Exception as e:
            logger.error(f"Error reading file", path=path, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file contents"""
        try:
            file_path = self._resolve_safe_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding="utf-8") as f:
                f.write(content)
            
            return {"success": True, "path": str(file_path)}
            
        except Exception as e:
            logger.error(f"Error writing file", path=path, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _list_directory(self, path: str) -> Dict[str, Any]:
        """List directory contents"""
        try:
            dir_path = self._resolve_safe_path(path)
            
            if not dir_path.exists():
                return {"success": False, "error": "Directory not found"}
            
            items = []
            for item in dir_path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None
                })
            
            return {"success": True, "items": items}
            
        except Exception as e:
            logger.error(f"Error listing directory", path=path, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _create_directory(self, path: str) -> Dict[str, Any]:
        """Create directory"""
        try:
            dir_path = self._resolve_safe_path(path)
            dir_path.mkdir(parents=True, exist_ok=True)
            
            return {"success": True, "path": str(dir_path)}
            
        except Exception as e:
            logger.error(f"Error creating directory", path=path, error=str(e))
            return {"success": False, "error": str(e)}
