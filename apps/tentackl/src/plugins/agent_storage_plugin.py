"""
Agent Storage Plugin for Tentackl Agent Memory System.

This plugin provides file storage operations scoped to an agent's namespace.
Each agent has an isolated file namespace within the user's Den storage.

Architecture:
    /agents/{agent_id}/
    ├── outputs/    # Default output folder
    ├── context/    # Persistent memory between runs
    ├── temp/       # Temporary files
    └── {custom}/   # Agent-created folders

Key features:
- Auto-scopes all operations to agent's namespace
- Simplified API without explicit path management
- Context management for persistent memory between runs
- Auto-tagging with agent:{agent_id}
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import structlog

logger = structlog.get_logger(__name__)


class AgentStoragePluginError(Exception):
    """Raised when agent storage operations fail."""
    pass


def _get_agent_path(agent_id: str, subfolder: Optional[str] = None) -> str:
    """Get the base path for an agent's namespace."""
    base = f"/agents/{agent_id}"
    if subfolder:
        return f"{base}/{subfolder}"
    return base


async def save_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Save a file to the agent's storage namespace.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID (determines namespace)
        filename: string (required) - Filename to save
        content: string | bytes (required) - File content
        subfolder: string (optional) - Subfolder within namespace (default: "outputs")
        content_type: string (optional) - MIME type (auto-detected from filename)
        tags: list[string] (optional) - Additional tags

    Returns:
        {
            file_id: string - Den file ID,
            filename: string - Saved filename,
            path: string - Full path in Den,
            url: string - Access URL
        }
    """
    try:
        from .den_file_plugin import upload_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        filename = inputs.get("filename")
        content = inputs.get("content")

        if not all([org_id, agent_id, filename, content]):
            return {"error": "Missing required fields: org_id, agent_id, filename, content"}

        subfolder = inputs.get("subfolder", "outputs")
        folder_path = _get_agent_path(agent_id, subfolder)

        # Auto-detect content type from filename
        content_type = inputs.get("content_type")
        if not content_type:
            if filename.endswith(".json"):
                content_type = "application/json"
            elif filename.endswith(".md"):
                content_type = "text/markdown"
            elif filename.endswith(".txt"):
                content_type = "text/plain"
            else:
                content_type = "application/octet-stream"

        # Build tags
        tags = ["agent_storage", f"agent:{agent_id}"]
        if inputs.get("tags"):
            tags.extend(inputs["tags"])

        result = await upload_file_handler({
            "org_id": org_id,
            "workflow_id": f"agent_{agent_id}",
            "agent_id": agent_id,
            "content": content,
            "filename": filename,
            "content_type": content_type,
            "folder_path": folder_path,
            "tags": tags,
        })

        if "error" in result:
            return result

        return {
            "file_id": result.get("file_id"),
            "filename": filename,
            "path": folder_path,
            "url": result.get("url"),
        }

    except Exception as e:
        logger.error("agent_save_failed", error=str(e), filename=inputs.get("filename"))
        return {"error": f"Save failed: {str(e)}"}


async def load_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Load a file from the agent's storage namespace.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        filename: string (required) - Filename to load
        subfolder: string (optional) - Subfolder to look in (default: "outputs")

    Returns:
        {
            content: string - File content,
            filename: string - Filename,
            size_bytes: int - File size
        }
    """
    try:
        from .den_file_plugin import list_files_handler, download_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        filename = inputs.get("filename")

        if not all([org_id, agent_id, filename]):
            return {"error": "Missing required fields: org_id, agent_id, filename"}

        subfolder = inputs.get("subfolder", "outputs")
        folder_path = _get_agent_path(agent_id, subfolder)

        # Find the file
        list_result = await list_files_handler({
            "org_id": org_id,
            "folder_path": folder_path,
            "tags": [f"agent:{agent_id}"],
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])

        for file_info in files:
            if file_info.get("name") == filename:
                download_result = await download_file_handler({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                if "error" in download_result:
                    return download_result

                return {
                    "content": download_result.get("content"),
                    "filename": filename,
                    "size_bytes": download_result.get("size_bytes"),
                }

        return {"error": f"File not found: {filename}"}

    except Exception as e:
        logger.error("agent_load_failed", error=str(e), filename=inputs.get("filename"))
        return {"error": f"Load failed: {str(e)}"}


async def list_files_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """List files in the agent's storage namespace.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        subfolder: string (optional) - Subfolder to list (default: all)
        tags: list[string] (optional) - Filter by additional tags

    Returns:
        {
            files: list[dict] - File metadata,
            count: int - Number of files
        }
    """
    try:
        from .den_file_plugin import list_files_handler as den_list

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, agent_id]):
            return {"error": "Missing required fields: org_id, agent_id"}

        subfolder = inputs.get("subfolder")
        folder_path = _get_agent_path(agent_id, subfolder) if subfolder else _get_agent_path(agent_id)

        # Build tags filter
        tags = [f"agent:{agent_id}"]
        if inputs.get("tags"):
            tags.extend(inputs["tags"])

        result = await den_list({
            "org_id": org_id,
            "folder_path": folder_path,
            "tags": tags,
        })

        return result

    except Exception as e:
        logger.error("agent_list_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"List failed: {str(e)}"}


async def delete_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a file from the agent's storage namespace.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        filename: string (required) - Filename to delete
        subfolder: string (optional) - Subfolder (default: "outputs")

    Returns:
        {
            deleted: bool - Whether deletion was successful
        }
    """
    try:
        from .den_file_plugin import list_files_handler as den_list, delete_file_handler as den_delete

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        filename = inputs.get("filename")

        if not all([org_id, agent_id, filename]):
            return {"error": "Missing required fields: org_id, agent_id, filename"}

        subfolder = inputs.get("subfolder", "outputs")
        folder_path = _get_agent_path(agent_id, subfolder)

        # Find the file
        list_result = await den_list({
            "org_id": org_id,
            "folder_path": folder_path,
            "tags": [f"agent:{agent_id}"],
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])

        for file_info in files:
            if file_info.get("name") == filename:
                delete_result = await den_delete({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                return delete_result

        return {"error": f"File not found: {filename}"}

    except Exception as e:
        logger.error("agent_delete_failed", error=str(e), filename=inputs.get("filename"))
        return {"error": f"Delete failed: {str(e)}"}


async def search_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Search for files in the agent's namespace by filename pattern or tags.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        pattern: string (optional) - Filename pattern (simple substring match)
        tags: list[string] (optional) - Tags to filter by

    Returns:
        {
            files: list[dict] - Matching files,
            count: int - Number of matches
        }
    """
    try:
        from .den_file_plugin import list_files_handler as den_list

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        pattern = inputs.get("pattern", "")

        if not all([org_id, agent_id]):
            return {"error": "Missing required fields: org_id, agent_id"}

        # List all files in agent namespace
        tags = [f"agent:{agent_id}"]
        if inputs.get("tags"):
            tags.extend(inputs["tags"])

        list_result = await den_list({
            "org_id": org_id,
            "folder_path": _get_agent_path(agent_id),
            "tags": tags,
        })

        if "error" in list_result:
            return list_result

        files = list_result.get("files", [])

        # Filter by pattern if provided
        if pattern:
            files = [f for f in files if pattern.lower() in f.get("name", "").lower()]

        return {
            "files": files,
            "count": len(files),
        }

    except Exception as e:
        logger.error("agent_search_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"Search failed: {str(e)}"}


async def get_context_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get the agent's persistent context/memory.

    Context is stored in /agents/{agent_id}/context/context.json
    and persists between agent runs.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID

    Returns:
        {
            context: dict | null - Context data or null if none exists
        }
    """
    try:
        from .den_file_plugin import list_files_handler as den_list, download_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, agent_id]):
            return {"error": "Missing required fields: org_id, agent_id"}

        folder_path = _get_agent_path(agent_id, "context")

        # Find context file
        list_result = await den_list({
            "org_id": org_id,
            "folder_path": folder_path,
            "tags": ["context", f"agent:{agent_id}"],
        })

        if "error" in list_result:
            return {"context": None}

        files = list_result.get("files", [])

        for file_info in files:
            if file_info.get("name") == "context.json":
                download_result = await download_file_handler({
                    "org_id": org_id,
                    "file_id": file_info.get("id"),
                    "agent_id": agent_id,
                })

                if "error" in download_result:
                    return {"context": None}

                context = json.loads(download_result.get("content"))
                return {"context": context}

        return {"context": None}

    except Exception as e:
        logger.error("get_context_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"Get context failed: {str(e)}"}


async def set_context_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Set the agent's persistent context/memory.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID
        context: dict (required) - Context data to store
        merge: bool (optional) - Merge with existing context (default: False, replaces)

    Returns:
        {
            success: bool - Whether context was saved,
            file_id: string - Den file ID
        }
    """
    try:
        from .den_file_plugin import upload_file_handler

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")
        context = inputs.get("context")

        if not all([org_id, agent_id]) or context is None:
            return {"error": "Missing required fields: org_id, agent_id, context"}

        # If merge is requested, load existing context first
        if inputs.get("merge", False):
            existing_result = await get_context_handler({
                "org_id": org_id,
                "agent_id": agent_id,
            })
            existing_context = existing_result.get("context", {}) or {}
            context = {**existing_context, **context}

        # Add metadata
        context_doc = {
            "_agent_id": agent_id,
            "_updated_at": datetime.utcnow().isoformat(),
            **context,
        }

        folder_path = _get_agent_path(agent_id, "context")

        result = await upload_file_handler({
            "org_id": org_id,
            "workflow_id": f"agent_{agent_id}",
            "agent_id": agent_id,
            "content": json.dumps(context_doc, indent=2, default=str),
            "filename": "context.json",
            "content_type": "application/json",
            "folder_path": folder_path,
            "tags": ["context", f"agent:{agent_id}", "agent_storage"],
        })

        if "error" in result:
            return result

        return {
            "success": True,
            "file_id": result.get("file_id"),
        }

    except Exception as e:
        logger.error("set_context_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"Set context failed: {str(e)}"}


async def list_my_files_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience method to list all files created by this agent.

    This is a simplified version of list that returns just the agent's files
    with a cleaner output format.

    Inputs:
        org_id: string (required) - Organization ID
        agent_id: string (required) - Agent ID

    Returns:
        {
            files: list[dict] - Simplified file info (name, path, size, url),
            folders: list[string] - List of folders in agent namespace,
            total_count: int - Total number of files
        }
    """
    try:
        from .den_file_plugin import list_files_handler as den_list

        org_id = inputs.get("org_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, agent_id]):
            return {"error": "Missing required fields: org_id, agent_id"}

        # List all files in agent namespace
        list_result = await den_list({
            "org_id": org_id,
            "folder_path": _get_agent_path(agent_id),
            "tags": [f"agent:{agent_id}"],
        })

        if "error" in list_result:
            return list_result

        raw_files = list_result.get("files", [])

        # Simplify output and group by folder
        folders = set()
        files = []

        for f in raw_files:
            folder = f.get("folder_path", "")
            # Extract relative path from agent namespace
            base_path = _get_agent_path(agent_id)
            relative_folder = folder.replace(base_path, "").strip("/") or "root"
            folders.add(relative_folder)

            files.append({
                "name": f.get("name"),
                "folder": relative_folder,
                "size_bytes": f.get("size_bytes"),
                "url": f.get("url"),
                "created_at": f.get("created_at"),
            })

        return {
            "files": files,
            "folders": sorted(list(folders)),
            "total_count": len(files),
        }

    except Exception as e:
        logger.error("list_my_files_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"List my files failed: {str(e)}"}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "agent_save": save_handler,
    "agent_load": load_handler,
    "agent_list": list_files_handler,
    "agent_delete": delete_handler,
    "agent_search": search_handler,
    "agent_get_context": get_context_handler,
    "agent_set_context": set_context_handler,
    "agent_list_my_files": list_my_files_handler,
}

# Plugin definitions for registry
AGENT_STORAGE_PLUGIN_DEFINITIONS = [
    {
        "name": "agent_save",
        "description": "Save a file to the agent's storage namespace",
        "handler": save_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "filename": {"type": "string"},
                "content": {"type": ["string", "object"]},
                "subfolder": {"type": "string"},
                "content_type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["org_id", "agent_id", "filename", "content"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "path": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_load",
        "description": "Load a file from the agent's storage namespace",
        "handler": load_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "filename": {"type": "string"},
                "subfolder": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "filename"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "filename": {"type": "string"},
                "size_bytes": {"type": "integer"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_list",
        "description": "List files in the agent's storage namespace",
        "handler": list_files_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "subfolder": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["org_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_delete",
        "description": "Delete a file from the agent's storage namespace",
        "handler": delete_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "filename": {"type": "string"},
                "subfolder": {"type": "string"},
            },
            "required": ["org_id", "agent_id", "filename"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "deleted": {"type": "boolean"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_search",
        "description": "Search for files in the agent's namespace",
        "handler": search_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "pattern": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["org_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_get_context",
        "description": "Get the agent's persistent context/memory",
        "handler": get_context_handler,
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
                "context": {"type": ["object", "null"]},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_set_context",
        "description": "Set the agent's persistent context/memory",
        "handler": set_context_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "context": {"type": "object"},
                "merge": {"type": "boolean"},
            },
            "required": ["org_id", "agent_id", "context"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "file_id": {"type": "string"},
            },
        },
        "category": "agent_storage",
    },
    {
        "name": "agent_list_my_files",
        "description": "List all files created by this agent",
        "handler": list_my_files_handler,
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
                "files": {"type": "array"},
                "folders": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
        "category": "agent_storage",
    },
]
