"""
Memory Plugin for Tentackl Agent Memory System.

Provides plugin handlers for agents to store and query organizational memories.
These handlers allow agents to persist knowledge that survives across orchestrator
cycles - enabling agents to learn and share knowledge.

Architecture:
    - memory_store_handler: Store new memories (key-value with metadata)
    - memory_query_handler: Query memories by topic, tags, or text search

Key features:
    - Organization-isolated knowledge storage
    - Versioning for memory updates
    - Topic and tag-based categorization
    - Scope-based access control
"""

from typing import Any, Dict, Optional

import structlog

from src.interfaces.database import Database
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryQuery,
    MemoryScopeEnum,
)
from src.application.memory import MemoryUseCases
from src.infrastructure.memory import build_memory_use_cases

logger = structlog.get_logger(__name__)

# Database instance - will be set by app startup or caller
_database: Optional[Database] = None


def set_database(db: Database) -> None:
    """Set the database instance for memory plugins."""
    global _database
    _database = db


def _get_database() -> Database:
    """Get the database instance, creating one if needed."""
    global _database
    if _database is None:
        _database = Database()
    return _database


async def _get_memory_use_cases() -> MemoryUseCases:
    """Get memory use cases with a connected database."""
    db = _get_database()
    return build_memory_use_cases(db)


async def memory_store_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Store a memory for an organization.

    This handler allows agents to persist knowledge that can be retrieved
    in future orchestrator cycles.

    Identity fields (org_id, user_id, agent_id) are taken from the
    ExecutionContext (built from the plan in DB), not from inputs.

    Inputs:
        key: string (required) - Unique key within the organization
        title: string (required) - Short title for the memory
        body: string (required) - The memory content
        scope: string (optional) - 'organization', 'user', 'agent', or 'topic' (default: 'organization')
        scope_value: string (optional) - The scope identifier (user/agent ID or topic name)
        topic: string (optional) - Topic category for the memory
        tags: list[string] (optional) - Tags for filtering and categorization

    Context (from ExecutionContext):
        organization_id: Organization this execution belongs to
        user_id: User who initiated the task
        agent_id: Agent executing the step

    Returns:
        {
            memory_id: string - The created memory ID,
            key: string - The memory key,
            version: int - The version number (1 for new memories)
        }
        OR
        {
            status: 'error',
            error: string - Error message
        }
    """
    try:
        # Get identity from context (trusted source), not inputs
        if context is None:
            return {"status": "error", "error": "ExecutionContext is required for memory operations"}

        org_id = context.organization_id
        user_id = context.user_id
        agent_id = context.agent_id

        # Log if inputs contain a different org_id (potential spoofing attempt)
        input_org_id = inputs.get("org_id")
        if input_org_id and input_org_id != org_id:
            logger.warning(
                "memory_store_org_id_mismatch",
                context_org_id=org_id,
                input_org_id=input_org_id,
                step_id=context.step_id,
            )

        # Validate required content fields
        key = inputs.get("key")
        title = inputs.get("title")
        body = inputs.get("body")

        if not key:
            return {"status": "error", "error": "Missing required field: key"}
        if not title:
            return {"status": "error", "error": "Missing required field: title"}
        if not body:
            return {"status": "error", "error": "Missing required field: body"}

        # Parse scope (default to organization)
        scope_str = inputs.get("scope", "organization").lower()
        try:
            scope = MemoryScopeEnum(scope_str)
        except ValueError:
            scope = MemoryScopeEnum.ORGANIZATION

        # Get optional content fields
        scope_value = inputs.get("scope_value")
        topic = inputs.get("topic")
        tags = inputs.get("tags", [])

        # Ensure tags is a list
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Create the memory request
        request = MemoryCreateRequest(
            organization_id=org_id,
            key=key,
            title=title,
            body=body,
            scope=scope,
            scope_value=scope_value,
            topic=topic,
            tags=tags,
            created_by_user_id=user_id,
            created_by_agent_id=agent_id,
        )

        # Store the memory
        use_cases = await _get_memory_use_cases()
        result = await use_cases.store(request)

        logger.info(
            "memory_stored_via_plugin",
            org_id=org_id,
            key=key,
            memory_id=result.id,
            agent_id=agent_id,
        )

        return {
            "memory_id": result.id,
            "key": result.key,
            "version": result.version,
        }

    except Exception as e:
        logger.error(
            "memory_store_handler_failed",
            error=str(e),
            org_id=context.organization_id if context else None,
            key=inputs.get("key"),
        )
        return {"status": "error", "error": f"Failed to store memory: {str(e)}"}


async def memory_query_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Query memories for an organization.

    This handler allows agents to retrieve stored knowledge based on
    various filters including topic, tags, and text search.

    Identity fields (org_id, user_id, agent_id) are taken from the
    ExecutionContext (built from the plan in DB), not from inputs.

    Inputs:
        text: string (optional) - Text for semantic search
        topic: string (optional) - Filter by topic
        tags: list[string] (optional) - Filter by tags (memories must have all tags)
        key: string (optional) - Lookup by exact key
        limit: int (optional) - Maximum number of results (default: 5, max: 50)

    Context (from ExecutionContext):
        organization_id: Organization this execution belongs to
        user_id: User who initiated the task
        agent_id: Agent executing the step

    Returns:
        {
            memories: list[dict] - List of matching memories with fields:
                id, key, title, body, topic, tags, relevance
            count: int - Number of results returned
        }
        OR
        {
            status: 'error',
            error: string - Error message
        }
    """
    try:
        # Get identity from context (trusted source), not inputs
        if context is None:
            return {"status": "error", "error": "ExecutionContext is required for memory operations"}

        org_id = context.organization_id
        user_id = context.user_id
        agent_id = context.agent_id

        # Log if inputs contain a different org_id (potential spoofing attempt)
        input_org_id = inputs.get("org_id")
        if input_org_id and input_org_id != org_id:
            logger.warning(
                "memory_query_org_id_mismatch",
                context_org_id=org_id,
                input_org_id=input_org_id,
                step_id=context.step_id,
            )

        # Get optional filters from inputs (these are content filters, not identity)
        text = inputs.get("text")
        topic = inputs.get("topic")
        tags = inputs.get("tags", [])
        key = inputs.get("key")
        limit = min(inputs.get("limit", 5), 50)  # Cap at 50

        # Ensure tags is a list
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Build the query
        query = MemoryQuery(
            organization_id=org_id,
            text=text,
            key=key,
            topic=topic,
            tags=tags if tags else None,
            limit=limit,
            requesting_agent_id=agent_id,
            requesting_user_id=user_id,
        )

        # Execute search
        use_cases = await _get_memory_use_cases()
        response = await use_cases.search(query)

        # Format results for agent consumption
        memories = []
        for memory in response.memories:
            memories.append({
                "id": memory.id,
                "key": memory.key,
                "title": memory.title,
                "body": memory.body,
                "topic": memory.topic,
                "tags": memory.tags,
                "relevance": memory.evidence.relevance_score if memory.evidence else 1.0,
            })

        logger.debug(
            "memory_query_via_plugin",
            org_id=org_id,
            topic=topic,
            result_count=len(memories),
            agent_id=agent_id,
        )

        return {
            "memories": memories,
            "count": len(memories),
        }

    except Exception as e:
        logger.error(
            "memory_query_handler_failed",
            error=str(e),
            org_id=context.organization_id if context else None,
        )
        return {"status": "error", "error": f"Failed to query memories: {str(e)}"}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "memory_store": memory_store_handler,
    "memory_query": memory_query_handler,
}
