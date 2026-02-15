"""
Document DB Plugin for Tentackl Agent Memory System.

This plugin provides document-oriented database operations for agents,
built on top of Den (InkPass file storage). Each agent gets isolated
document collections stored as JSON files.

Architecture:
    /agents/{agent_id}/documents/
    ├── leads/                    # Collection folder
    │   ├── _schema.json          # Optional schema definition
    │   ├── doc_001.json          # Document: {name: "Alice", ...}
    │   └── doc_002.json          # Document: {name: "Bob", ...}
    └── history/                  # Another collection
        └── doc_001.json

Key concepts:
- Collection = folder
- Document = JSON file
- Schema = optional _schema.json for validation/discovery
- Documents auto-tagged with collection:name for querying
"""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import json
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)


class DocumentDBPluginError(Exception):
    """Raised when document DB operations fail."""
    pass


def _get_collection_path(agent_id: str, collection: str) -> str:
    """Get the folder path for a collection."""
    return f"/agents/{agent_id}/documents/{collection}"


def _generate_doc_id() -> str:
    """Generate a unique document ID."""
    return f"doc_{str(uuid4())[:8]}"


async def create_collection_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new document collection for an agent.

    A collection is simply a folder in Den storage. Optionally,
    you can provide a schema that will be stored as _schema.json
    to help with discovery and validation.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID (for namespace isolation)
        collection: string (required) - Collection name
        schema: dict (optional) - JSON Schema for documents
        description: string (optional) - Collection description

    Returns:
        {
            collection: string - Collection name,
            path: string - Full folder path,
            schema_created: bool - Whether schema was created
        }
    """
    try:
        from .den_file_plugin import upload_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")

        if not all([org_id, agent_id, collection]):
            return {"error": "Missing required fields: org_id, agent_id, collection"}

        collection_path = _get_collection_path(agent_id, collection)
        schema_created = False

        # If schema provided, create _schema.json
        schema = inputs.get("schema")
        if schema:
            schema_doc = {
                "collection": collection,
                "description": inputs.get("description", ""),
                "schema": schema,
                "created_at": datetime.utcnow().isoformat(),
            }

            result = await upload_file_handler({
                "org_id": org_id,
                "workflow_id": f"agent_{agent_id}",
                "agent_id": agent_id,
                "content": json.dumps(schema_doc, indent=2),
                "filename": "_schema.json",
                "content_type": "application/json",
                "folder_path": collection_path,
                "tags": ["document_db", f"collection:{collection}", "schema"],
            })

            if "error" not in result:
                schema_created = True
            else:
                logger.warning("Failed to create schema", error=result.get("error"))

        return {
            "collection": collection,
            "path": collection_path,
            "schema_created": schema_created,
        }

    except Exception as e:
        logger.error("create_collection_failed", error=str(e), collection=inputs.get("collection"))
        return {"error": f"Create collection failed: {str(e)}"}


async def insert_document_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Insert a document into a collection.

    Documents are stored as JSON files with auto-generated IDs.
    The document ID is included in the stored data as _id.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name
        document: dict (required) - Document data
        doc_id: string (optional) - Custom document ID (auto-generated if not provided)

    Returns:
        {
            doc_id: string - Document ID,
            file_id: string - Den file ID,
            collection: string - Collection name
        }
    """
    try:
        from .den_file_plugin import upload_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")
        document = inputs.get("document")

        if not all([org_id, agent_id, collection, document]):
            return {"error": "Missing required fields: org_id, agent_id, collection, document"}

        if not isinstance(document, dict):
            return {"error": "Document must be a dictionary"}

        # Generate or use provided doc_id
        doc_id = inputs.get("doc_id") or _generate_doc_id()

        # Add metadata to document
        stored_doc = {
            "_id": doc_id,
            "_collection": collection,
            "_agent_id": agent_id,
            "_created_at": datetime.utcnow().isoformat(),
            "_updated_at": datetime.utcnow().isoformat(),
            **document,
        }

        collection_path = _get_collection_path(agent_id, collection)

        result = await upload_file_handler({
            "org_id": org_id,
            "workflow_id": f"agent_{agent_id}",
            "agent_id": agent_id,
            "content": json.dumps(stored_doc, indent=2, default=str),
            "filename": f"{doc_id}.json",
            "content_type": "application/json",
            "folder_path": collection_path,
            "tags": ["document_db", f"collection:{collection}", f"doc:{doc_id}"],
        })

        if "error" in result:
            return result

        return {
            "doc_id": doc_id,
            "file_id": result.get("file_id"),
            "collection": collection,
        }

    except Exception as e:
        logger.error("insert_document_failed", error=str(e), collection=inputs.get("collection"))
        return {"error": f"Insert document failed: {str(e)}"}


