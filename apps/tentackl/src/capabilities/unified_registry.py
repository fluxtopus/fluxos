"""
Unified Capability Registry

Single source of truth for all capabilities in the system.
Resolves agents, primitives, and plugins from the database.

Resolution order:
1. User-defined agents (org-scoped)
2. System agents
3. Primitives
4. User plugins (org-scoped)
5. Builtin plugins

Usage:
    registry = UnifiedCapabilityRegistry()
    await registry.initialize()

    # Resolve a capability by name
    capability = await registry.resolve("summarize")

    # Resolve with explicit type
    capability = await registry.resolve("http.get", capability_type="primitive")

    # List all capabilities for prompt generation
    docs = await registry.list_for_planner()
"""

import structlog
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from sqlalchemy import select

from src.interfaces.database import Database
from src.database.capability_models import AgentCapability, Primitive, Plugin


logger = structlog.get_logger(__name__)


class CapabilityType(str, Enum):
    """Types of capabilities in the system."""
    AGENT = "agent"
    PRIMITIVE = "primitive"
    PLUGIN = "plugin"


@dataclass
class ResolvedCapability:
    """A resolved capability ready for execution."""
    name: str
    capability_type: CapabilityType
    config: Union[AgentCapability, Primitive, Plugin]
    organization_id: Optional[str] = None

    @property
    def is_deterministic(self) -> bool:
        """Whether this capability is deterministic (no LLM)."""
        if self.capability_type == CapabilityType.PRIMITIVE:
            return True
        if self.capability_type == CapabilityType.PLUGIN:
            return True
        # Agents are not deterministic (LLM-powered)
        return False

    @property
    def execution_hints(self) -> Dict[str, Any]:
        """Get execution hints for this capability."""
        if hasattr(self.config, 'execution_hints') and self.config.execution_hints:
            return self.config.execution_hints
        return {}


