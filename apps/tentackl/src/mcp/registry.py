import json
from pathlib import Path
from typing import Dict, List, Optional, Type
from src.mcp.base import MCPProvider
from src.mcp.filesystem_provider import FileSystemProvider
from src.core.config import settings
import structlog

logger = structlog.get_logger()


class MCPRegistry:
    """Registry for MCP providers"""
    
    _providers: Dict[str, MCPProvider] = {}
    _provider_classes: Dict[str, Type[MCPProvider]] = {
        "filesystem": FileSystemProvider
    }
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize MCP registry from configuration"""
        if not settings.MCP_ENABLED:
            logger.info("MCP is disabled")
            return
        
        # Load registry configuration
        registry_path = Path(settings.MCP_REGISTRY_PATH)
        
        if registry_path.exists():
            with open(registry_path) as f:
                config = json.load(f)
        else:
            # Default configuration
            config = {
                "providers": [
                    {
                        "name": "filesystem",
                        "type": "filesystem",
                        "config": {
                            "base_path": "/tmp/tentackl/mcp"
                        }
                    }
                ]
            }
        
        # Initialize providers
        for provider_config in config.get("providers", []):
            await cls.register_provider(provider_config)
        
        logger.info(f"MCP registry initialized", providers=list(cls._providers.keys()))
    
    @classmethod
    async def register_provider(cls, provider_config: Dict) -> None:
        """Register a provider"""
        provider_type = provider_config["type"]
        provider_name = provider_config["name"]
        
        if provider_type not in cls._provider_classes:
            logger.error(f"Unknown provider type: {provider_type}")
            return
        
        # Create provider instance
        provider_class = cls._provider_classes[provider_type]
        provider = provider_class(provider_config.get("config", {}))
        
        # Initialize provider
        await provider.initialize()
        
        # Register
        cls._providers[provider_name] = provider
        logger.info(f"Registered MCP provider", name=provider_name, type=provider_type)
    
    @classmethod
    def get_provider(cls, name: str) -> Optional[MCPProvider]:
        """Get a provider by name"""
        return cls._providers.get(name)
    
    @classmethod
    def get_all_providers(cls) -> List[MCPProvider]:
        """Get all registered providers"""
        return list(cls._providers.values())
    
    @classmethod
    def get_all_tools(cls) -> Dict[str, List[Dict]]:
        """Get all tools from all providers"""
        tools_by_provider = {}
        
        for name, provider in cls._providers.items():
            tools = []
            for tool in provider.get_tools():
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "parameters": [p.dict() for p in tool.parameters]
                })
            tools_by_provider[name] = tools
        
        return tools_by_provider