async def find_documents_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Find documents in a collection with optional filtering.

    Simple query support via exact field matching.
    For complex queries, use the Data Admin agent.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name
        query: dict (optional) - Field values to match (exact match only)
        limit: int (optional) - Maximum documents to return (default: 100)

    Returns:
        {
            documents: list[dict] - Matching documents,
            count: int - Number of documents found
        }
    """
    try:
        from .den_file_plugin import list_files_handler, download_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")
        query = inputs.get("query", {})
        limit = inputs.get("limit", 100)

        if not all([org_id, agent_id, collection]):
            return {"error": "Missing required fields: org_id, agent_id, collection"}

        collection_path = _get_collection_path(agent_id, collection)

        # List all files in collection
        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": collection_path,
            "tags": ["document_db", f"collection:{collection}"],
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])
        documents = []

        for file_info in files:
            # Skip schema file
            if file_info.get("name") == "_schema.json":
                continue

            # Download and parse document
            download_result = await download_file_handler({
                "org_id": org_id,
                "file_id": file_info.get("id"),
                "agent_id": agent_id,
            })

            if "error" in download_result:
                continue

            try:
                doc = json.loads(download_result.get("content"))

                # Apply query filter (exact match)
                if query:
                    match = all(
                        doc.get(k) == v for k, v in query.items()
                    )
                    if not match:
                        continue

                documents.append(doc)

                if len(documents) >= limit:
                    break

            except json.JSONDecodeError:
                logger.warning("Invalid JSON in document", file_id=file_info.get("id"))
                continue

        return {
            "documents": documents,
            "count": len(documents),
        }

    except Exception as e:
        logger.error("find_documents_failed", error=str(e), collection=inputs.get("collection"))
        return {"error": f"Find documents failed: {str(e)}"}


async def get_document_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get a single document by ID.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name
        doc_id: string (required) - Document ID

    Returns:
        {
            document: dict | null - Document data or null if not found
        }
    """
    try:
        from .den_file_plugin import list_files_handler, download_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")
        doc_id = inputs.get("doc_id")

        if not all([org_id, agent_id, collection, doc_id]):
            return {"error": "Missing required fields: org_id, agent_id, collection, doc_id"}

        collection_path = _get_collection_path(agent_id, collection)

        # List files and find the document
        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": collection_path,
            "tags": [f"doc:{doc_id}"],
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])

        # Find matching document
        for file_info in files:
            if file_info.get("name") == f"{doc_id}.json":
                download_result = await download_file_handler({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                if "error" in download_result:
                    return download_result

                doc = json.loads(download_result.get("content"))
                return {"document": doc}

        return {"document": None}

    except Exception as e:
        logger.error("get_document_failed", error=str(e), doc_id=inputs.get("doc_id"))
        return {"error": f"Get document failed: {str(e)}"}


async def update_document_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing document.

    Merges the provided updates with the existing document.
    Use $set to replace specific fields, or provide fields directly.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name
        doc_id: string (required) - Document ID
        updates: dict (required) - Fields to update

    Returns:
        {
            doc_id: string - Document ID,
            updated: bool - Whether update was successful
        }
    """
    try:
        from .den_file_plugin import list_files_handler, download_file_handler, upload_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")
        doc_id = inputs.get("doc_id")
        updates = inputs.get("updates")

        if not all([org_id, agent_id, collection, doc_id, updates]):
            return {"error": "Missing required fields: org_id, agent_id, collection, doc_id, updates"}

        collection_path = _get_collection_path(agent_id, collection)

        # Get existing document
        get_result = await get_document_handler({
            "org_id": org_id,
            "agent_id": agent_id,
            "collection": collection,
            "doc_id": doc_id,
        })

        if "error" in get_result:
            return get_result

        existing_doc = get_result.get("document")
        if not existing_doc:
            return {"error": f"Document not found: {doc_id}"}

        # Merge updates (handle $set operator or direct fields)
        if "$set" in updates:
            merged_doc = {**existing_doc, **updates["$set"]}
        else:
            merged_doc = {**existing_doc, **updates}

        # Update metadata
        merged_doc["_updated_at"] = datetime.utcnow().isoformat()

        # Save updated document
        result = await upload_file_handler({
            "org_id": org_id,
            "workflow_id": f"agent_{agent_id}",
            "agent_id": agent_id,
            "content": json.dumps(merged_doc, indent=2, default=str),
            "filename": f"{doc_id}.json",
            "content_type": "application/json",
            "folder_path": collection_path,
            "tags": ["document_db", f"collection:{collection}", f"doc:{doc_id}"],
        })

        if "error" in result:
            return result

        return {
            "doc_id": doc_id,
            "updated": True,
        }

    except Exception as e:
        logger.error("update_document_failed", error=str(e), doc_id=inputs.get("doc_id"))
        return {"error": f"Update document failed: {str(e)}"}


async def delete_document_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a document from a collection.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name
        doc_id: string (required) - Document ID

    Returns:
        {
            doc_id: string - Document ID,
            deleted: bool - Whether deletion was successful
        }
    """
    try:
        from .den_file_plugin import list_files_handler, delete_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")
        doc_id = inputs.get("doc_id")

        if not all([org_id, agent_id, collection, doc_id]):
            return {"error": "Missing required fields: org_id, agent_id, collection, doc_id"}

        collection_path = _get_collection_path(agent_id, collection)

        # Find the document file
        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": collection_path,
            "tags": [f"doc:{doc_id}"],
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])

        for file_info in files:
            if file_info.get("name") == f"{doc_id}.json":
                delete_result = await delete_file_handler({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                if "error" in delete_result:
                    return delete_result

                return {
                    "doc_id": doc_id,
                    "deleted": True,
                }

        return {"error": f"Document not found: {doc_id}"}

    except Exception as e:
        logger.error("delete_document_failed", error=str(e), doc_id=inputs.get("doc_id"))
        return {"error": f"Delete document failed: {str(e)}"}


async def list_collections_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """List all collections for an agent.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID

    Returns:
        {
            collections: list[dict] - Collection info (name, doc_count),
            count: int - Number of collections
        }
    """
    try:
        from .den_file_plugin import list_files_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, agent_id]):
            return {"error": "Missing required fields: org_id, agent_id"}

        base_path = f"/agents/{agent_id}/documents"

        # List all files with document_db tag (search all folders, filter by agent path)
        list_result = await list_files_handler({
            "org_id": org_id,
            "tags": ["document_db"],
        })

        if "error" in list_result:
            # If folder doesn't exist, return empty list
            if "not found" in str(list_result.get("error", "")).lower():
                return {"collections": [], "count": 0}
            return list_result

        # Filter to only this agent's documents
        all_files = list_result.get("files", [])
        files = [f for f in all_files if f.get("folder_path", "").startswith(base_path)]

        # Group by collection (extract from folder_path)
        collection_counts: Dict[str, int] = {}
        for file_info in files:
            folder = file_info.get("folder_path", "")
            # Extract collection name from path: /agents/{id}/documents/{collection}
            parts = folder.split("/")
            if len(parts) >= 5:
                collection_name = parts[4]
                if collection_name not in collection_counts:
                    collection_counts[collection_name] = 0
                # Don't count schema files
                if file_info.get("name") != "_schema.json":
                    collection_counts[collection_name] += 1

        collections = [
            {"name": name, "document_count": count}
            for name, count in collection_counts.items()
        ]

        return {
            "collections": collections,
            "count": len(collections),
        }

    except Exception as e:
        logger.error("list_collections_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"List collections failed: {str(e)}"}


async def get_schema_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get the schema for a collection (if one exists).

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name

    Returns:
        {
            schema: dict | null - Schema definition or null if not defined
        }
    """
    try:
        from .den_file_plugin import list_files_handler, download_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")

        if not all([org_id, agent_id, collection]):
            return {"error": "Missing required fields: org_id, agent_id, collection"}

        collection_path = _get_collection_path(agent_id, collection)

        # List files and find schema
        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": collection_path,
            "tags": ["schema"],
        })

        if "error" in list_result:
            return {"schema": None}

        files = list_result.get("files", [])

        for file_info in files:
            if file_info.get("name") == "_schema.json":
                download_result = await download_file_handler({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                if "error" in download_result:
                    return {"schema": None}

                schema_doc = json.loads(download_result.get("content"))
                return {"schema": schema_doc}

        return {"schema": None}

    except Exception as e:
        logger.error("get_schema_failed", error=str(e), collection=inputs.get("collection"))
        return {"error": f"Get schema failed: {str(e)}"}


async def count_documents_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Count documents in a collection.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        collection: string (required) - Collection name

    Returns:
        {
            count: int - Number of documents
        }
    """
    try:
        from .den_file_plugin import list_files_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        collection = inputs.get("collection")

        if not all([org_id, agent_id, collection]):
            return {"error": "Missing required fields: org_id, agent_id, collection"}

        collection_path = _get_collection_path(agent_id, collection)

        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": collection_path,
            "tags": ["document_db", f"collection:{collection}"],
        })

        if "error" in list_result:
            return {"count": 0}

        files = list_result.get("files", [])
        # Count documents (exclude schema file)
        count = sum(1 for f in files if f.get("name") != "_schema.json")

        return {"count": count}

    except Exception as e:
        logger.error("count_documents_failed", error=str(e), collection=inputs.get("collection"))
        return {"error": f"Count documents failed: {str(e)}"}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "doc_create_collection": create_collection_handler,
    "doc_insert": insert_document_handler,
    "doc_find": find_documents_handler,
    "doc_get": get_document_handler,
    "doc_update": update_document_handler,
    "doc_delete": delete_document_handler,
    "doc_list_collections": list_collections_handler,
    "doc_get_schema": get_schema_handler,
    "doc_count": count_documents_handler,
}

