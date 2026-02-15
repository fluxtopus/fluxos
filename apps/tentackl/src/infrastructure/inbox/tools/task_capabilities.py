# REVIEW: Agents now use CapabilityUseCases with org scoping, but primitives/plugins
# REVIEW: still rely on the unified registry. Consider a single capability search
# REVIEW: service that unifies agents + primitives + plugins with ranking.
"""Inbox tool: Search available task capabilities.

Allows Flux to discover what agents, primitives, and plugins are
available so it can make informed decisions about task creation and
give accurate answers about platform capabilities.
"""

from typing import Any, Dict, Optional
from uuid import UUID

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.capabilities import (
    CapabilityForbidden,
    CapabilityNotFound,
    CapabilityUseCases,
)
from src.infrastructure.capabilities.sql_repository import SqlCapabilityRepository
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)

_capability_use_cases: Optional[CapabilityUseCases] = None


def _get_capability_use_cases() -> CapabilityUseCases:
    global _capability_use_cases
    if _capability_use_cases is None:
        _capability_use_cases = CapabilityUseCases(
            repository=SqlCapabilityRepository(Database())
        )
    return _capability_use_cases


class TaskCapabilitiesTool(BaseTool):
    """Search and list the platform's available task capabilities."""

    @property
    def name(self) -> str:
        return "task_capabilities"

    @property
    def description(self) -> str:
        return (
            "Search available agents, primitives, and plugins that tasks can use. "
            "Call this before creating a task to verify the capability exists, "
            "or when the user asks what you can do."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Optional search term to filter capabilities. "
                            "Matches against name, description, domain, and keywords. "
                            "Omit to list all capabilities."
                        ),
                    },
                    "capability_type": {
                        "type": "string",
                        "enum": ["agent", "primitive", "plugin", "all"],
                        "description": (
                            "Filter by type. 'agent' = LLM-powered, "
                            "'primitive' = deterministic tools, "
                            "'plugin' = service integrations. "
                            "Default: 'all'"
                        ),
                        "default": "all",
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Filter agents by domain (e.g. 'content', 'research', "
                            "'analytics', 'communication'). Only applies to agents."
                        ),
                    },
                    "detail": {
                        "type": "boolean",
                        "description": (
                            "If true, include inputs/outputs schemas and execution hints. "
                            "Default: false (summary only)."
                        ),
                        "default": False,
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        """Query the unified capability registry."""
        query = (arguments.get("query") or "").strip().lower()
        cap_type = arguments.get("capability_type", "all")
        domain = (arguments.get("domain") or "").strip().lower()
        detail = arguments.get("detail", False)
        organization_id = context.get("organization_id")

        try:
            from src.capabilities.unified_registry import get_registry

            registry = await get_registry()

            results: Dict[str, Any] = {}

            # --- Agents ---
            if cap_type in ("agent", "all"):
                if organization_id:
                    use_cases = _get_capability_use_cases()
                    if query:
                        search_result = await use_cases.search_capabilities(
                            query=query,
                            org_id=organization_id,
                            include_system=True,
                            active_only=True,
                            domain=domain or None,
                            tags=None,
                            limit=50,
                            min_similarity=0.5,
                            prefer_semantic=True,
                        )
                        agents = search_result["results"]
                    else:
                        list_result = await use_cases.list_capabilities(
                            org_id=organization_id,
                            domain=domain or None,
                            tags=None,
                            include_system=True,
                            active_only=True,
                            limit=50,
                            offset=0,
                        )
                        agents = list_result["capabilities"]

                    if detail:
                        agent_list = []
                        for agent in agents:
                            detail_entry = agent
                            if "inputs_schema" not in agent or "outputs_schema" not in agent:
                                try:
                                    detail_result = await use_cases.get_capability(
                                        capability_id=UUID(str(agent["id"])),
                                        org_id=organization_id,
                                    )
                                    detail_entry = detail_result["capability"]
                                except (CapabilityNotFound, CapabilityForbidden):
                                    detail_entry = agent

                            agent_list.append(
                                {
                                    "agent_type": detail_entry["agent_type"],
                                    "name": detail_entry["name"],
                                    "domain": detail_entry.get("domain"),
                                    "description": (detail_entry.get("description") or "")[:300],
                                    "inputs": detail_entry.get("inputs_schema"),
                                    "outputs": detail_entry.get("outputs_schema"),
                                }
                            )
                    else:
                        agent_list = [
                            {
                                "agent_type": a["agent_type"],
                                "name": a["name"],
                                "domain": a.get("domain"),
                                "description": (a.get("description") or "").strip().split("\n")[0][:120],
                            }
                            for a in agents
                        ]
                else:
                    agents = registry.list_agents()

                    if domain:
                        agents = [
                            a for a in agents
                            if (a.get("domain") or "").lower() == domain
                        ]

                    if query:
                        agents = [
                            a for a in agents
                            if _matches(query, a)
                        ]

                    if detail:
                        agent_list = [
                            {
                                "agent_type": a["agent_type"],
                                "name": a["name"],
                                "domain": a.get("domain"),
                                "description": a.get("description", "")[:300],
                                "inputs": a.get("inputs_schema"),
                                "outputs": a.get("outputs_schema"),
                            }
                            for a in agents
                        ]
                    else:
                        agent_list = [
                            {
                                "agent_type": a["agent_type"],
                                "name": a["name"],
                                "domain": a.get("domain"),
                                "description": (a.get("description") or "").strip().split("\n")[0][:120],
                            }
                            for a in agents
                        ]

                results["agents"] = agent_list
                results["agent_count"] = len(agent_list)

            # --- Primitives ---
            if cap_type in ("primitive", "all"):
                primitives = registry.list_primitives()

                if query:
                    primitives = [
                        p for p in primitives
                        if _matches(query, p)
                    ]

                prim_list = [
                    {
                        "name": p["name"],
                        "category": p.get("category"),
                        "description": (p.get("description") or "").strip().split("\n")[0][:120],
                    }
                    for p in primitives
                ]
                results["primitives"] = prim_list
                results["primitive_count"] = len(prim_list)

            # --- Plugins ---
            if cap_type in ("plugin", "all"):
                plugins = registry.list_plugins()

                if query:
                    plugins = [
                        p for p in plugins
                        if _matches(query, p)
                    ]

                plugin_list = [
                    {
                        "namespace": p["namespace"],
                        "name": p["name"],
                        "type": p.get("plugin_type"),
                        "description": (p.get("description") or "").strip().split("\n")[0][:120],
                    }
                    for p in plugins
                ]
                results["plugins"] = plugin_list
                results["plugin_count"] = len(plugin_list)

            # --- Summary ---
            total = sum(
                results.get(k, 0)
                for k in ("agent_count", "primitive_count", "plugin_count")
            )

            if total == 0 and query:
                return ToolResult(
                    success=True,
                    data=results,
                    message=f"No capabilities found matching '{query}'.",
                )

            return ToolResult(
                success=True,
                data=results,
                message=f"Found {total} capabilities.",
            )

        except Exception as e:
            logger.error("Failed to query capabilities", error=str(e))
            return ToolResult(
                success=False,
                error=f"Failed to query capabilities: {str(e)}",
            )


def _matches(query: str, item: Dict[str, Any]) -> bool:
    """Check if a query matches any searchable field of a capability."""
    searchable = " ".join(
        str(v).lower()
        for k, v in item.items()
        if k in ("name", "agent_type", "namespace", "description", "domain", "category")
        and v
    )
    return query in searchable
