"""
Tests for UnifiedCapabilityRegistry

Tests the single source of truth for all capabilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.capabilities.unified_registry import (
    UnifiedCapabilityRegistry,
    ResolvedCapability,
    CapabilityType,
    get_registry,
    reset_registry,
)


class TestCapabilityType:
    """Tests for CapabilityType enum."""

    def test_agent_type(self):
        assert CapabilityType.AGENT == "agent"

    def test_primitive_type(self):
        assert CapabilityType.PRIMITIVE == "primitive"

    def test_plugin_type(self):
        assert CapabilityType.PLUGIN == "plugin"


class TestResolvedCapability:
    """Tests for ResolvedCapability dataclass."""

    def test_is_deterministic_primitive(self):
        """Primitives should be deterministic."""
        resolved = ResolvedCapability(
            name="json.parse",
            capability_type=CapabilityType.PRIMITIVE,
            config=MagicMock(),
        )
        assert resolved.is_deterministic is True

    def test_is_deterministic_plugin(self):
        """Plugins should be deterministic."""
        resolved = ResolvedCapability(
            name="den.upload",
            capability_type=CapabilityType.PLUGIN,
            config=MagicMock(),
        )
        assert resolved.is_deterministic is True

    def test_is_deterministic_agent(self):
        """Agents should not be deterministic (LLM-powered)."""
        resolved = ResolvedCapability(
            name="summarize",
            capability_type=CapabilityType.AGENT,
            config=MagicMock(),
        )
        assert resolved.is_deterministic is False

    def test_execution_hints_with_hints(self):
        """Should return execution hints from config."""
        config = MagicMock()
        config.execution_hints = {"speed": "fast", "cost": "low"}

        resolved = ResolvedCapability(
            name="test",
            capability_type=CapabilityType.AGENT,
            config=config,
        )

        assert resolved.execution_hints == {"speed": "fast", "cost": "low"}

    def test_execution_hints_without_hints(self):
        """Should return empty dict when no hints."""
        config = MagicMock()
        config.execution_hints = None

        resolved = ResolvedCapability(
            name="test",
            capability_type=CapabilityType.AGENT,
            config=config,
        )

        assert resolved.execution_hints == {}


class TestUnifiedCapabilityRegistry:
    """Tests for UnifiedCapabilityRegistry class."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_session = MagicMock()
        return db

    @pytest.fixture
    def registry(self, mock_db):
        """Create a registry instance with mock db."""
        return UnifiedCapabilityRegistry(db=mock_db)

    def test_init(self, registry, mock_db):
        """Test initialization."""
        assert registry._db == mock_db
        assert registry._owns_db is False
        assert registry._initialized is False
        assert registry._agent_cache == {}
        assert registry._primitive_cache == {}
        assert registry._plugin_cache == {}

    def test_list_agents_empty(self, registry):
        """Test listing agents when cache is empty."""
        assert registry.list_agents() == []

    def test_list_primitives_empty(self, registry):
        """Test listing primitives when cache is empty."""
        assert registry.list_primitives() == []

    def test_list_plugins_empty(self, registry):
        """Test listing plugins when cache is empty."""
        assert registry.list_plugins() == []

    def test_available_types(self, registry):
        """Test available_types returns agent types."""
        # Add some agents to cache
        mock_agent = MagicMock()
        mock_agent.agent_type = "summarize"
        registry._agent_cache["summarize"] = mock_agent

        assert "summarize" in registry.available_types()

    def test_get_agent_config(self, registry):
        """Test getting agent config by type."""
        mock_agent = MagicMock()
        registry._agent_cache["summarize"] = mock_agent

        assert registry.get_agent_config("summarize") == mock_agent
        assert registry.get_agent_config("nonexistent") is None

    def test_get_primitive(self, registry):
        """Test getting primitive by name."""
        mock_primitive = MagicMock()
        registry._primitive_cache["json.parse"] = mock_primitive

        assert registry.get_primitive("json.parse") == mock_primitive
        assert registry.get_primitive("nonexistent") is None

    def test_get_plugin(self, registry):
        """Test getting plugin by namespace."""
        mock_plugin = MagicMock()
        registry._plugin_cache["den"] = mock_plugin

        assert registry.get_plugin("den") == mock_plugin
        assert registry.get_plugin("nonexistent") is None


class TestRegistryResolution:
    """Tests for capability resolution."""

    @pytest.fixture
    def registry(self):
        """Create a registry with populated caches."""
        registry = UnifiedCapabilityRegistry(db=MagicMock())
        registry._initialized = True

        # Add mock agent
        mock_agent = MagicMock()
        mock_agent.organization_id = None
        mock_agent.is_system = True
        registry._agent_cache["summarize"] = mock_agent

        # Add mock primitive
        mock_primitive = MagicMock()
        registry._primitive_cache["json.parse"] = mock_primitive

        # Add mock plugin
        mock_plugin = MagicMock()
        mock_plugin.organization_id = None
        registry._plugin_cache["den"] = mock_plugin

        return registry

    @pytest.mark.asyncio
    async def test_resolve_agent(self, registry):
        """Test resolving an agent."""
        resolved = await registry.resolve("summarize")

        assert resolved is not None
        assert resolved.name == "summarize"
        assert resolved.capability_type == CapabilityType.AGENT

    @pytest.mark.asyncio
    async def test_resolve_primitive(self, registry):
        """Test resolving a primitive."""
        resolved = await registry.resolve("json.parse")

        assert resolved is not None
        assert resolved.name == "json.parse"
        assert resolved.capability_type == CapabilityType.PRIMITIVE

    @pytest.mark.asyncio
    async def test_resolve_plugin_namespace(self, registry):
        """Test resolving a plugin by namespace."""
        resolved = await registry.resolve("den")

        assert resolved is not None
        assert resolved.name == "den"
        assert resolved.capability_type == CapabilityType.PLUGIN

    @pytest.mark.asyncio
    async def test_resolve_plugin_operation(self, registry):
        """Test resolving a namespaced plugin operation."""
        resolved = await registry.resolve("den.upload")

        assert resolved is not None
        assert resolved.name == "den.upload"
        assert resolved.capability_type == CapabilityType.PLUGIN

    @pytest.mark.asyncio
    async def test_resolve_explicit_type(self, registry):
        """Test resolving with explicit type."""
        resolved = await registry.resolve("summarize", capability_type="agent")

        assert resolved is not None
        assert resolved.capability_type == CapabilityType.AGENT

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, registry):
        """Test resolving non-existent capability."""
        resolved = await registry.resolve("nonexistent")

        assert resolved is None

    @pytest.mark.asyncio
    async def test_resolve_any(self, registry):
        """Test resolve_any convenience method."""
        cap_type, config = await registry.resolve_any("summarize")

        assert cap_type == CapabilityType.AGENT
        assert config is not None


class TestGlobalRegistry:
    """Tests for global registry functions."""

    @pytest.mark.asyncio
    async def test_reset_registry(self):
        """Test resetting the global registry."""
        await reset_registry()

        # After reset, global should be None
        from src.capabilities.unified_registry import _registry
        # Can't directly check _registry since it's module-level
        # But calling get_registry should create a new one
