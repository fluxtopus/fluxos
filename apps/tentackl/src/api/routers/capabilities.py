"""Capabilities API endpoints for the unified capabilities system.

This module provides endpoints to manage AgentCapability records from the
capabilities_agents table - the unified source of truth for agent definitions.
"""

# REVIEW:
# - Overlaps with /api/agents endpoints (capability discovery/search), which can diverge.
# - Global database injection pattern repeated here; tight coupling to app startup.

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.params import Depends as DependsParam
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
import structlog
import yaml

from src.application.capabilities import (
    CapabilityConflict,
    CapabilityForbidden,
    CapabilityNotFound,
    CapabilityUseCases,
    CapabilityValidationError,
)
from src.application.capabilities import use_cases as capability_use_cases
from src.infrastructure.capabilities.sql_repository import SqlCapabilityRepository
from src.interfaces.database import Database
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail

logger = structlog.get_logger()

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])

# Global database instance (injected at app startup)
database: Optional[Database] = None


# Pydantic models for responses


class CapabilityListItem(BaseModel):
    """Summary of a capability for list views."""
    id: UUID
    agent_type: str
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    task_type: str
    is_system: bool
    is_active: bool
    organization_id: Optional[UUID] = None
    # Management fields
    version: int
    is_latest: bool
    tags: List[str] = []
    # Analytics fields
    usage_count: int
    success_count: int
    failure_count: int
    last_used_at: Optional[datetime] = None
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Permission indicator
    can_edit: bool = False

    model_config = ConfigDict(from_attributes=True)


class CapabilitiesListResponse(BaseModel):
    """Response for list capabilities endpoint."""
    capabilities: List[CapabilityListItem]
    count: int
    total: int
    limit: int
    offset: int


# Dependency injection


async def get_database() -> Database:
    """Get the database instance."""
    if database is None:
        raise HTTPException(
            status_code=503,
            detail="Database not initialized"
        )
    return database


def get_capability_use_cases(
    db: Database = Depends(get_database),
) -> CapabilityUseCases:
    """Provide application-layer capability use cases."""
    return CapabilityUseCases(repository=SqlCapabilityRepository(db))


def _resolve_capability_use_cases(
    use_cases: CapabilityUseCases,
    db: Database,
) -> CapabilityUseCases:
    """Resolve use cases for direct (non-FastAPI) calls in tests."""
    if isinstance(use_cases, DependsParam):
        if db is None:
            raise HTTPException(status_code=503, detail="Database not initialized")
        return CapabilityUseCases(repository=SqlCapabilityRepository(db))
    return use_cases


# Endpoints


