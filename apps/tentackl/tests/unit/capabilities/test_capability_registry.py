"""
Unit tests for CapabilityRegistry
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.capabilities.capability_registry import (
    CapabilityRegistry,
    ToolDefinition,
    AgentCapability
)
from src.interfaces.configurable_agent import CapabilityConfig
from src.interfaces.agent import AgentInterface
from src.core.exceptions import (
    CapabilityNotFoundError,
    CapabilityBindingError
)


@pytest.fixture
def registry():
    """Create a capability registry"""
    return CapabilityRegistry()


@pytest.fixture
def custom_tool():
    """Create a custom tool definition"""
    async def custom_handler(data: str) -> str:
        return f"Processed: {data}"
    
    return ToolDefinition(
        name="custom_processor",
        description="Custom data processor",
        handler=custom_handler,
        config_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
                "options": {"type": "object"}
            }
        },
        permissions_required=["custom:process"],
        sandboxable=True,
        category=AgentCapability.CUSTOM
    )


@pytest.fixture
def mock_agent():
    """Create a mock agent"""
    agent = MagicMock(spec=AgentInterface)
    agent.agent_id = "test-agent-123"
    agent._capabilities = {}
    return agent


class TestCapabilityRegistry:
    """Test CapabilityRegistry functionality"""
    
    def test_builtin_capabilities_registered(self, registry):
        """Test that built-in capabilities are registered"""
        tools = registry._tools
        
        # Check core capabilities are registered
        assert "file_read" in tools
        assert "file_write" in tools
        assert "api_call" in tools
        assert "data_transform" in tools
        assert "validator" in tools
        assert "cache" in tools
        
        # Check tool properties
        file_read = tools["file_read"]
        assert file_read.category == AgentCapability.FILE_READ
        assert file_read.permissions_required == ["filesystem:read"]
        assert file_read.sandboxable is True
    
    def test_register_custom_tool(self, registry, custom_tool):
        """Test registering a custom tool"""
        registry.register_tool(custom_tool)
        
        assert "custom_processor" in registry._tools
        assert registry._tools["custom_processor"] == custom_tool
    
    def test_register_tool_overwrite(self, registry, custom_tool):
        """Test overwriting an existing tool"""
        # Register once
        registry.register_tool(custom_tool)
        
        # Create modified version
        modified_tool = ToolDefinition(
            name="custom_processor",
            description="Modified processor",
            handler=lambda x: x,
            category=AgentCapability.DATA_TRANSFORM
        )
        
        # Register again (should overwrite)
        registry.register_tool(modified_tool)
        
        assert registry._tools["custom_processor"].description == "Modified processor"
        assert registry._tools["custom_processor"].category == AgentCapability.DATA_TRANSFORM
    
    async def test_bind_capability_success(self, registry, mock_agent):
        """Test successful capability binding"""
        capability = CapabilityConfig(
            tool="file_read",
            config={"formats": ["txt", "json"], "max_size_mb": 10},
            permissions={"filesystem": ["read"]},
            sandbox=True
        )
        
        await registry.bind_capability(mock_agent, capability)
        
        # Check binding was stored
        assert mock_agent.agent_id in registry._bindings
        assert "file_read" in registry._bindings[mock_agent.agent_id]
        
        binding = registry._bindings[mock_agent.agent_id]["file_read"]
        assert binding["config"] == capability.config
        assert binding["sandbox"] is True
        assert binding["permissions"] == capability.permissions
        
        # Check capability was injected into agent
        assert "file_read" in mock_agent._capabilities
    
    async def test_bind_nonexistent_capability(self, registry, mock_agent):
        """Test binding non-existent capability"""
        capability = CapabilityConfig(
            tool="nonexistent_tool",
            config={}
        )
        
        with pytest.raises(CapabilityNotFoundError) as exc_info:
            await registry.bind_capability(mock_agent, capability)
        
        assert "not found in registry" in str(exc_info.value)
    
    async def test_bind_capability_insufficient_permissions(self, registry, mock_agent):
        """Test binding with insufficient permissions"""
        capability = CapabilityConfig(
            tool="file_write",
            config={},
            permissions={"filesystem": ["read"]},  # Need write permission
            sandbox=True
        )
        
        with pytest.raises(CapabilityBindingError) as exc_info:
            await registry.bind_capability(mock_agent, capability)
        
        assert "Insufficient permissions" in str(exc_info.value)
    
    async def test_validate_capability_valid(self, registry):
        """Test validating a valid capability"""
        capability = CapabilityConfig(
            tool="data_transform",
            config={
                "operations": ["filter", "map"],
                "memory_limit_mb": 512
            }
        )
        
        result = await registry.validate_capability(capability)
        assert result is True
    
    async def test_validate_capability_invalid_tool(self, registry):
        """Test validating capability with invalid tool"""
        capability = CapabilityConfig(
            tool="invalid_tool",
            config={}
        )
        
        result = await registry.validate_capability(capability)
        assert result is False
    
    async def test_validate_capability_unsandboxable(self, registry):
        """Test validating unsandboxable capability"""
        # Register an unsandboxable tool
        unsandboxable = ToolDefinition(
            name="system_tool",
            description="System level tool",
            handler=lambda: None,
            sandboxable=False
        )
        registry.register_tool(unsandboxable)
        
        capability = CapabilityConfig(
            tool="system_tool",
            config={},
            sandbox=True  # Try to sandbox unsandboxable tool
        )
        
        result = await registry.validate_capability(capability)
        assert result is False
    
    async def test_get_available_tools(self, registry, custom_tool):
        """Test getting list of available tools"""
        # Add custom tool
        registry.register_tool(custom_tool)
        
        tools = await registry.get_available_tools()
        
        assert isinstance(tools, list)
        assert "file_read" in tools
        assert "file_write" in tools
        assert "custom_processor" in tools
    
    def test_get_tool_definition(self, registry, custom_tool):
        """Test getting tool definition by name"""
        registry.register_tool(custom_tool)
        
        # Get existing tool
        tool_def = registry.get_tool_definition("custom_processor")
        assert tool_def == custom_tool
        
        # Get non-existent tool
        tool_def = registry.get_tool_definition("nonexistent")
        assert tool_def is None
    
    def test_get_tools_by_category(self, registry, custom_tool):
        """Test getting tools by category"""
        registry.register_tool(custom_tool)
        
        # Get file operations
        file_tools = registry.get_tools_by_category(AgentCapability.FILE_READ)
        assert len(file_tools) >= 1
        assert all(t.category == AgentCapability.FILE_READ for t in file_tools)
        
        # Get custom tools
        custom_tools = registry.get_tools_by_category(AgentCapability.CUSTOM)
        assert len(custom_tools) >= 1
        assert any(t.name == "custom_processor" for t in custom_tools)
    
    async def test_unbind_capability(self, registry, mock_agent):
        """Test unbinding a capability"""
        # First bind a capability
        capability = CapabilityConfig(
            tool="cache",
            config={"ttl_seconds": 3600}
        )
        await registry.bind_capability(mock_agent, capability)
        
        # Verify it's bound
        assert "cache" in registry._bindings[mock_agent.agent_id]
        
        # Unbind it
        await registry.unbind_capability(mock_agent.agent_id, "cache")
        
        # Verify it's unbound
        assert mock_agent.agent_id not in registry._bindings
    
    async def test_unbind_all_capabilities(self, registry, mock_agent):
        """Test unbinding all capabilities from an agent"""
        # Bind multiple capabilities
        capabilities = [
            CapabilityConfig(tool="file_read", config={}),
            CapabilityConfig(tool="cache", config={}),
            CapabilityConfig(tool="validator", config={})
        ]
        
        for cap in capabilities:
            await registry.bind_capability(mock_agent, cap)
        
        # Verify all are bound
        assert len(registry._bindings[mock_agent.agent_id]) == 3
        
        # Unbind all
        await registry.unbind_all(mock_agent.agent_id)
        
        # Verify all are unbound
        assert mock_agent.agent_id not in registry._bindings
    
    def test_check_permissions_simple(self, registry):
        """Test simple permission checking"""
        # Test with granted permissions
        granted = {"filesystem": ["read", "write"], "network": True}
        required = ["filesystem:read", "network"]
        assert registry._check_permissions(granted, required) is True
        
        # Test with missing permissions
        granted = {"filesystem": ["read"]}
        required = ["filesystem:write"]
        assert registry._check_permissions(granted, required) is False
        
        # Test with boolean permissions
        granted = {"admin": False}
        required = ["admin"]
        assert registry._check_permissions(granted, required) is False
    
    async def test_file_handlers(self, registry):
        """Test built-in file handlers"""
        # Test file read
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        
        try:
            content = await registry._file_read_handler(temp_path)
            assert content == "Test content"
        finally:
            Path(temp_path).unlink()
        
        # Test file write
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            await registry._file_write_handler(temp_path, "New content")
            with open(temp_path, 'r') as f:
                assert f.read() == "New content"
            
            # Test append mode
            await registry._file_write_handler(temp_path, " Appended", append=True)
            with open(temp_path, 'r') as f:
                assert f.read() == "New content Appended"
        finally:
            Path(temp_path).unlink()
    
    async def test_data_transform_handler(self, registry):
        """Test built-in data transformation handler"""
        # Test filter operation
        data = [1, 2, 3, 4, 5]
        operations = [
            {"type": "filter", "condition": "x > 2"}
        ]
        result = await registry._data_transform_handler(data, operations)
        assert result == [3, 4, 5]
        
        # Test map operation
        data = [1, 2, 3]
        operations = [
            {"type": "map", "expression": "x * 2"}
        ]
        result = await registry._data_transform_handler(data, operations)
        assert result == [2, 4, 6]
        
        # Test aggregate operation
        data = [1, 2, 3, 4, 5]
        operations = [
            {"type": "aggregate", "function": "sum"}
        ]
        result = await registry._data_transform_handler(data, operations)
        assert result == 15
    
    async def test_validator_handler(self, registry):
        """Test built-in validation handler"""
        data = {
            "name": "John",
            "age": 25,
            "email": "john@example.com"
        }
        
        rules = [
            {"type": "required", "field": "name"},
            {"type": "required", "field": "phone"},  # Missing field
            {"type": "type", "field": "age", "expected": "int"},
            {"type": "type", "field": "email", "expected": "str"}
        ]
        
        result = await registry._validator_handler(data, rules)
        
        assert result["valid"] is False
        assert "Required field 'phone' is missing" in result["errors"]
        assert result["data"] is None  # Invalid data
    
    async def test_cache_handler(self, registry):
        """Test built-in caching handler"""
        # Test set and get
        await registry._cache_handler("key1", "value1", ttl=60)
        value = await registry._cache_handler("key1")
        assert value == "value1"
        
        # Test get non-existent key
        value = await registry._cache_handler("nonexistent")
        assert value is None
        
        # Test expiration
        await registry._cache_handler("key2", "value2", ttl=0.1)
        await asyncio.sleep(0.2)
        value = await registry._cache_handler("key2")
        assert value is None
    
    async def test_discover_plugins(self, registry):
        """Test plugin discovery"""
        # Create a temporary plugin directory
        with tempfile.TemporaryDirectory() as plugin_dir:
            # Create a plugin module
            plugin_path = Path(plugin_dir) / "test_plugin.py"
            plugin_path.write_text("""
