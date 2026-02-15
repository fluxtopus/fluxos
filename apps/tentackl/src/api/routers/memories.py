"""
# REVIEW:
# - Uses global database + memory_use_cases injection; fallback instantiation makes lifecycle unclear.
# - Several response models use mutable defaults (tags/extended_data/metadata), risking shared state in Pydantic v1.
API routes for Memory Service.

Provides endpoints for:
- Creating memories
- Retrieving memories by ID or key
- Searching memories with filters
- Updating memories (creating new versions)
- Deleting memories (soft delete)
- Getting version history
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.interfaces.database import Database
from src.application.memory import MemoryUseCases
from src.infrastructure.memory import build_memory_use_cases
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryQuery,
    MemoryScopeEnum,
    MemoryNotFoundError,
    MemoryPermissionDeniedError,
    MemoryValidationError,
    MemoryDuplicateKeyError,
    MemoryVersionCollisionError,
)


logger = structlog.get_logger()

router = APIRouter(prefix="/api/memories", tags=["memories"])

# Database instance (injected at startup by app.py)
database: Optional[Database] = None

# Singleton MemoryUseCases (injected at startup by app.py)
memory_use_cases: Optional[MemoryUseCases] = None


def get_database() -> Database:
    """Get database instance."""
    if database is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


def _get_memory_use_cases() -> MemoryUseCases:
    """Get the injected use cases or fall back to creating them."""
    if memory_use_cases is not None:
        return memory_use_cases
    db = get_database()
    return build_memory_use_cases(db)


# === Request Models ===


class CreateMemoryRequest(BaseModel):
    """Request to create a new memory."""
    key: str
    title: str
    body: str
    scope: Optional[str] = "organization"
    scope_value: Optional[str] = None
    topic: Optional[str] = None
    tags: Optional[List[str]] = None
    content_type: Optional[str] = "text"
    extended_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateMemoryRequest(BaseModel):
    """Request to update an existing memory."""
    body: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    topic: Optional[str] = None
    extended_data: Optional[Dict[str, Any]] = None
    change_summary: Optional[str] = None


# === Response Models ===


class MemoryResponse(BaseModel):
    """Response model for a single memory."""
    id: str
    key: str
    title: str
    body: str
    scope: str
    topic: Optional[str] = None
    tags: List[str] = []
    version: int
    extended_data: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SearchMemoriesResponse(BaseModel):
    """Response model for memory search."""
    memories: List[MemoryResponse]
    total_count: int
    query_time_ms: int


class VersionHistoryItem(BaseModel):
    """A single version history entry."""
    version: int
    body: str
    extended_data: Dict[str, Any] = {}
    change_summary: Optional[str] = None
    changed_by: Optional[str] = None
    changed_by_agent: bool = False
    created_at: Optional[str] = None


# === Endpoints ===


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: CreateMemoryRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "create")),
):
    """
    Create a new memory.

    The memory is stored with organizational isolation and versioning.
    The organization_id is extracted from the authenticated user's metadata.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    # Convert scope string to enum
    try:
        scope_enum = MemoryScopeEnum(request.scope or "organization")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope: {request.scope}. Must be one of: organization, user, agent, topic"
        )

    # Validate and default scope_value based on scope
    scope_value = request.scope_value
    if scope_enum == MemoryScopeEnum.USER:
        if scope_value is None:
            scope_value = user.id
        elif scope_value != user.id:
            raise HTTPException(
                status_code=400,
                detail="User-scoped memories must belong to the authenticated user"
            )
    elif scope_enum == MemoryScopeEnum.AGENT:
        if scope_value is None:
            raise HTTPException(
                status_code=400,
                detail="Agent-scoped memories require a scope_value (agent ID)"
            )
    elif scope_enum in (MemoryScopeEnum.ORGANIZATION, MemoryScopeEnum.TOPIC):
        scope_value = None

    use_cases = _get_memory_use_cases()

    create_request = MemoryCreateRequest(
        organization_id=org_id,
        key=request.key,
        title=request.title,
        body=request.body,
        scope=scope_enum,
        scope_value=scope_value,
        topic=request.topic,
        tags=request.tags,
        content_type=request.content_type or "text",
        extended_data=request.extended_data,
        metadata=request.metadata,
        created_by_user_id=user.id,
        created_by_agent_id=None,
    )

    try:
        result = await use_cases.store(create_request)
    except MemoryDuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail=f"Memory with key '{request.key}' already exists"
        )
    except MemoryValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))

    logger.info(
        "Memory created via API",
        memory_id=result.id,
        key=result.key,
        organization_id=org_id,
        user_id=user.id,
    )

    return MemoryResponse(
        id=result.id,
        key=result.key,
        title=result.title,
        body=result.body,
        scope=result.scope,
        topic=result.topic,
        tags=result.tags,
        version=result.version,
        extended_data=result.extended_data,
        metadata=result.metadata,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: UUID,
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "view")),
):
    """
    Get a memory by ID.

    Returns the memory if it exists and belongs to the user's organization.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    use_cases = _get_memory_use_cases()

    try:
        result = await use_cases.retrieve(str(memory_id), org_id, user_id=user.id)
    except MemoryPermissionDeniedError:
        raise HTTPException(status_code=403, detail="Access denied")
    except MemoryValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))

    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")

    return MemoryResponse(
        id=result.id,
        key=result.key,
        title=result.title,
        body=result.body,
        scope=result.scope,
        topic=result.topic,
        tags=result.tags,
        version=result.version,
        extended_data=result.extended_data,
        metadata=result.metadata,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.get("", response_model=SearchMemoriesResponse)
async def search_memories(
    text: Optional[str] = Query(None, description="Text for semantic search"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    key: Optional[str] = Query(None, description="Filter by exact key"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "view")),
):
    """
    Search memories with filters.

    Returns a paginated list of memories matching the query parameters.
    All queries are scoped to the user's organization.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    # Parse comma-separated tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Convert scope string to enum if provided
    scope_enum = None
    if scope:
        try:
            scope_enum = MemoryScopeEnum(scope)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope: {scope}. Must be one of: organization, user, agent, topic"
            )

    use_cases = _get_memory_use_cases()

    query = MemoryQuery(
        organization_id=org_id,
        text=text,
        key=key,
        scope=scope_enum,
        topic=topic,
        tags=tag_list,
        limit=limit,
        offset=offset,
        requesting_user_id=user.id,
    )

    response = await use_cases.search(query)

    memories = [
        MemoryResponse(
            id=m.id,
            key=m.key,
            title=m.title,
            body=m.body,
            scope=m.scope,
            topic=m.topic,
            tags=m.tags,
            version=m.version,
            extended_data=m.extended_data,
            metadata=m.metadata,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in response.memories
    ]

    return SearchMemoriesResponse(
        memories=memories,
        total_count=response.total_count,
        query_time_ms=response.query_time_ms,
    )


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "update")),
):
    """
    Update a memory.

    Creates a new version if the body is changed.
    Returns the updated memory.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    use_cases = _get_memory_use_cases()

    update_request = MemoryUpdateRequest(
        body=request.body,
        title=request.title,
        tags=request.tags,
        topic=request.topic,
        extended_data=request.extended_data,
        change_summary=request.change_summary,
        changed_by=user.id,
        changed_by_agent=False,
    )

    try:
        result = await use_cases.update(
            str(memory_id), org_id, update_request, user_id=user.id,
        )
    except MemoryNotFoundError:
        raise HTTPException(status_code=404, detail="Memory not found")
    except MemoryPermissionDeniedError:
        raise HTTPException(status_code=403, detail="Access denied")
    except MemoryVersionCollisionError:
        raise HTTPException(
            status_code=409,
            detail="Version conflict: memory was updated concurrently. Retry with latest version."
        )
    except MemoryValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))

    logger.info(
        "Memory updated via API",
        memory_id=result.id,
        version=result.version,
        organization_id=org_id,
        user_id=user.id,
    )

    return MemoryResponse(
        id=result.id,
        key=result.key,
        title=result.title,
        body=result.body,
        scope=result.scope,
        topic=result.topic,
        tags=result.tags,
        version=result.version,
        extended_data=result.extended_data,
        metadata=result.metadata,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "delete")),
):
    """
    Delete a memory (soft delete).

    Sets the memory status to 'deleted'. The memory can still be
    recovered if needed, but will not appear in normal searches.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    use_cases = _get_memory_use_cases()

    try:
        deleted = await use_cases.delete(str(memory_id), org_id, user_id=user.id)
    except MemoryPermissionDeniedError:
        raise HTTPException(status_code=403, detail="Access denied")
    except MemoryValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))

    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")

    logger.info(
        "Memory deleted via API",
        memory_id=str(memory_id),
        organization_id=org_id,
        user_id=user.id,
    )


