"""Tool for searching capabilities in the unified capability system.

This tool allows Arrow to discover existing capabilities instead of always
creating new generic llm_worker agents. Updated to use capabilities_agents
table as part of the capabilities unification (CAP-015).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class SearchAgentsTool(BaseTool):
    """Search for capabilities in the unified capability system.

    This tool enables Arrow to:
    - Find existing capabilities that match a task description
    - Filter by domain, tags, or keywords
    - Get capability details needed for task/agent creation (inputs, outputs, etc.)
    - Search user's organization capabilities and system capabilities

    The tool uses a hybrid approach:
    1. Semantic search via pgvector embeddings (when available)
    2. Keyword-based search as fallback
    """

    @property
    def name(self) -> str:
        return "search_agents"

    @property
    def description(self) -> str:
        return """Search the capability registry to find existing capabilities that match your needs.

Use this tool BEFORE creating tasks or agents to check if suitable capabilities already exist.
Searches both system capabilities and user-defined custom capabilities.

Returns capability details including:
- agent_type (for referencing in tasks or agents)
- Name and description
- Domain (content, research, analytics, etc.)
- Required inputs schema and expected outputs schema
- Similarity score indicating match quality (0-1)
- Whether it's a system or custom capability

Examples:
- query="summarize text" → Finds summarize capability
- query="research topic", domain="research" → Finds research capabilities
- query="analyze data", tags=["analytics", "data"] → Finds analytics capabilities
"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords describing what you need the capability to do (e.g., 'summarize text', 'validate JSON', 'analyze sentiment')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter (e.g., 'content', 'research', 'analytics', 'validation')"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags to filter by (e.g., ['text', 'nlp'], ['data', 'validation'])"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10
                    },
                    "include_system": {
                        "type": "boolean",
                        "description": "Include system capabilities in results (default: true)",
                        "default": True
                    }
                },
                "required": ["query"]
            }
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Search for capabilities in the unified capability system.

        Args:
            arguments: {
                "query": str (required) - Search keywords
                "domain": str (optional) - Domain filter
                "tags": List[str] (optional) - Tag filters
                "limit": int (optional) - Max results (default 10)
                "include_system": bool (optional) - Include system capabilities (default True)
            }
            context: {
                "database": Database instance (required)
                "organization_id": str (optional) - User's organization ID for org-scoped search
                "capability_recommender": CapabilityRecommender (optional)
            }

        Returns:
            ToolResult with list of matching capabilities or error
        """
        query = arguments.get("query", "").strip()
        domain = arguments.get("domain")
        tags = arguments.get("tags", [])
        limit = arguments.get("limit", 10)
        include_system = arguments.get("include_system", True)

        if not query:
            return ToolResult(
                success=False,
                error="query parameter is required"
            )

        # Get organization_id from context for org-scoped searches
        organization_id = context.get("organization_id")

        logger.info(
            "Searching capabilities",
            query=query,
            domain=domain,
            tags=tags,
            limit=limit,
            organization_id=organization_id,
            include_system=include_system
        )

        try:
            # Get capability recommender from context
            capability_recommender = context.get("capability_recommender")
            if not capability_recommender:
                # Import lazily to avoid circular imports
                from src.infrastructure.flux_runtime.capability_recommender import CapabilityRecommender

                # Get database from context
                database = context.get("database")
                if not database:
                    # Import and create database instance
                    from src.api.app import get_database
                    database = get_database()

                capability_recommender = CapabilityRecommender(database)

            # Use the recommender to search capabilities
            matches = await capability_recommender.search_and_rank(
                query=query,
                domain=domain,
                tags=tags,
                organization_id=organization_id,
                include_system=include_system,
                limit=limit
            )

            if not matches:
                return ToolResult(
                    success=True,
                    data={"capabilities": [], "count": 0},
                    message=f"No capabilities found matching '{query}'. Consider creating a new custom capability."
                )

            # Format results for LLM
            capabilities_data = []
            for match in matches:
                capability_info = {
                    "agent_type": match.agent_type,
                    "name": match.name,
                    "description": match.description,
                    "domain": match.domain,
                    "tags": match.tags,
                    "similarity": match.similarity,
                    "match_type": match.match_type,
                    "is_system": match.is_system,
                    "is_custom": not match.is_system,
                    "inputs_schema": match.inputs_schema,
                    "outputs_schema": match.outputs_schema,
                    "usage_count": match.usage_count,
                    "success_rate": match.success_rate,
                }
                capabilities_data.append(capability_info)

            # Build helpful message
            top_match = matches[0]
            if top_match.similarity >= 0.8:
                custom_tag = " [custom]" if not top_match.is_system else ""
                message = f"Found excellent match: {top_match.agent_type}{custom_tag} (similarity: {top_match.similarity:.2f})"
            elif top_match.similarity >= 0.5:
                message = f"Found {len(matches)} potential matches. Top result: {top_match.agent_type} (similarity: {top_match.similarity:.2f})"
            else:
                message = f"Found {len(matches)} capabilities but similarity is low. Consider creating a specialized capability."

            logger.info(
                "Capability search completed",
                query=query,
                found_count=len(matches),
                top_similarity=top_match.similarity,
                search_type=top_match.match_type
            )

            return ToolResult(
                success=True,
                data={"capabilities": capabilities_data, "count": len(matches)},
                message=message
            )

        except Exception as e:
            logger.error("Capability search failed", error=str(e), query=query)
            return ToolResult(
                success=False,
                error=f"Capability search error: {str(e)}"
            )