from src.capabilities.capability_registry import ToolDefinition
from src.interfaces.configurable_agent import AgentCapability

def plugin_handler(data):
    return f"Plugin processed: {data}"

CAPABILITIES = [
    ToolDefinition(
        name="plugin_tool",
        description="Plugin tool",
        handler=plugin_handler,
        category=AgentCapability.CUSTOM
    )
]
""")
            
            # Discover plugins
            loaded = await registry.discover_plugins(plugin_dir)
            
            assert "plugin_tool" in loaded
            assert "plugin_tool" in registry._tools
            assert registry._tools["plugin_tool"].description == "Plugin tool"
    
    async def test_discover_plugins_with_registration_function(self, registry):
        """Test plugin discovery with registration function"""
        with tempfile.TemporaryDirectory() as plugin_dir:
            # Create a plugin with registration function
            plugin_path = Path(plugin_dir) / "advanced_plugin.py"
            plugin_path.write_text("""
from src.capabilities.capability_registry import ToolDefinition
from src.interfaces.configurable_agent import AgentCapability

def register_capabilities():
    return [
        ToolDefinition(
            name="advanced_tool1",
            description="Advanced tool 1",
            handler=lambda x: x,
            category=AgentCapability.CUSTOM
        ),
        ToolDefinition(
            name="advanced_tool2",
            description="Advanced tool 2",
            handler=lambda x: x * 2,
            category=AgentCapability.CUSTOM
        )
    ]