class UnifiedCapabilityRegistry:
    """
    Single source of truth for all capabilities.

    Loads capabilities from the database and provides resolution
    for both the Planner (prompt generation) and Executor (step execution).
    """

    def __init__(self, db: Optional[Database] = None):
        """
        Initialize the registry.

        Args:
            db: Optional database instance. If not provided, creates a new one.
        """
        self._db = db
        self._owns_db = False
        self._initialized = False

        # Caches for performance
        # agent_type -> list of variants (system + org-scoped)
        # NOTE: tests and some legacy call paths still assign a single object
        # directly (not a list). Access through _agent_variants() for backward
        # compatibility.
        self._agent_cache: Dict[str, Union[AgentCapability, List[AgentCapability]]] = {}
        self._primitive_cache: Dict[str, Primitive] = {}
        self._plugin_cache: Dict[str, Plugin] = {}

    def _agent_variants(self, agent_type: str) -> List[AgentCapability]:
        """Normalize cache entries to a list for backward compatibility."""
        raw = self._agent_cache.get(agent_type)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return [raw]

    async def initialize(self) -> None:
        """Initialize the registry and connect to database."""
        if self._initialized:
            return

        if self._db is None:
            self._db = Database()
            self._owns_db = True
            await self._db.connect()

        await self._load_caches()
        self._initialized = True
        logger.info(
            "UnifiedCapabilityRegistry initialized",
            agents=len(self._agent_cache),
            primitives=len(self._primitive_cache),
            plugins=len(self._plugin_cache),
        )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._owns_db and self._db:
            await self._db.disconnect()
        self._initialized = False

    async def _load_caches(self) -> None:
        """Load all capabilities into memory caches."""
        async with self._db.get_session() as session:
            # Load agents
            agents_result = await session.execute(
                select(AgentCapability).where(AgentCapability.is_active == True)
            )
            for agent in agents_result.scalars():
                existing = self._agent_cache.get(agent.agent_type)
                if existing is None:
                    self._agent_cache[agent.agent_type] = [agent]
                elif isinstance(existing, list):
                    existing.append(agent)
                else:
                    self._agent_cache[agent.agent_type] = [existing, agent]

            # Load primitives
            primitives_result = await session.execute(
                select(Primitive).where(Primitive.is_active == True)
            )
            for primitive in primitives_result.scalars():
                self._primitive_cache[primitive.name] = primitive

            # Load plugins
            plugins_result = await session.execute(
                select(Plugin).where(Plugin.is_active == True)
            )
            for plugin in plugins_result.scalars():
                self._plugin_cache[plugin.namespace] = plugin

    async def refresh(self) -> None:
        """Refresh the caches from database."""
        self._agent_cache.clear()
        self._primitive_cache.clear()
        self._plugin_cache.clear()
        await self._load_caches()

    async def resolve(
        self,
        name: str,
        capability_type: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Optional[ResolvedCapability]:
        """
        Resolve a capability by name.

        Resolution order (if capability_type not specified):
        1. User-defined agents (if organization_id provided)
        2. System agents
        3. Primitives
        4. User plugins (if organization_id provided)
        5. Builtin plugins

        Args:
            name: Capability name (e.g., "summarize", "http.get", "den.upload")
            capability_type: Optional explicit type ("agent", "primitive", "plugin")
            organization_id: Optional organization ID for user-defined capabilities

        Returns:
            ResolvedCapability if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        # If explicit type specified, resolve directly
        if capability_type:
            return await self._resolve_by_type(name, capability_type, organization_id)

        # Try resolution order
        # 1. Check if it's a namespaced plugin operation (e.g., "den.upload")
        if "." in name:
            parts = name.split(".", 1)
            namespace = parts[0]
            if namespace in self._plugin_cache:
                plugin = self._plugin_cache[namespace]
                return ResolvedCapability(
                    name=name,
                    capability_type=CapabilityType.PLUGIN,
                    config=plugin,
                    organization_id=str(plugin.organization_id) if plugin.organization_id else None,
                )

        # 2. Try as agent
        resolved_agent = self._resolve_agent(name, organization_id)
        if resolved_agent is not None:
            return resolved_agent

        # 3. Try as primitive
        if name in self._primitive_cache:
            return ResolvedCapability(
                name=name,
                capability_type=CapabilityType.PRIMITIVE,
                config=self._primitive_cache[name],
            )

        # 4. Try as plugin namespace
        if name in self._plugin_cache:
            plugin = self._plugin_cache[name]
            return ResolvedCapability(
                name=name,
                capability_type=CapabilityType.PLUGIN,
                config=plugin,
                organization_id=str(plugin.organization_id) if plugin.organization_id else None,
            )

        logger.debug("Capability not found", name=name, type=capability_type)
        return None

    def _resolve_agent(
        self,
        agent_type: str,
        organization_id: Optional[str],
    ) -> Optional[ResolvedCapability]:
        """Resolve an agent using org-first then system fallback precedence."""
        variants = self._agent_variants(agent_type)
        if not variants:
            return None

        if organization_id:
            for agent in variants:
                if agent.organization_id is not None and str(agent.organization_id) == str(organization_id):
                    return ResolvedCapability(
                        name=agent_type,
                        capability_type=CapabilityType.AGENT,
                        config=agent,
                        organization_id=organization_id,
                    )

        for agent in variants:
            if agent.is_system or agent.organization_id is None:
                return ResolvedCapability(
                    name=agent_type,
                    capability_type=CapabilityType.AGENT,
                    config=agent,
                    organization_id=None,
                )

        return None

    async def _resolve_by_type(
        self,
        name: str,
        capability_type: str,
        organization_id: Optional[str] = None,
    ) -> Optional[ResolvedCapability]:
        """Resolve capability by explicit type."""
        cap_type = CapabilityType(capability_type)

        if cap_type == CapabilityType.AGENT:
            return self._resolve_agent(name, organization_id)

        elif cap_type == CapabilityType.PRIMITIVE:
            if name in self._primitive_cache:
                return ResolvedCapability(
                    name=name,
                    capability_type=CapabilityType.PRIMITIVE,
                    config=self._primitive_cache[name],
                )

        elif cap_type == CapabilityType.PLUGIN:
            # Handle namespaced operations (e.g., "den.upload")
            namespace = name.split(".")[0] if "." in name else name
            if namespace in self._plugin_cache:
                return ResolvedCapability(
                    name=name,
                    capability_type=CapabilityType.PLUGIN,
                    config=self._plugin_cache[namespace],
                    organization_id=organization_id,
                )

        return None

    async def resolve_any(self, name: str) -> Tuple[Optional[CapabilityType], Optional[Any]]:
        """
        Resolve a capability and return its type and config.

        Convenience method for backward compatibility.

        Returns:
            Tuple of (CapabilityType, config) or (None, None) if not found
        """
        resolved = await self.resolve(name)
        if resolved:
            return resolved.capability_type, resolved.config
        return None, None

    def _visible_agents(self, organization_id: Optional[str]) -> List[AgentCapability]:
        """Return visible agents for an optional organization context."""
        visible: List[AgentCapability] = []
        for agent_type in sorted(self._agent_cache.keys()):
            resolved = self._resolve_agent(agent_type, organization_id)
            if resolved is not None:
                visible.append(resolved.config)
        return visible

    def list_agents(self, organization_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List visible agents for an optional organization context."""
        return [
            {
                "agent_type": agent.agent_type,
                "name": agent.name,
                "domain": agent.domain,
                "description": agent.description,
                "is_system": bool(agent.is_system),
                "is_custom": not bool(agent.is_system),
                "organization_id": str(agent.organization_id) if agent.organization_id else None,
                "inputs_schema": agent.inputs_schema,
                "outputs_schema": agent.outputs_schema,
            }
            for agent in self._visible_agents(organization_id)
        ]

    def list_primitives(self) -> List[Dict[str, Any]]:
        """List all registered primitives."""
        return [
            {
                "name": prim.name,
                "category": prim.category,
                "description": prim.description,
            }
            for prim in self._primitive_cache.values()
        ]

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins."""
        return [
            {
                "namespace": plugin.namespace,
                "name": plugin.name,
                "plugin_type": plugin.plugin_type,
                "description": plugin.description,
                "is_system": plugin.is_system,
                "config": plugin.config or {},
            }
            for plugin in self._plugin_cache.values()
        ]

    def list_all(self) -> List[Dict[str, Any]]:
        """List all capabilities with their types."""
        capabilities = []

        for agent in self._visible_agents(None):
            capabilities.append({
                "name": agent.agent_type,
                "type": "agent",
                "description": agent.description,
                "domain": agent.domain,
                "deterministic": False,
            })

        for prim in self._primitive_cache.values():
            capabilities.append({
                "name": prim.name,
                "type": "primitive",
                "description": prim.description,
                "category": prim.category,
                "deterministic": True,
            })

        for plugin in self._plugin_cache.values():
            capabilities.append({
                "name": plugin.namespace,
                "type": "plugin",
                "description": plugin.description,
                "plugin_type": plugin.plugin_type,
                "deterministic": True,
            })

        return capabilities

    async def list_for_planner(self, organization_id: Optional[str] = None) -> str:
        """
        Generate prompt documentation for the planner.

        This creates a comprehensive list of all available capabilities
        that can be included in the planning prompt.

        Args:
            organization_id: Optional org ID to include user-defined capabilities

        Returns:
            Markdown-formatted documentation string
        """
        if not self._initialized:
            await self.initialize()

        lines = ["# Available Capabilities\n"]

        # Agents section
        lines.append("## Agents (LLM-powered)\n")
        lines.append("Use agents for tasks requiring reasoning, creativity, or understanding.\n")

        # Group agents by domain
        agents_by_domain: Dict[str, List[AgentCapability]] = {}
        for agent in self._visible_agents(organization_id):
            domain = agent.domain or "general"
            if domain not in agents_by_domain:
                agents_by_domain[domain] = []
            agents_by_domain[domain].append(agent)

        for domain, agents in sorted(agents_by_domain.items()):
            lines.append(f"### {domain.title()} Domain\n")
            for agent in sorted(agents, key=lambda a: a.agent_type):
                hints = agent.execution_hints or {}
                speed = hints.get("speed", "medium")
                cost = hints.get("cost", "medium")
                prefix = " [custom]" if (agent.organization_id is not None and not agent.is_system) else ""
                lines.append(f"- **{agent.agent_type}**{prefix}: {agent.description.strip().split(chr(10))[0]}")
                lines.append(f"  - Speed: {speed}, Cost: {cost}")

                # List inputs
                if agent.inputs_schema:
                    schema = agent.inputs_schema
                    # Normalize JSON Schema format
                    if "properties" in schema and isinstance(schema.get("properties"), dict):
                        schema_required = schema.get("required", [])
                        required = [k for k in schema["properties"] if k in schema_required]
                    else:
                        required = [k for k, v in schema.items() if isinstance(v, dict) and v.get("required")]
                    if required:
                        lines.append(f"  - Required inputs: {', '.join(required)}")
            lines.append("")

        # Primitives section
        if self._primitive_cache:
            lines.append("## Primitives (Deterministic Tools)\n")
            lines.append("Use primitives for fast, deterministic operations without LLM.\n")

            # Group by category
            prims_by_category: Dict[str, List[Primitive]] = {}
            for prim in self._primitive_cache.values():
                category = prim.category or "general"
                if category not in prims_by_category:
                    prims_by_category[category] = []
                prims_by_category[category].append(prim)

            for category, prims in sorted(prims_by_category.items()):
                lines.append(f"### {category.title()}\n")
                for prim in sorted(prims, key=lambda p: p.name):
                    lines.append(f"- **{prim.name}**: {prim.description}")
                lines.append("")

        # Plugins section
        if self._plugin_cache:
            lines.append("## Plugins (Service Integrations)\n")
            lines.append("Use plugins to interact with external services.\n")

            for plugin in sorted(self._plugin_cache.values(), key=lambda p: p.namespace):
                lines.append(f"- **{plugin.namespace}**: {plugin.description}")
                lines.append(f"  - Type: {plugin.plugin_type}")
            lines.append("")

        # Efficiency guidance
        lines.append("## Efficiency Principle\n")
        lines.append("Prefer primitives and plugins over agents when possible:")
        lines.append("- Primitives: Instant, free, deterministic")
        lines.append("- Plugins: Fast, cheap, deterministic")
        lines.append("- Agents: Slower, costs tokens, non-deterministic but intelligent")
        lines.append("")
        lines.append("Use agents when you need reasoning, creativity, or understanding.")
        lines.append("Use primitives/plugins for mechanical operations.\n")

        return "\n".join(lines)

    def get_agent_config(self, agent_type: str) -> Optional[AgentCapability]:
        """Get agent configuration by type."""
        resolved = self._resolve_agent(agent_type, organization_id=None)
        return resolved.config if resolved else None

    def get_primitive(self, name: str) -> Optional[Primitive]:
        """Get primitive by name."""
        return self._primitive_cache.get(name)

    def get_plugin(self, namespace: str) -> Optional[Plugin]:
        """Get plugin by namespace."""
        return self._plugin_cache.get(namespace)

    # Backward compatibility methods

    def available_types(self) -> List[str]:
        """Get list of available agent types (backward compat)."""
        return list(self._agent_cache.keys())

    async def create_agent(
        self,
        agent_type: str,
        llm_client=None,
        model: str = "x-ai/grok-4.1-fast",
        **kwargs,
    ):
        """
        Create an agent instance for the specified type.

        This is a bridge method for backward compatibility with SubagentFactory.

        Args:
            agent_type: Type of agent to create
            llm_client: Optional shared LLM client
            model: Model to use for LLM-based agents
            **kwargs: Additional arguments

        Returns:
            Agent instance ready for execution
        """
        resolved = await self.resolve(agent_type, capability_type="agent")
        if not resolved:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Import here to avoid circular imports
        from src.agents.db_configured_agent import DatabaseConfiguredAgent

        return DatabaseConfiguredAgent(
            config=resolved.config,
            llm_client=llm_client,
            model=model,
        )


# Global instance
_registry: Optional[UnifiedCapabilityRegistry] = None


async def get_registry() -> UnifiedCapabilityRegistry:
    """Get the global UnifiedCapabilityRegistry instance."""
    global _registry
    if _registry is None:
        _registry = UnifiedCapabilityRegistry()
        await _registry.initialize()
    return _registry


async def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _registry
    if _registry:
        await _registry.cleanup()
    _registry = None
