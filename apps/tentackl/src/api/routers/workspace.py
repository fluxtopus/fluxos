"""
# REVIEW:
# - Exposes Mongo-style query operators directly; requires careful validation to prevent expensive/unsafe queries.
# - org_id is extracted from user metadata; no fallback if metadata missing (many endpoints will 400).
API routes for workspace objects.

Provides endpoints for:
- CRUD operations on flexible objects (events, contacts, custom types)
- Query with MongoDB-style operators
- Full-text search
- Type schema management
"""

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import structlog

from src.application.workspace import WorkspaceUseCases
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.infrastructure.workspace import WorkspaceServiceAdapter
from src.interfaces.database import Database


logger = structlog.get_logger()

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


# Database instance (injected at startup)
database: Optional[Database] = None


def get_database() -> Database:
    """Get database instance."""
    if database is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


def get_workspace_use_cases(
    db: Database = Depends(get_database),
) -> WorkspaceUseCases:
    """Provide application-layer workspace use cases."""
    return WorkspaceUseCases(workspace_ops=WorkspaceServiceAdapter(db))


def get_org_id(user: AuthUser) -> str:
    """Extract organization_id from AuthUser metadata."""
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID not available")
    return org_id


# === Request/Response Models ===


class CreateObjectRequest(BaseModel):
    """Request to create a workspace object."""
    type: str = Field(..., description="Object type (e.g., 'event', 'contact')")
    data: Dict[str, Any] = Field(..., description="Object data")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags for filtering")


class UpdateObjectRequest(BaseModel):
    """Request to update a workspace object."""
    data: Dict[str, Any] = Field(..., description="Data to update")
    merge: bool = Field(default=True, description="Merge with existing data (True) or replace (False)")