# Plugin definitions for registry
DOCUMENT_DB_PLUGIN_DEFINITIONS = [
    {
        "name": "doc_create_collection",
        "description": "Create a new document collection for an agent",
        "handler": create_collection_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "schema": {"type": "object"},
                "description": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string"},
                "path": {"type": "string"},
                "schema_created": {"type": "boolean"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_insert",
        "description": "Insert a document into a collection",
        "handler": insert_document_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "document": {"type": "object"},
                "doc_id": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection", "document"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "file_id": {"type": "string"},
                "collection": {"type": "string"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_find",
        "description": "Find documents in a collection with optional filtering",
        "handler": find_documents_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "query": {"type": "object"},
                "limit": {"type": "integer"},
            },
            "required": ["org_id", "agent_id", "collection"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "documents": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_get",
        "description": "Get a single document by ID",
        "handler": get_document_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "doc_id": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection", "doc_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "document": {"type": ["object", "null"]},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_update",
        "description": "Update an existing document",
        "handler": update_document_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "doc_id": {"type": "string"},
                "updates": {"type": "object"},
            },
            "required": ["org_id", "agent_id", "collection", "doc_id", "updates"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "updated": {"type": "boolean"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_delete",
        "description": "Delete a document from a collection",
        "handler": delete_document_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
                "doc_id": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection", "doc_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "deleted": {"type": "boolean"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_list_collections",
        "description": "List all collections for an agent",
        "handler": list_collections_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["org_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "collections": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_get_schema",
        "description": "Get the schema for a collection",
        "handler": get_schema_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "schema": {"type": ["object", "null"]},
            },
        },
        "category": "document_db",
    },
    {
        "name": "doc_count",
        "description": "Count documents in a collection",
        "handler": count_documents_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "collection": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "collection"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        },
        "category": "document_db",
    },
]