""")
            
            loaded = await registry.discover_plugins(plugin_dir)
            
            assert "advanced_tool1" in loaded
            assert "advanced_tool2" in loaded
            assert len(loaded) == 2
    
    async def test_discover_plugins_error_handling(self, registry):
        """Test plugin discovery error handling"""
        with tempfile.TemporaryDirectory() as plugin_dir:
            # Create a plugin with syntax error
            plugin_path = Path(plugin_dir) / "bad_plugin.py"
            plugin_path.write_text("""
# Invalid Python syntax
def bad_function(
""")
            
            # Should handle error gracefully
            loaded = await registry.discover_plugins(plugin_dir)
            assert len(loaded) == 0  # No plugins loaded due to error
    
    async def test_create_tool_instance_class_based(self, registry):
        """Test creating instance of class-based tool"""
        class CustomTool:
            def __init__(self, prefix="Custom"):
                self.prefix = prefix
            
            async def process(self, data):
                return f"{self.prefix}: {data}"
        
        tool_def = ToolDefinition(
            name="class_tool",
            description="Class-based tool",
            handler=CustomTool
        )
        
        instance = await registry._create_tool_instance(
            tool_def,
            {"prefix": "Modified"}
        )
        
        assert isinstance(instance, CustomTool)
        assert instance.prefix == "Modified"
    
    async def test_create_tool_instance_factory(self, registry):
        """Test creating instance with factory function"""
        def tool_factory(config):
            multiplier = config.get("multiplier", 1)
            return lambda x: x * multiplier
        
        tool_def = ToolDefinition(
            name="factory_tool",
            description="Factory-based tool",
            handler=tool_factory
        )
        
        instance = await registry._create_tool_instance(
            tool_def,
            {"multiplier": 3}
        )
        
        assert callable(instance)
        assert instance(5) == 15
    
    async def test_concurrent_binding(self, registry):
        """Test concurrent capability binding"""
        # Create multiple agents
        agents = []
        for i in range(5):
            agent = MagicMock(spec=AgentInterface)
            agent.agent_id = f"agent-{i}"
            agent._capabilities = {}
            agents.append(agent)
        
        # Bind capabilities concurrently
        tasks = []
        for agent in agents:
            capability = CapabilityConfig(
                tool="cache",
                config={"ttl_seconds": 3600}
            )
            tasks.append(registry.bind_capability(agent, capability))
        
        await asyncio.gather(*tasks)
        
        # Verify all bindings were created
        assert len(registry._bindings) == 5
        for agent in agents:
            assert agent.agent_id in registry._bindings