class QueryRequest(BaseModel):
    """Request to query workspace objects."""
    type: Optional[str] = Field(default=None, description="Filter by type")
    where: Optional[Dict[str, Any]] = Field(default=None, description="MongoDB-style query operators")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags (all must match)")
    created_by_id: Optional[str] = Field(default=None, description="Filter by creator ID (e.g., task UUID)")
    created_by_type: Optional[str] = Field(default=None, description="Filter by creator type (e.g., 'task')")
    order_by: Optional[str] = Field(default=None, description="Field to order by (e.g., 'data.title', 'created_at')")
    order_desc: bool = Field(default=False, description="Order descending")
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ShortcutQueryRequest(BaseModel):
    """Request for ultra-fast shortcut queries."""
    object_type: Optional[str] = Field(default=None, description="Object type (e.g., 'event', 'contact')")
    created_by_id: Optional[str] = Field(default=None, description="Filter by creator ID (e.g., task UUID)")
    created_by_type: Optional[str] = Field(default=None, description="Filter by creator type (e.g., 'task')")
    where: Optional[Dict[str, Any]] = Field(default=None, description="MongoDB-style query operators")
    limit: int = Field(default=20, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ShortcutQueryResponse(BaseModel):
    """Response for shortcut queries with timing metrics."""
    object_type: str
    data: List[Dict[str, Any]]
    total_count: int
    query_time_ms: int
    has_more: bool = Field(default=False, description="Whether more results are available beyond this page")


class ShortcutSearchRequest(BaseModel):
    """Request for ultra-fast shortcut text search."""
    query: str = Field(..., description="Search query text")
    object_type: Optional[str] = Field(default=None, description="Filter by object type")
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SearchRequest(BaseModel):
    """Request to search workspace objects."""
    query: str = Field(..., description="Search query")
    type: Optional[str] = Field(default=None, description="Filter by type")
    limit: int = Field(default=50, ge=1, le=200)


class RegisterTypeRequest(BaseModel):
    """Request to register a type schema."""
    type_name: str = Field(..., description="Type name")
    schema: Dict[str, Any] = Field(..., description="JSON Schema definition")
    is_strict: bool = Field(default=False, description="Reject invalid data (True) or warn only (False)")


class ObjectResponse(BaseModel):
    """Response for a workspace object."""
    id: str
    org_id: str
    type: str
    data: Dict[str, Any]
    tags: List[str]
    created_by_type: Optional[str]
    created_by_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    warnings: Optional[List[str]] = Field(default=None)

    model_config = {"from_attributes": True}


class TypeSchemaResponse(BaseModel):
    """Response for a type schema."""
    type_name: str
    schema: Dict[str, Any]
    is_strict: bool


class InferSchemaResponse(BaseModel):
    """Response for inferred schema."""
    type: str
    sample_size: int
    fields: Dict[str, Dict[str, Any]]


# === Object CRUD Endpoints ===


@router.post("/objects", response_model=ObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_object(
    request: CreateObjectRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "create")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Create a new workspace object.

    Objects can be any type: events, contacts, notes, custom types.
    Data is stored as flexible JSONB and searchable via full-text search.
    """
    org_id = get_org_id(user)

    try:
        result = await use_cases.create_object(
            org_id=org_id,
            type=request.type,
            data=request.data,
            created_by_type="user",
            created_by_id=user.id,
            tags=request.tags,
        )
        return ObjectResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


@router.get("/objects/{object_id}", response_model=ObjectResponse)
async def get_object(
    object_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """Get a workspace object by ID."""
    org_id = get_org_id(user)

    result = await use_cases.get_object(org_id=org_id, object_id=object_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")
    return ObjectResponse(**result)


@router.patch("/objects/{object_id}", response_model=ObjectResponse)
async def update_object(
    object_id: str,
    request: UpdateObjectRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "create")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Update a workspace object.

    By default, merges new data with existing data.
    Set merge=False to replace entirely.
    """
    org_id = get_org_id(user)

    try:
        result = await use_cases.update_object(
            org_id=org_id,
            object_id=object_id,
            data=request.data,
            merge=request.merge,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")
        return ObjectResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))


@router.delete("/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object(
    object_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "create")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """Delete a workspace object."""
    org_id = get_org_id(user)

    deleted = await use_cases.delete_object(org_id=org_id, object_id=object_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")


# === Query & Search Endpoints ===


@router.post("/objects/query", response_model=List[ObjectResponse])
async def query_objects(
    request: QueryRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Query workspace objects with filters.

    Supports MongoDB-style operators:
    - $eq, $ne: equality
    - $gt, $gte, $lt, $lte: comparison
    - $in, $nin: list membership
    - $exists: field exists
    - $regex: pattern match

    Example:
    ```json
    {
      "type": "event",
      "where": {
        "status": {"$eq": "confirmed"},
        "start_date": {"$gte": "2026-01-01"}
      },
      "order_by": "data.start_date",
      "limit": 50
    }
    ```
    """
    org_id = get_org_id(user)

    results = await use_cases.query_objects(
        org_id=org_id,
        type=request.type,
        where=request.where,
        tags=request.tags,
        order_by=request.order_by,
        order_desc=request.order_desc,
        limit=request.limit,
        offset=request.offset,
        created_by_id=request.created_by_id,
        created_by_type=request.created_by_type,
    )
    return [ObjectResponse(**r) for r in results]


@router.post("/shortcuts/query", response_model=ShortcutQueryResponse)
async def shortcut_query(
    request: ShortcutQueryRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Ultra-fast query for workspace shortcuts.

    Returns wrapped response with timing metrics.
    Used by #calendar, #contacts, and other workspace shortcuts
    for instant query results without LLM involvement.

    Performance target: <200ms total, <50ms query time.
    """
    start_time = time.perf_counter()
    org_id = get_org_id(user)

    results = await use_cases.query_objects(
        org_id=org_id,
        type=request.object_type,
        where=request.where,
        limit=request.limit,
        offset=request.offset,
        created_by_id=request.created_by_id,
        created_by_type=request.created_by_type,
    )

    query_time_ms = int((time.perf_counter() - start_time) * 1000)

    return ShortcutQueryResponse(
        object_type=request.object_type or "mixed",
        data=[{"id": r["id"], "data": r["data"]} for r in results],
        total_count=len(results),
        query_time_ms=query_time_ms,
        has_more=len(results) == request.limit,
    )


@router.post("/shortcuts/search", response_model=ShortcutQueryResponse)
async def shortcut_search(
    request: ShortcutSearchRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Ultra-fast full-text search for workspace shortcuts.

    Returns wrapped response with timing metrics.
    Used by #calendar, #contacts shortcuts when searching by text
    (e.g., "#calendar toronto raptors").

    Performance target: <200ms total.
    """
    start_time = time.perf_counter()
    org_id = get_org_id(user)

    results = await use_cases.search_objects(
        org_id=org_id,
        query=request.query,
        type=request.object_type,
        limit=request.limit,
        offset=request.offset,
    )

    query_time_ms = int((time.perf_counter() - start_time) * 1000)

    return ShortcutQueryResponse(
        object_type=request.object_type or "mixed",
        data=[{"id": r["id"], "data": r["data"]} for r in results],
        total_count=len(results),
        query_time_ms=query_time_ms,
        has_more=len(results) == request.limit,
    )


@router.post("/objects/search", response_model=List[ObjectResponse])
async def search_objects(
    request: SearchRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Full-text search across workspace objects.

    Searches common text fields: title, name, description, summary, email, content, notes.
    Results are ranked by relevance.
    """
    org_id = get_org_id(user)

    results = await use_cases.search_objects(
        org_id=org_id,
        query=request.query,
        type=request.type,
        limit=request.limit,
    )
    return [ObjectResponse(**r) for r in results]


# === Convenience GET Endpoints ===


@router.get("/events", response_model=List[ObjectResponse])
async def list_events(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """List all events (shortcut for query type=event)."""
    org_id = get_org_id(user)

    results = await use_cases.query_objects(
        org_id=org_id,
        type="event",
        limit=limit,
        offset=offset,
    )
    return [ObjectResponse(**r) for r in results]


@router.get("/contacts", response_model=List[ObjectResponse])
async def list_contacts(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """List all contacts (shortcut for query type=contact)."""
    org_id = get_org_id(user)

    results = await use_cases.query_objects(
        org_id=org_id,
        type="contact",
        limit=limit,
        offset=offset,
    )
    return [ObjectResponse(**r) for r in results]


# === Type Schema Endpoints ===


@router.post("/types", response_model=TypeSchemaResponse, status_code=status.HTTP_201_CREATED)
async def register_type_schema(
    request: RegisterTypeRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "create")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Register a JSON Schema for a type.

    When a schema is registered:
    - If is_strict=True: Objects that don't match are rejected
    - If is_strict=False: Objects that don't match get warnings

    Example schema:
    ```json
    {
      "type_name": "event",
      "schema": {
        "type": "object",
        "required": ["title", "start"],
        "properties": {
          "title": {"type": "string"},
          "start": {"type": "string", "format": "date-time"},
          "end": {"type": "string", "format": "date-time"},
          "location": {"type": "string"}
        }
      },
      "is_strict": false
    }
    ```
    """
    org_id = get_org_id(user)

    result = await use_cases.register_type_schema(
        org_id=org_id,
        type_name=request.type_name,
        schema=request.schema,
        is_strict=request.is_strict,
    )
    return TypeSchemaResponse(**result)


@router.get("/types", response_model=List[TypeSchemaResponse])
async def list_types(
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """List all registered type schemas for the organization."""
    org_id = get_org_id(user)

    results = await use_cases.list_type_schemas(org_id=org_id)
    return [TypeSchemaResponse(**r) for r in results]


@router.get("/types/{type_name}/schema", response_model=TypeSchemaResponse)
async def get_type_schema(
    type_name: str,
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """Get the registered schema for a type."""
    org_id = get_org_id(user)

    result = await use_cases.get_type_schema(org_id=org_id, type_name=type_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Schema not found for type: {type_name}")
    return TypeSchemaResponse(**result)


@router.get("/types/{type_name}/infer", response_model=InferSchemaResponse)
async def infer_type_schema(
    type_name: str,
    sample_size: int = Query(default=100, ge=1, le=1000),
    user: AuthUser = Depends(auth_middleware.require_permission("workspace", "view")),
    use_cases: WorkspaceUseCases = Depends(get_workspace_use_cases),
):
    """
    Infer schema from existing objects of a type.

    Analyzes up to sample_size objects to determine:
    - Which fields are commonly present
    - What types each field contains

    Useful for discovering the actual structure of unschema'd data.
    """
    org_id = get_org_id(user)

    result = await use_cases.infer_type_schema(
        org_id=org_id,
        type_name=type_name,
        sample_size=sample_size,
    )
    return InferSchemaResponse(**result)
