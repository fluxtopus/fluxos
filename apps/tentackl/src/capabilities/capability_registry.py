"""
Capability Registry

This module implements the registry for managing available tools and capabilities
that can be bound to configurable agents.
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable, Type
from dataclasses import dataclass
import inspect
import importlib
import pkgutil
from pathlib import Path

from ..interfaces.configurable_agent import (
    CapabilityBinderInterface,
    CapabilityConfig,
    AgentCapability
)
from ..interfaces.agent import AgentInterface
from ..core.exceptions import (
    CapabilityNotFoundError,
    CapabilityBindingError
)
from ..core.safe_eval import safe_eval
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ToolDefinition:
    """Definition of a tool/capability"""
    name: str
    description: str
    handler: Callable
    config_schema: Optional[Dict[str, Any]] = None
    permissions_required: Optional[List[str]] = None
    sandboxable: bool = True
    category: AgentCapability = AgentCapability.CUSTOM


class CapabilityRegistry(CapabilityBinderInterface):
    """Registry for agent capabilities and tools"""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._tool_instances: Dict[str, Any] = {}
        self._bindings: Dict[str, Dict[str, Any]] = {}  # agent_id -> tool -> instance
        self._lock = asyncio.Lock()
        
        # Register built-in capabilities
        self._register_builtin_capabilities()
    
    def _register_builtin_capabilities(self) -> None:
        """Register built-in capabilities"""
        # File operations
        self.register_tool(ToolDefinition(
            name="file_read",
            description="Read files from the filesystem",
            handler=self._file_read_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "formats": {"type": "array", "items": {"type": "string"}},
                    "max_size_mb": {"type": "number"}
                }
            },
            permissions_required=["filesystem:read"],
            category=AgentCapability.FILE_READ
        ))
        
        self.register_tool(ToolDefinition(
            name="file_write",
            description="Write files to the filesystem",
            handler=self._file_write_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "formats": {"type": "array", "items": {"type": "string"}},
                    "max_size_mb": {"type": "number"},
                    "append_mode": {"type": "boolean"}
                }
            },
            permissions_required=["filesystem:write"],
            category=AgentCapability.FILE_WRITE
        ))
        
        # API operations
        self.register_tool(ToolDefinition(
            name="api_call",
            description="Make HTTP API calls",
            handler=self._api_call_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "allowed_hosts": {"type": "array", "items": {"type": "string"}},
                    "timeout": {"type": "number"},
                    "max_retries": {"type": "integer"}
                }
            },
            permissions_required=["network:http"],
            category=AgentCapability.API_CALL
        ))
        
        # Data transformation
        self.register_tool(ToolDefinition(
            name="data_transform",
            description="Transform and process data",
            handler=self._data_transform_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "operations": {"type": "array", "items": {"type": "string"}},
                    "memory_limit_mb": {"type": "number"}
                }
            },
            category=AgentCapability.DATA_TRANSFORM
        ))
        
        # Validation
        self.register_tool(ToolDefinition(
            name="validator",
            description="Validate data against schemas and rules",
            handler=self._validator_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "rules": {"type": "array"},
                    "schemas": {"type": "object"}
                }
            },
            category=AgentCapability.VALIDATION
        ))
        
        # Caching
        self.register_tool(ToolDefinition(
            name="cache",
            description="Cache results for performance",
            handler=self._cache_handler,
            config_schema={
                "type": "object",
                "properties": {
                    "ttl_seconds": {"type": "integer"},
                    "max_entries": {"type": "integer"},
                    "eviction_policy": {"type": "string"}
                }
            },
            category=AgentCapability.CACHING
        ))
        
        # Browser automation (if browser-use is available)
        try:
            from .browser_use_capability import BROWSER_USE_CAPABILITY
            self.register_tool(BROWSER_USE_CAPABILITY)
            logger.info("Browser-use capability registered")
        except ImportError:
            logger.warning("Browser-use not available, skipping browser capability")
        
        # Shell command execution
        try:
            from .shell_capability import SHELL_CAPABILITY
            self.register_tool(SHELL_CAPABILITY)
            logger.info("Shell capability registered")
        except ImportError as e:
            logger.debug("Shell capability not available", error=str(e))
        
        # Database operations
        try:
            from .database_capability import DATABASE_CAPABILITY
            self.register_tool(DATABASE_CAPABILITY)
            logger.info("Database capability registered")
        except ImportError as e:
            logger.debug("Database capability not available", error=str(e))
        
        # Document readers
        try:
            from .document_reader_capability import LOCAL_DOCUMENT_READER_CAPABILITY
            self.register_tool(LOCAL_DOCUMENT_READER_CAPABILITY)
            logger.info("Local document reader capability registered")
        except ImportError as e:
            logger.debug("Document reader capability not available", error=str(e))
        
        logger.info(
            "Built-in capabilities registered",
            count=len(self._tools)
        )
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a new tool"""
        if tool.name in self._tools:
            logger.warning(
                "Tool already registered, overwriting",
                tool=tool.name
            )
        
        self._tools[tool.name] = tool
        logger.info(
            "Tool registered",
            name=tool.name,
            category=tool.category.value
        )
    
    async def bind_capability(
        self,
        agent: AgentInterface,
        capability: CapabilityConfig
    ) -> None:
        """Bind a capability to an agent"""
        try:
            async with self._lock:
                # Validate capability exists
                if capability.tool not in self._tools:
                    raise CapabilityNotFoundError(
                        f"Tool '{capability.tool}' not found in registry"
                    )
                
                tool_def = self._tools[capability.tool]
                
                # Check permissions if sandboxed
                if capability.sandbox:
                    if not self._check_permissions(
                        capability.permissions or {},
                        tool_def.permissions_required or []
                    ):
                        raise CapabilityBindingError(
                            f"Insufficient permissions for tool '{capability.tool}'"
                        )
                
                # Create tool instance
                tool_instance = await self._create_tool_instance(
                    tool_def,
                    capability.config
                )
                
                # Store binding
                agent_id = getattr(agent, 'agent_id', str(id(agent)))
                if agent_id not in self._bindings:
                    self._bindings[agent_id] = {}
                
                self._bindings[agent_id][capability.tool] = {
                    "instance": tool_instance,
                    "config": capability.config,
                    "sandbox": capability.sandbox,
                    "permissions": capability.permissions
                }
                
                # Inject capability into agent if it has a method for it
                if hasattr(agent, '_capabilities') and isinstance(agent._capabilities, dict):
                    agent._capabilities[capability.tool] = tool_instance
                
                logger.info(
                    "Capability bound to agent",
                    agent_id=agent_id,
                    tool=capability.tool,
                    sandbox=capability.sandbox
                )
                
        except Exception as e:
            logger.error(
                "Failed to bind capability",
                error=str(e),
                tool=capability.tool
            )
            raise
    
    async def validate_capability(
        self,
        capability: CapabilityConfig
    ) -> bool:
        """Validate that a capability can be bound"""
        try:
            # Check if tool exists
            if capability.tool not in self._tools:
                return False
            
            tool_def = self._tools[capability.tool]
            
            # Validate config against schema
            if tool_def.config_schema and capability.config:
                # Simple validation - in production would use jsonschema
                required_keys = [
                    prop for prop, schema in tool_def.config_schema.get("properties", {}).items()
                    if schema.get("required", False)
                ]
                for key in required_keys:
                    if key not in capability.config:
                        return False
            
            # Check if tool can be sandboxed
            if capability.sandbox and not tool_def.sandboxable:
                return False
            
            return True
            
        except Exception as e:
            logger.error(
                "Capability validation failed",
                error=str(e),
                tool=capability.tool
            )
            return False
    
    async def get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        return list(self._tools.keys())
    
    def get_tool_definition(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name"""
        return self._tools.get(tool_name)
    
    def get_tools_by_category(
        self,
        category: AgentCapability
    ) -> List[ToolDefinition]:
        """Get tools by category"""
        return [
            tool for tool in self._tools.values()
            if tool.category == category
        ]
    
    async def unbind_capability(
        self,
        agent_id: str,
        tool_name: str
    ) -> None:
        """Unbind a capability from an agent"""
        async with self._lock:
            if agent_id in self._bindings and tool_name in self._bindings[agent_id]:
                # Cleanup tool instance if needed
                tool_instance = self._bindings[agent_id][tool_name]["instance"]
                if hasattr(tool_instance, 'cleanup'):
                    await tool_instance.cleanup()
                
                del self._bindings[agent_id][tool_name]
                
                if not self._bindings[agent_id]:
                    del self._bindings[agent_id]
                
                logger.info(
                    "Capability unbound",
                    agent_id=agent_id,
                    tool=tool_name
                )
    
    async def unbind_all(
        self,
        agent_id: str
    ) -> None:
        """Unbind all capabilities from an agent"""
        if agent_id in self._bindings:
            tools = list(self._bindings[agent_id].keys())
            for tool_name in tools:
                await self.unbind_capability(agent_id, tool_name)
    
    def _check_permissions(
        self,
        granted: Dict[str, Any],
        required: List[str]
    ) -> bool:
        """Check if granted permissions satisfy requirements"""
        for req in required:
            # Simple permission check - can be enhanced
            if ":" in req:
                category, action = req.split(":", 1)
                if category not in granted:
                    return False
                if isinstance(granted[category], list) and action not in granted[category]:
                    return False
                elif isinstance(granted[category], bool) and not granted[category]:
                    return False
            else:
                if req not in granted or not granted[req]:
                    return False
        
        return True
    
    async def _create_tool_instance(
        self,
        tool_def: ToolDefinition,
        config: Dict[str, Any]
    ) -> Any:
        """Create an instance of a tool"""
        # For built-in tools, return the handler
        if inspect.iscoroutinefunction(tool_def.handler):
            return tool_def.handler
        
        # For class-based tools
        if inspect.isclass(tool_def.handler):
            return tool_def.handler(**config)
        
        # For factory functions
        if callable(tool_def.handler):
            instance = tool_def.handler(config)
            if inspect.isawaitable(instance):
                return await instance
            return instance
        
        return tool_def.handler
    
    # Built-in tool handlers
    
    async def _file_read_handler(
        self,
        path: str,
        encoding: str = "utf-8"
    ) -> str:
        """Built-in file read handler"""
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error("File read failed", error=str(e), path=path)
            raise
    
    async def _file_write_handler(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        append: bool = False
    ) -> None:
        """Built-in file write handler"""
        try:
            mode = 'a' if append else 'w'
            with open(path, mode, encoding=encoding) as f:
                f.write(content)
        except Exception as e:
            logger.error("File write failed", error=str(e), path=path)
            raise
    
    async def _api_call_handler(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Built-in API call handler"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                url,
                headers=headers,
                json=data if method in ["POST", "PUT", "PATCH"] else None,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                return {
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": await response.json() if response.content_type == "application/json" else await response.text()
                }
    
    async def _data_transform_handler(
        self,
        data: Any,
        operations: List[Dict[str, Any]]
    ) -> Any:
        """Built-in data transformation handler"""
        result = data
        
        for op in operations:
            op_type = op.get("type")
            
            if op_type == "filter":
                if isinstance(result, list):
                    condition_expr = op['condition']
                    result = [
                        x for x in result
                        if safe_eval(condition_expr, names={"x": x})
                    ]

            elif op_type == "map":
                if isinstance(result, list):
                    map_expr = op['expression']
                    result = [
                        safe_eval(map_expr, names={"x": x})
                        for x in result
                    ]
            
            elif op_type == "aggregate":
                if isinstance(result, list) and op.get("function") == "sum":
                    result = sum(result)
                elif isinstance(result, list) and op.get("function") == "count":
                    result = len(result)
        
        return result
    
    async def _validator_handler(
        self,
        data: Any,
        rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Built-in validation handler"""
        errors = []
        warnings = []
        
        for rule in rules:
            rule_type = rule.get("type")
            field = rule.get("field")
            
            if rule_type == "required" and field:
                if isinstance(data, dict) and field not in data:
                    errors.append(f"Required field '{field}' is missing")
            
            elif rule_type == "type" and field:
                if isinstance(data, dict) and field in data:
                    expected_type = rule.get("expected")
                    actual_type = type(data[field]).__name__
                    if expected_type and actual_type != expected_type:
                        errors.append(
                            f"Field '{field}' has wrong type: "
                            f"expected {expected_type}, got {actual_type}"
                        )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "data": data if len(errors) == 0 else None
        }
    
    async def _cache_handler(
        self,
        key: str,
        value: Optional[Any] = None,
        ttl: int = 3600
    ) -> Any:
        """Built-in caching handler"""
        # Simple in-memory cache implementation
        if not hasattr(self, '_cache'):
            self._cache = {}
        
        if value is not None:
            # Set value
            self._cache[key] = {
                "value": value,
                "expires_at": asyncio.get_event_loop().time() + ttl
            }
            return value
        else:
            # Get value
            if key in self._cache:
                entry = self._cache[key]
                if asyncio.get_event_loop().time() < entry["expires_at"]:
                    return entry["value"]
                else:
                    del self._cache[key]
            return None
    
    async def discover_plugins(
        self,
        plugin_dir: str
    ) -> List[str]:
        """Discover and load plugin capabilities"""
        loaded = []
        plugin_path = Path(plugin_dir)
        
        if not plugin_path.exists():
            logger.warning("Plugin directory not found", path=plugin_dir)
            return loaded
        
        # Add plugin directory to Python path
        import sys
        sys.path.insert(0, str(plugin_path))
        
        try:
            # Discover plugin modules
            for finder, name, ispkg in pkgutil.iter_modules([str(plugin_path)]):
                try:
                    module = importlib.import_module(name)
                    
                    # Look for capability definitions
                    if hasattr(module, 'CAPABILITIES'):
                        for cap in module.CAPABILITIES:
                            if isinstance(cap, ToolDefinition):
                                self.register_tool(cap)
                                loaded.append(cap.name)
                    
                    # Look for registration function
                    if hasattr(module, 'register_capabilities'):
                        caps = module.register_capabilities()
                        for cap in caps:
                            if isinstance(cap, ToolDefinition):
                                self.register_tool(cap)
                                loaded.append(cap.name)
                    
                    logger.info(
                        "Plugin loaded",
                        module=name,
                        capabilities=len([c for c in loaded if c.startswith(name)])
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to load plugin",
                        module=name,
                        error=str(e)
                    )
            
        finally:
            # Remove plugin directory from path
            sys.path.remove(str(plugin_path))
        
        return loaded
