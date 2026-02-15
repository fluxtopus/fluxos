# REVIEW:
# - Admin-only router but permission checks are "agents" create/view; no explicit admin guard or org ownership checks here.
# - Repeated plugin handler lookups + error handling across endpoints; could be centralized.
# - Depends on string-keyed plugin handlers ("agent_save"/"agent_load"), no interface contract enforcement.
"""
API routes for agent storage namespace operations.

Provides endpoints for agents to:
- Save/load files in their isolated namespace
- Manage persistent context
- List and search their files
- Organize files in subfolders
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail

logger = structlog.get_logger()

# Admin-only router for debugging agent storage
# Agents access storage directly via plugins, not HTTP
router = APIRouter(prefix="/api/admin/agent-storage", tags=["admin", "agent-storage"])


def get_org_id(user: AuthUser) -> str:
    """Extract organization_id from AuthUser metadata."""
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID not available")
    return org_id


# === Request/Response Models ===


class SaveFileRequest(BaseModel):
    """Request to save a file in agent namespace."""
    agent_id: str = Field(..., description="Agent ID for namespace scoping")
    filename: str = Field(..., description="Name of the file")
    content: str = Field(..., description="File content (text or base64)")
    subfolder: Optional[str] = Field(None, description="Subfolder within agent namespace")
    content_type: Optional[str] = Field(None, description="MIME type of the file")
    tags: Optional[List[str]] = Field(None, description="Tags for the file")


class LoadFileRequest(BaseModel):
    """Request to load a file from agent namespace."""
    agent_id: str = Field(..., description="Agent ID for namespace scoping")
    filename: str = Field(..., description="Name of the file")
    subfolder: Optional[str] = Field(None, description="Subfolder within agent namespace")


class ListFilesRequest(BaseModel):
    """Request to list files in agent namespace."""
    agent_id: str = Field(..., description="Agent ID for namespace scoping")
    subfolder: Optional[str] = Field(None, description="Subfolder to list")
    pattern: Optional[str] = Field(None, description="Filename pattern (glob)")


class ContextRequest(BaseModel):
    """Request for context operations."""
    agent_id: str = Field(..., description="Agent ID for namespace scoping")
    key: str = Field(..., description="Context key")
    value: Optional[Any] = Field(None, description="Context value (for set)")


class FileResponse(BaseModel):
    """Response for a single file."""
    filename: str
    path: str
    content_type: Optional[str]
    size: int
    created_at: Optional[datetime]
    tags: List[str] = []


class FileContentResponse(BaseModel):
    """Response for file content."""
    filename: str
    content: str
    content_type: Optional[str]
    size: int


class ContextResponse(BaseModel):
    """Response for context operations."""
    key: str
    value: Any
    exists: bool


class AgentStorageStatsResponse(BaseModel):
    """Response for agent storage statistics."""
    agent_id: str
    total_files: int
    total_size_bytes: int
    folders: List[str]
    context_keys: List[str]


# === Plugin Integration ===


async def get_storage_plugin():
    """Get the agent storage plugin handlers."""
    from src.plugins.agent_storage_plugin import PLUGIN_HANDLERS
    return PLUGIN_HANDLERS


# === Endpoints ===


@router.post("/save", response_model=FileResponse)
async def save_file(
    request: SaveFileRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "create")),
):
    """
    Save a file to the agent's storage namespace.

    Files are automatically scoped to /agents/{agent_id}/.
    """
    handlers = await get_storage_plugin()

    try:
        result = await handlers["agent_save"]({
            "agent_id": request.agent_id,
            "filename": request.filename,
            "content": request.content,
            "subfolder": request.subfolder,
            "content_type": request.content_type,
            "tags": request.tags,
            "org_id": get_org_id(user),
        })

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return FileResponse(
            filename=result.get("filename", request.filename),
            path=result.get("path", ""),
            content_type=result.get("content_type"),
            size=result.get("size", 0),
            created_at=result.get("created_at"),
            tags=result.get("tags", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_file_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to save file: {str(e)}"))


@router.post("/load", response_model=FileContentResponse)
async def load_file(
    request: LoadFileRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "view")),
):
    """
    Load a file from the agent's storage namespace.
    """
    handlers = await get_storage_plugin()

    try:
        result = await handlers["agent_load"]({
            "agent_id": request.agent_id,
            "filename": request.filename,
            "subfolder": request.subfolder,
            "org_id": get_org_id(user),
        })

        if result.get("error"):
            if result.get("error") == "File not found":
                raise HTTPException(status_code=404, detail="File not found")
            raise HTTPException(status_code=400, detail=result.get("error", "Load failed"))

        return FileContentResponse(
            filename=result.get("filename", request.filename),
            content=result.get("content", ""),
            content_type=result.get("content_type"),
            size=result.get("size", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("load_file_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to load file: {str(e)}"))


@router.post("/list", response_model=List[FileResponse])
async def list_files(
    request: ListFilesRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "view")),
):
    """
    List files in the agent's storage namespace.
    """
    handlers = await get_storage_plugin()

    try:
        result = await handlers["agent_list"]({
            "agent_id": request.agent_id,
            "subfolder": request.subfolder,
            "pattern": request.pattern,
            "org_id": get_org_id(user),
        })

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("error", "List failed"))

        files = result.get("files", [])
        return [
            FileResponse(
                filename=f.get("name", ""),
                path=f.get("path", ""),
                content_type=f.get("content_type"),
                size=f.get("size", 0),
                created_at=f.get("created_at"),
                tags=f.get("tags", []),
            )
            for f in files
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_files_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to list files: {str(e)}"))


@router.post("/delete")
async def delete_file(
    request: LoadFileRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "create")),
):
    """
    Delete a file from the agent's storage namespace.
    """
    handlers = await get_storage_plugin()

    try:
        result = await handlers["agent_delete"]({
            "agent_id": request.agent_id,
            "filename": request.filename,
            "subfolder": request.subfolder,
            "org_id": get_org_id(user),
        })

        if result.get("error"):
            if result.get("error") == "File not found":
                raise HTTPException(status_code=404, detail="File not found")
            raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))

        return {"success": True, "deleted": request.filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_file_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to delete file: {str(e)}"))


@router.post("/context/get", response_model=ContextResponse)
async def get_context(
    request: ContextRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "view")),
):
    """
    Get a context value from the agent's persistent storage.
    """
    handlers = await get_storage_plugin()

    try:
        result = await handlers["agent_get_context"]({
            "agent_id": request.agent_id,
            "org_id": get_org_id(user),
        })

        # Plugin returns {"context": {...}}, extract the specific key
        full_context = result.get("context") or {}
        # Remove internal metadata keys
        value = full_context.get(request.key) if request.key not in ("_agent_id", "_updated_at") else None

        return ContextResponse(
            key=request.key,
            value=value,
            exists=value is not None,
        )

    except Exception as e:
        logger.error("get_context_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to get context: {str(e)}"))


@router.post("/context/set", response_model=ContextResponse)
async def set_context(
    request: ContextRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "create")),
):
    """
    Set a context value in the agent's persistent storage.

    Uses merge mode to update a single key without overwriting other context data.
    """
    handlers = await get_storage_plugin()

    try:
        # Wrap key-value into context dict and use merge mode
        result = await handlers["agent_set_context"]({
            "agent_id": request.agent_id,
            "context": {request.key: request.value},
            "merge": True,
            "org_id": get_org_id(user),
        })

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("error", "Set context failed"))

        return ContextResponse(
            key=request.key,
            value=request.value,
            exists=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("set_context_failed", error=str(e), agent_id=request.agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to set context: {str(e)}"))


@router.get("/{agent_id}/stats", response_model=AgentStorageStatsResponse)
async def get_agent_storage_stats(
    agent_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("agents", "view")),
):
    """
    Get storage statistics for an agent.
    """
    handlers = await get_storage_plugin()

    try:
        # List all files to compute stats
        result = await handlers["agent_list"]({
            "agent_id": agent_id,
            "org_id": get_org_id(user),
        })

        files = result.get("files", [])

        # Compute stats
        total_size = sum(f.get("size", 0) for f in files)
        folders = set()
        for f in files:
            path = f.get("path", "")
            if "/" in path:
                folder = "/".join(path.split("/")[:-1])
                folders.add(folder)

        # Get context keys
        context_result = await handlers["agent_load"]({
            "agent_id": agent_id,
            "filename": "_context.json",
            "subfolder": "context",
            "org_id": get_org_id(user),
        })

        context_keys = []
        if context_result.get("success"):
            import json
            try:
                context_data = json.loads(context_result.get("content", "{}"))
                context_keys = list(context_data.keys())
            except json.JSONDecodeError:
                pass

        return AgentStorageStatsResponse(
            agent_id=agent_id,
            total_files=len(files),
            total_size_bytes=total_size,
            folders=list(folders),
            context_keys=context_keys,
        )

    except Exception as e:
        logger.error("get_stats_failed", error=str(e), agent_id=agent_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to get stats: {str(e)}"))