@router.get("/{memory_id}/versions", response_model=List[VersionHistoryItem])
async def get_memory_versions(
    memory_id: UUID,
    limit: int = Query(20, ge=1, le=100, description="Maximum versions to return"),
    user: AuthUser = Depends(auth_middleware.require_permission("memories", "view")),
):
    """
    Get version history for a memory.

    Returns a list of all versions of the memory, ordered by version
    number descending (newest first).
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Organization ID not found in user metadata"
        )

    use_cases = _get_memory_use_cases()

    try:
        versions = await use_cases.get_version_history(
            str(memory_id), org_id, user_id=user.id, limit=limit,
        )
    except MemoryPermissionDeniedError:
        raise HTTPException(status_code=403, detail="Access denied")
    except MemoryValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))

    if not versions:
        # Check if memory exists (permission already checked above via get_version_history)
        try:
            memory = await use_cases.retrieve(str(memory_id), org_id, user_id=user.id)
        except MemoryPermissionDeniedError:
            raise HTTPException(status_code=403, detail="Access denied")
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

    return [
        VersionHistoryItem(
            version=v["version"],
            body=v["body"],
            extended_data=v.get("extended_data", {}),
            change_summary=v.get("change_summary"),
            changed_by=v.get("changed_by"),
            changed_by_agent=v.get("changed_by_agent", False),
            created_at=v.get("created_at"),
        )
        for v in versions
    ]