@router.get("/agents", response_model=CapabilitiesListResponse)
async def list_capabilities(
    domain: Optional[str] = Query(None, description="Filter by domain (content, research, analytics, etc.)"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags (matches any)"),
    include_system: bool = Query(True, description="Include system capabilities in results"),
    active_only: bool = Query(True, description="Only return active capabilities"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    List all capabilities with optional filters.

    Returns capabilities owned by the user's organization plus system capabilities.
    Supports filtering by domain, tags, and active status.

    **Filters:**
    - `domain`: Filter by capability domain (e.g., "content", "research", "analytics")
    - `tags`: Filter by tags (matches capabilities with ANY of the specified tags)
    - `include_system`: Include system-defined capabilities (default: true)
    - `active_only`: Only include active capabilities (default: true)

    **Pagination:**
    - `limit`: Maximum number of results (1-500, default: 100)
    - `offset`: Number of results to skip (default: 0)
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None

        resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
        result = await resolved_use_cases.list_capabilities(
            org_id=org_id,
            domain=domain,
            tags=tags,
            include_system=include_system,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

        capability_items = [CapabilityListItem(**cap) for cap in result["capabilities"]]

        return CapabilitiesListResponse(
            capabilities=capability_items,
            count=result["count"],
            total=result["total"],
            limit=result["limit"],
            offset=result["offset"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list capabilities", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to list capabilities: {str(e)}")
        )


# =============================================================================
# SEARCH ENDPOINT - Must be registered BEFORE /agents/{capability_id} routes
# to avoid the wildcard path parameter capturing "search"
# =============================================================================


class SearchCapabilityItem(BaseModel):
    """Search result item with similarity score."""
    id: UUID
    agent_type: str
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    task_type: str
    is_system: bool
    is_active: bool
    organization_id: Optional[UUID] = None
    version: int
    is_latest: bool
    tags: List[str] = []
    keywords: List[str] = []
    usage_count: int
    success_count: int
    failure_count: int
    last_used_at: Optional[datetime] = None
    similarity: float = 0.0  # Similarity score (0-1)
    match_type: str = "keyword"  # "semantic" or "keyword"
    can_edit: bool = False

    model_config = ConfigDict(from_attributes=True)


class SearchCapabilitiesResponse(BaseModel):
    """Response for search capabilities endpoint."""
    results: List[SearchCapabilityItem]
    count: int
    query: str
    search_type: str  # "semantic", "keyword", or "hybrid"


@router.get("/agents/search", response_model=SearchCapabilitiesResponse)
async def search_capabilities(
    query: str = Query(..., min_length=1, max_length=500, description="Search query"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags (matches any)"),
    include_system: bool = Query(True, description="Include system capabilities in results"),
    active_only: bool = Query(True, description="Only return active capabilities"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    min_similarity: float = Query(0.5, ge=0.0, le=1.0, description="Minimum similarity threshold for semantic search"),
    prefer_semantic: bool = Query(True, description="Prefer semantic search when embeddings available"),
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    Search capabilities using semantic similarity or keyword matching.

    **Search Strategy:**
    1. If embeddings are available and `prefer_semantic=true`, uses pgvector cosine
       similarity to find semantically similar capabilities.
    2. Falls back to keyword matching on name, description, agent_type, tags, and
       keywords when embeddings are not available or `prefer_semantic=false`.

    **Filters:**
    - `domain`: Filter by capability domain (content, research, analytics, etc.)
    - `tags`: Filter by tags (matches capabilities with ANY of the specified tags)
    - `include_system`: Include system-defined capabilities (default: true)
    - `active_only`: Only include active capabilities (default: true)

    **Semantic Search Parameters:**
    - `min_similarity`: Minimum cosine similarity threshold (0.0-1.0, default: 0.5)
    - `prefer_semantic`: Use semantic search when available (default: true)

    **Returns:**
    - Results sorted by relevance (similarity score descending)
    - Each result includes `similarity` score (0-1) and `match_type` ("semantic" or "keyword")
    - `search_type` indicates which strategy was used: "semantic", "keyword", or "hybrid"

    **Authorization:**
    - Returns user's organization capabilities plus system capabilities
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None

        if isinstance(use_cases, DependsParam):
            if db is None:
                raise HTTPException(status_code=503, detail="Database not initialized")

            async with db.get_session() as session:
                search_type = "keyword"
                results = []
                if prefer_semantic:
                    query_embedding = await _generate_query_embedding(query)
                    if query_embedding:
                        results = await _semantic_search(
                            session=session,
                            query_embedding=query_embedding,
                            org_id=org_id,
                            include_system=include_system,
                            active_only=active_only,
                            domain=domain,
                            tags=tags,
                            limit=limit,
                            min_similarity=min_similarity,
                        )
                        if results:
                            search_type = "semantic"
                        else:
                            results = await _keyword_search(
                                session=session,
                                query=query,
                                org_id=org_id,
                                include_system=include_system,
                                active_only=active_only,
                                domain=domain,
                                tags=tags,
                                limit=limit,
                            )
                            search_type = "keyword"
                    else:
                        results = await _keyword_search(
                            session=session,
                            query=query,
                            org_id=org_id,
                            include_system=include_system,
                            active_only=active_only,
                            domain=domain,
                            tags=tags,
                            limit=limit,
                        )
                        search_type = "keyword"
                else:
                    results = await _keyword_search(
                        session=session,
                        query=query,
                        org_id=org_id,
                        include_system=include_system,
                        active_only=active_only,
                        domain=domain,
                        tags=tags,
                        limit=limit,
                    )
                    search_type = "keyword"

            result = {
                "results": results,
                "count": len(results),
                "query": query,
                "search_type": search_type,
            }
        else:
            resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
            result = await resolved_use_cases.search_capabilities(
                query=query,
                org_id=org_id,
                include_system=include_system,
                active_only=active_only,
                domain=domain,
                tags=tags,
                limit=limit,
                min_similarity=min_similarity,
                prefer_semantic=prefer_semantic,
            )

        search_results = []
        for r in result["results"]:
            can_edit = (
                not r["is_system"]
                and org_id is not None
                and r["organization_id"] is not None
                and str(r["organization_id"]) == str(org_id)
            )

            search_results.append(
                SearchCapabilityItem(
                    id=r["id"],
                    agent_type=r["agent_type"],
                    name=r["name"],
                    description=r["description"],
                    domain=r["domain"],
                    task_type=r["task_type"],
                    is_system=r["is_system"],
                    is_active=r["is_active"],
                    organization_id=r["organization_id"],
                    version=r["version"],
                    is_latest=r["is_latest"],
                    tags=r["tags"],
                    keywords=r["keywords"],
                    usage_count=r["usage_count"],
                    success_count=r["success_count"],
                    failure_count=r["failure_count"],
                    last_used_at=r["last_used_at"],
                    similarity=r["similarity"],
                    match_type=r["match_type"],
                    can_edit=can_edit,
                )
            )

        return SearchCapabilitiesResponse(
            results=search_results,
            count=result["count"],
            query=result["query"],
            search_type=result["search_type"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to search capabilities", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to search capabilities: {str(e)}")
        )


# Request/Response models for Create endpoint

class CreateCapabilityRequest(BaseModel):
    """Request model for creating a user-defined capability from YAML spec."""
    spec_yaml: str = Field(..., description="YAML specification for the capability")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags for categorization")

    @field_validator('spec_yaml')
    @classmethod
    def validate_yaml_parseable(cls, v: str) -> str:
        """Ensure the YAML is parseable."""
        try:
            yaml.safe_load(v)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {str(e)}")
        return v


class CapabilityDetail(BaseModel):
    """Full capability details for create/get responses."""
    id: UUID
    agent_type: str
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    task_type: str
    system_prompt: str
    inputs_schema: Dict[str, Any] = {}
    outputs_schema: Dict[str, Any] = {}
    examples: List[Dict[str, Any]] = []
    execution_hints: Dict[str, Any] = {}
    is_system: bool
    is_active: bool
    organization_id: Optional[UUID] = None
    # Management fields
    version: int
    is_latest: bool
    created_by: Optional[UUID] = None
    tags: List[str] = []
    spec_yaml: Optional[str] = None
    # Analytics fields
    usage_count: int
    success_count: int
    failure_count: int
    last_used_at: Optional[datetime] = None
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Permission indicator
    can_edit: bool = False

    model_config = ConfigDict(from_attributes=True)


class CreateCapabilityResponse(BaseModel):
    """Response for create capability endpoint."""
    capability: CapabilityDetail
    message: str = "Capability created successfully"


@router.post("/agents", response_model=CreateCapabilityResponse, status_code=201)
async def create_capability(
    request: CreateCapabilityRequest,
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    Create a user-defined capability from a YAML specification.

    The YAML format matches the seeded agent format with fields:
    - **agent_type** (required): Unique identifier for the capability (e.g., "my_summarizer")
    - **name** (optional): Display name for the capability
    - **description** (optional): Description of what the capability does
    - **domain** (optional): Domain category (content, research, analytics, etc.)
    - **task_type** (optional): Type of task (general, reasoning, creative, web_research, analysis)
    - **system_prompt** (required): The prompt that defines the capability's behavior
    - **inputs** (required): Input schema defining expected inputs
    - **outputs** (optional): Output schema defining expected outputs
    - **examples** (optional): Example usages
    - **execution_hints** (optional): Hints for the planner (deterministic, speed, cost, etc.)

    The capability is created with:
    - is_system=false (user-defined)
    - organization_id from the authenticated user
    - created_by set to the current user's ID
    - version=1, is_latest=true

    **Validation:**
    - agent_type must be unique within the user's organization
    - Required fields: agent_type, system_prompt, inputs
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None
        resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
        result = await resolved_use_cases.create_capability(
            spec_yaml=request.spec_yaml,
            tags=request.tags,
            org_id=org_id,
            user_id=current_user.id,
        )

        return CreateCapabilityResponse(
            capability=CapabilityDetail(**result["capability"]),
            message=result["message"],
        )
    except CapabilityValidationError as exc:
        detail = exc.args[0] if exc.args else str(exc)
        raise HTTPException(status_code=400, detail=detail)
    except CapabilityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CapabilityForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as e:
        logger.error("Failed to create capability", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to create capability: {str(e)}")
        )


class UpdateCapabilityRequest(BaseModel):
    """Request model for updating a user-defined capability."""
    spec_yaml: Optional[str] = Field(None, description="Updated YAML specification")
    tags: Optional[List[str]] = Field(None, description="Updated tags for categorization")
    is_active: Optional[bool] = Field(None, description="Whether the capability is active")

    @field_validator('spec_yaml')
    @classmethod
    def validate_yaml_parseable(cls, v: Optional[str]) -> Optional[str]:
        """Ensure the YAML is parseable if provided."""
        if v is not None:
            try:
                yaml.safe_load(v)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML: {str(e)}")
        return v


class UpdateCapabilityResponse(BaseModel):
    """Response for update capability endpoint."""
    capability: CapabilityDetail
    message: str = "Capability updated successfully"
    version_created: bool = False  # True if a new version was created


@router.put("/agents/{capability_id}", response_model=UpdateCapabilityResponse)
async def update_capability(
    capability_id: UUID,
    request: UpdateCapabilityRequest,
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    Update a user-defined capability.

    **Authorization:**
    - Only capabilities owned by the user's organization can be updated
    - System capabilities cannot be modified

    **Update Behavior:**
    - When spec_yaml is changed, a new version is created (version increments, old version marked is_latest=false)
    - When only tags or is_active are changed, the existing record is updated in place
    - Empty updates (no changes) return the existing capability unchanged

    **Fields that can be updated:**
    - `spec_yaml`: The YAML specification (triggers versioning)
    - `tags`: Tags for categorization
    - `is_active`: Whether the capability is active
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None
        resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
        result = await resolved_use_cases.update_capability(
            capability_id=capability_id,
            spec_yaml=request.spec_yaml,
            tags=request.tags,
            is_active=request.is_active,
            org_id=org_id,
            user_id=current_user.id,
        )

        return UpdateCapabilityResponse(
            capability=CapabilityDetail(**result["capability"]),
            message=result["message"],
            version_created=result["version_created"],
        )
    except CapabilityValidationError as exc:
        detail = exc.args[0] if exc.args else str(exc)
        raise HTTPException(status_code=400, detail=detail)
    except CapabilityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CapabilityForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as e:
        logger.error("Failed to update capability", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to update capability: {str(e)}")
        )


class GetCapabilityResponse(BaseModel):
    """Response for get single capability endpoint."""
    capability: CapabilityDetail


@router.get("/agents/{capability_id}", response_model=GetCapabilityResponse)
async def get_capability(
    capability_id: UUID,
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    Get a single capability with full details.

    Returns the capability with all fields including spec_yaml, usage stats,
    execution hints, and input/output schemas.

    **Authorization:**
    - System capabilities are readable by all authenticated users
    - User-defined capabilities are readable by users in the same organization

    **Returns:**
    - 200 with full capability details
    - 404 if capability not found
    - 403 if user doesn't have permission to view the capability
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None
        resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
        result = await resolved_use_cases.get_capability(capability_id=capability_id, org_id=org_id)

        logger.info(
            "Retrieved capability",
            capability_id=str(result["capability"]["id"]),
            agent_type=result["capability"]["agent_type"],
            is_system=result["capability"]["is_system"],
        )

        return GetCapabilityResponse(
            capability=CapabilityDetail(**result["capability"])
        )
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CapabilityForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as e:
        logger.error("Failed to get capability", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to get capability: {str(e)}")
        )


class DeleteCapabilityResponse(BaseModel):
    """Response for delete capability endpoint."""
    id: UUID
    agent_type: str
    message: str = "Capability deleted successfully"


@router.delete("/agents/{capability_id}", response_model=DeleteCapabilityResponse)
async def delete_capability(
    capability_id: UUID,
    use_cases: CapabilityUseCases = Depends(get_capability_use_cases),
    db: Database = Depends(get_database),
    current_user: AuthUser = Depends(auth_middleware.require_auth())
):
    """
    Soft-delete a user-defined capability by setting is_active=false.

    **Authorization:**
    - Only capabilities owned by the user's organization can be deleted
    - System capabilities cannot be deleted

    **Behavior:**
    - Sets is_active=false (soft delete, capability still exists in database)
    - Does NOT remove the capability or its version history
    - Deleted capabilities can be reactivated via the update endpoint

    **Returns:**
    - 200 with the deleted capability's id and agent_type
    - 404 if capability not found
    - 403 if trying to delete system capability or capability from different organization
    """
    try:
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None
        resolved_use_cases = _resolve_capability_use_cases(use_cases, db)
        result = await resolved_use_cases.delete_capability(capability_id=capability_id, org_id=org_id)

        logger.info(
            "Soft-deleted capability",
            agent_type=result["agent_type"],
            capability_id=str(result["id"]),
            organization_id=str(org_id),
        )

        return DeleteCapabilityResponse(**result)
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CapabilityForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as e:
        logger.error("Failed to delete capability", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to delete capability: {str(e)}")
        )


# -------------------------------------------------------------------------
# Compatibility helpers (legacy tests import these directly)
# -------------------------------------------------------------------------

def validate_capability_spec(spec: Dict[str, Any]) -> List[str]:
    """Validate a capability specification and return error messages."""
    return capability_use_cases.validate_capability_spec(spec)


def _extract_keywords(spec: Dict[str, Any]) -> List[str]:
    """Proxy to application-layer keyword extraction for tests."""
    return capability_use_cases._extract_keywords(spec)


def get_embedding_client():
    """Compatibility wrapper for tests patching embedding client access."""
    return capability_use_cases.get_embedding_client()


async def _generate_query_embedding(query: str) -> Optional[List[float]]:
    """Proxy to application-layer embedding generation for tests."""
    try:
        embedding_client = get_embedding_client()
        if not embedding_client.is_configured:
            return None

        async with embedding_client as client:
            result = await client.create_embedding(query)
            return result.embedding
    except Exception:
        return None


async def _semantic_search(
    session,
    query_embedding: List[float],
    org_id: Optional[str],
    include_system: bool,
    active_only: bool,
    domain: Optional[str],
    tags: Optional[List[str]],
    limit: int,
    min_similarity: float,
) -> List[Dict[str, Any]]:
    """Proxy to application-layer semantic search for tests."""
    return await capability_use_cases._semantic_search(
        session=session,
        query_embedding=query_embedding,
        org_id=org_id,
        include_system=include_system,
        active_only=active_only,
        domain=domain,
        tags=tags,
        limit=limit,
        min_similarity=min_similarity,
    )


async def _keyword_search(
    session,
    query: str,
    org_id: Optional[str],
    include_system: bool,
    active_only: bool,
    domain: Optional[str],
    tags: Optional[List[str]],
    limit: int,
) -> List[Dict[str, Any]]:
    """Proxy to application-layer keyword search for tests."""
    return await capability_use_cases._keyword_search(
        session=session,
        query=query,
        org_id=org_id,
        include_system=include_system,
        active_only=active_only,
        domain=domain,
        tags=tags,
        limit=limit,
    )
