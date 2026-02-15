"""
Workspace plugin for flexible object storage operations.

Allows agents to create, query, update, delete, and search
workspace objects (events, contacts, custom types).
"""

from typing import Any, Dict
import structlog

from src.plugins.registry import registry, PluginDefinition
from src.application.workspace import WorkspaceUseCases
from src.infrastructure.workspace import WorkspaceServiceAdapter
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)

# Database instance - will be set by the lifespan or caller
_database: Database = None


def set_database(db: Database) -> None:
    """Set the database instance for workspace plugins."""
    global _database
    _database = db


def _get_use_cases() -> WorkspaceUseCases:
    """Get workspace use cases."""
    if not _database:
        raise ValueError("Database not initialized for workspace plugin")
    return WorkspaceUseCases(workspace_ops=WorkspaceServiceAdapter(_database))


async def workspace_create_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Create a workspace object (event, contact, or custom type).

    Inputs:
      org_id: string (required) - Organization ID
      type: string (required) - Object type (e.g., "event", "contact")
      data: object or array (required) - Object data or array of objects
      tags: array (optional) - Tags for filtering
      created_by_type: string (optional) - "user" or "agent"
      created_by_id: string (optional) - Creator ID

    Returns:
      For single object: The created object with id, type, data, timestamps
      For array: { objects: [...], count: N }
    """
    org_id = inputs.get("org_id")
    obj_type = inputs.get("type")
    data = inputs.get("data")

    if not org_id:
        return {"error": "org_id is required"}
    if not obj_type:
        return {"error": "type is required"}
    if data is None:
        return {"error": "data is required"}

    # Handle JSON string input - parse it to object/array
    # This happens when data comes from LLM compose output (content field is always a string)
    if isinstance(data, str):
        data = data.strip()
        if data.startswith('[') or data.startswith('{'):
            import json
            try:
                data = json.loads(data)
                logger.debug("Parsed JSON string data", parsed_type=type(data).__name__)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in data field: {str(e)}"}
        else:
            return {"error": "data must be an object, array, or valid JSON string"}

    # Handle empty array - return success with empty result
    if isinstance(data, list) and len(data) == 0:
        return {"objects": [], "count": 0, "message": "No objects to create (empty data array)"}

    try:
        use_cases = _get_use_cases()
        # Handle array of objects
        if isinstance(data, list):
            created_objects = []
            for item in data:
                result = await use_cases.create_object(
                    org_id=org_id,
                    type=obj_type,
                    data=item,
                    tags=inputs.get("tags"),
                    created_by_type=inputs.get("created_by_type", "agent"),
                    created_by_id=inputs.get("created_by_id"),
                )
                created_objects.append(result)
            return {"objects": created_objects, "count": len(created_objects)}

        # Handle single object
        result = await use_cases.create_object(
            org_id=org_id,
            type=obj_type,
            data=data,
            tags=inputs.get("tags"),
            created_by_type=inputs.get("created_by_type", "agent"),
            created_by_id=inputs.get("created_by_id"),
        )
        return result
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("workspace_create failed", error=str(e))
        return {"error": f"Failed to create object: {str(e)}"}


async def workspace_get_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a workspace object by ID.

    Inputs:
      org_id: string (required) - Organization ID
      id: string (required) - Object UUID

    Returns:
      The object if found, or { error: "Not found" }
    """
    org_id = inputs.get("org_id")
    obj_id = inputs.get("id")

    if not org_id:
        return {"error": "org_id is required"}
    if not obj_id:
        return {"error": "id is required"}

    try:
        use_cases = _get_use_cases()
        result = await use_cases.get_object(org_id, obj_id)
        if not result:
            return {"error": f"Object not found: {obj_id}"}
        return result
    except Exception as e:
        logger.error("workspace_get failed", error=str(e))
        return {"error": f"Failed to get object: {str(e)}"}


async def workspace_update_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a workspace object.

    Inputs:
      org_id: string (required) - Organization ID
      id: string (required) - Object UUID
      data: object (required) - New data
      merge: boolean (optional) - Merge with existing (default: true)

    Returns:
      The updated object
    """
    org_id = inputs.get("org_id")
    obj_id = inputs.get("id")
    data = inputs.get("data")

    if not org_id:
        return {"error": "org_id is required"}
    if not obj_id:
        return {"error": "id is required"}
    if not data:
        return {"error": "data is required"}

    try:
        use_cases = _get_use_cases()
        result = await use_cases.update_object(
            org_id=org_id,
            object_id=obj_id,
            data=data,
            merge=inputs.get("merge", True),
        )
        if not result:
            return {"error": f"Object not found: {obj_id}"}
        return result
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("workspace_update failed", error=str(e))
        return {"error": f"Failed to update object: {str(e)}"}


async def workspace_delete_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a workspace object.

    Inputs:
      org_id: string (required) - Organization ID
      id: string (required) - Object UUID

    Returns:
      { deleted: true } if successful
    """
    org_id = inputs.get("org_id")
    obj_id = inputs.get("id")

    if not org_id:
        return {"error": "org_id is required"}
    if not obj_id:
        return {"error": "id is required"}

    try:
        use_cases = _get_use_cases()
        deleted = await use_cases.delete_object(org_id, obj_id)
        if not deleted:
            return {"error": f"Object not found: {obj_id}"}
        return {"deleted": True, "id": obj_id}
    except Exception as e:
        logger.error("workspace_delete failed", error=str(e))
        return {"error": f"Failed to delete object: {str(e)}"}


