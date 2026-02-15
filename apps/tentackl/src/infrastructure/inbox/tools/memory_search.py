# REVIEW: Tool constructs MemoryUseCases/Database per call and embeds search/store
# REVIEW: logic inline, making it hard to reuse outside inbox and to test. Consider
# REVIEW: injecting a memory service dependency and centralizing validation.
"""Inbox tool: Search and store organizational memories."""

from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.infrastructure.memory import build_memory_use_cases

logger = structlog.get_logger(__name__)


class MemoryTool(BaseTool):
    """Search and store organizational memories from the inbox."""

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Search and store organizational knowledge. Use 'search' to find "
            "memories by text, topic, tags, or exact key. Use 'store' to save "
            "important context — user preferences, decisions, key facts."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "store"],
                        "description": "Action to perform: search or store.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Semantic search query (search only).",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by topic (search) or assign topic (store).",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (search) or assign tags (store).",
                    },
                    "key": {
                        "type": "string",
                        "description": "Exact key lookup (search) or unique key (store).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (search only, default 5, max 10).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Memory title (store only, required for store).",
                    },
                    "body": {
                        "type": "string",
                        "description": "Memory content (store only, required for store).",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["organization", "user", "agent", "topic"],
                        "description": "Memory scope (store only, default: organization).",
                    },
                },
                "required": ["action"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        action = arguments.get("action")
        organization_id = context.get("organization_id")
        user_id = context.get("user_id")

        if not organization_id:
            return ToolResult(success=False, error="Missing organization_id")
        if not user_id:
            return ToolResult(success=False, error="Missing user_id")

        try:
            if action == "search":
                return await self._handle_search(arguments, organization_id, user_id)
            elif action == "store":
                return await self._handle_store(arguments, organization_id, user_id)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error("memory_tool_failed", error=str(e), action=action)
            return ToolResult(success=False, error=f"Memory {action} failed: {str(e)}")

    async def _handle_search(
        self, arguments: Dict[str, Any], organization_id: str, user_id: str
    ) -> ToolResult:
        from src.domain.memory.models import MemoryQuery

        text = arguments.get("text")
        topic = arguments.get("topic")
        tags = arguments.get("tags")
        key = arguments.get("key")
        limit = min(arguments.get("limit", 5), 10)

        # Ensure tags is a list
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # At least one search criterion required
        if not any([text, topic, tags, key]):
            return ToolResult(
                success=False,
                error="Provide at least one of: text, topic, tags, or key.",
            )

        query = MemoryQuery(
            organization_id=organization_id,
            text=text,
            key=key,
            topic=topic,
            tags=tags if tags else None,
            limit=limit,
            requesting_user_id=user_id,
            requesting_agent_id="flux",
        )

        use_cases = build_memory_use_cases()
        response = await use_cases.search(query)

        memories = []
        for memory in response.memories:
            entry: Dict[str, Any] = {
                "id": memory.id,
                "key": memory.key,
                "title": memory.title,
                "body": memory.body,
                "topic": memory.topic,
                "tags": memory.tags,
                "relevance": memory.evidence.relevance_score if memory.evidence else 1.0,
                "updated_at": str(memory.updated_at) if memory.updated_at else None,
            }
            memories.append(entry)

        return ToolResult(
            success=True,
            data={"memories": memories, "count": len(memories)},
            message=f"Found {len(memories)} memory(ies).",
        )

    async def _handle_store(
        self, arguments: Dict[str, Any], organization_id: str, user_id: str
    ) -> ToolResult:
        from src.domain.memory.models import MemoryCreateRequest, MemoryScopeEnum

        key = arguments.get("key")
        title = arguments.get("title")
        body = arguments.get("body")

        if not key:
            return ToolResult(success=False, error="Missing required field: key")
        if not title:
            return ToolResult(success=False, error="Missing required field: title")
        if not body:
            return ToolResult(success=False, error="Missing required field: body")

        # Parse scope
        scope_str = arguments.get("scope", "organization").lower()
        try:
            scope = MemoryScopeEnum(scope_str)
        except ValueError:
            scope = MemoryScopeEnum.ORGANIZATION

        topic = arguments.get("topic")
        tags = arguments.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        request = MemoryCreateRequest(
            organization_id=organization_id,
            key=key,
            title=title,
            body=body,
            scope=scope,
            topic=topic,
            tags=tags if tags else None,
            created_by_user_id=user_id,
            created_by_agent_id="flux",
        )

        use_cases = build_memory_use_cases()
        result = await use_cases.store(request)

        logger.info(
            "memory_stored_via_flux",
            org_id=organization_id,
            key=key,
            memory_id=result.id,
        )

        return ToolResult(
            success=True,
            data={
                "memory_id": result.id,
                "key": result.key,
                "version": result.version,
            },
            message=f"Memory stored: {key} (v{result.version})",
        )