async def workspace_query_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Query workspace objects with filters.

    Inputs:
      org_id: string (required) - Organization ID
      type: string (optional) - Filter by type
      where: object (optional) - MongoDB-style query operators
      tags: array (optional) - Filter by tags (all must match)
      order_by: string (optional) - Field to order by
      order_desc: boolean (optional) - Order descending
      limit: number (optional) - Max results (default: 100)
      offset: number (optional) - Skip first N results

    Returns:
      { objects: [...], count: number }
    """
    org_id = inputs.get("org_id")

    if not org_id:
        return {"error": "org_id is required"}

    try:
        use_cases = _get_use_cases()
        objects = await use_cases.query_objects(
            org_id=org_id,
            type=inputs.get("type"),
            where=inputs.get("where"),
            tags=inputs.get("tags"),
            order_by=inputs.get("order_by"),
            order_desc=inputs.get("order_desc", False),
            limit=inputs.get("limit", 100),
            offset=inputs.get("offset", 0),
        )
        return {"objects": objects, "count": len(objects)}
    except Exception as e:
        logger.error("workspace_query failed", error=str(e))
        return {"error": f"Failed to query objects: {str(e)}"}


async def workspace_search_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Full-text search across workspace objects.

    Inputs:
      org_id: string (required) - Organization ID
      query: string (required) - Search query
      type: string (optional) - Filter by type
      limit: number (optional) - Max results (default: 50)

    Returns:
      { objects: [...], count: number, query: string }
    """
    org_id = inputs.get("org_id")
    query = inputs.get("query")

    if not org_id:
        return {"error": "org_id is required"}
    if not query:
        return {"error": "query is required"}

    try:
        use_cases = _get_use_cases()
        objects = await use_cases.search_objects(
            org_id=org_id,
            query=query,
            type=inputs.get("type"),
            limit=inputs.get("limit", 50),
        )
        return {"objects": objects, "count": len(objects), "query": query}
    except Exception as e:
        logger.error("workspace_search failed", error=str(e))
        return {"error": f"Failed to search objects: {str(e)}"}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "workspace_create": workspace_create_handler,
    "workspace_get": workspace_get_handler,
    "workspace_update": workspace_update_handler,
    "workspace_delete": workspace_delete_handler,
    "workspace_query": workspace_query_handler,
    "workspace_search": workspace_search_handler,
}


# Register plugins
registry.register(
    PluginDefinition(
        name="workspace_create",
        description="Create a workspace object (event, contact, or custom type)",
        handler=workspace_create_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "description": "Organization ID"},
                "type": {"type": "string", "description": "Object type (event, contact, etc.)"},
                "data": {"description": "Object data - single object or array of objects"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "created_by_type": {"type": "string", "enum": ["user", "agent"]},
                "created_by_id": {"type": "string"},
            },
            "required": ["org_id", "type", "data"],
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "type": {"type": "string"},
                "data": {"type": "object"},
                "tags": {"type": "array"},
                "created_at": {"type": "string"},
            },
        },
        category="workspace",
    )
)

registry.register(
    PluginDefinition(
        name="workspace_get",
        description="Get a workspace object by ID",
        handler=workspace_get_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "id": {"type": "string"},
            },
            "required": ["org_id", "id"],
        },
        category="workspace",
    )
)

registry.register(
    PluginDefinition(
        name="workspace_update",
        description="Update a workspace object",
        handler=workspace_update_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "id": {"type": "string"},
                "data": {"type": "object"},
                "merge": {"type": "boolean", "default": True},
            },
            "required": ["org_id", "id", "data"],
        },
        category="workspace",
    )
)

registry.register(
    PluginDefinition(
        name="workspace_delete",
        description="Delete a workspace object",
        handler=workspace_delete_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "id": {"type": "string"},
            },
            "required": ["org_id", "id"],
        },
        category="workspace",
    )
)

registry.register(
    PluginDefinition(
        name="workspace_query",
        description="Query workspace objects with filters",
        handler=workspace_query_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "type": {"type": "string"},
                "where": {"type": "object", "description": "MongoDB-style query operators"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "order_by": {"type": "string"},
                "order_desc": {"type": "boolean"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
            "required": ["org_id"],
        },
        category="workspace",
    )
)

registry.register(
    PluginDefinition(
        name="workspace_search",
        description="Full-text search across workspace objects",
        handler=workspace_search_handler,
        inputs_schema={
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "query": {"type": "string"},
                "type": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["org_id", "query"],
        },
        category="workspace",
    )
)
