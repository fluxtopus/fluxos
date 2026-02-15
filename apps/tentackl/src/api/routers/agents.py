# REVIEW:
# - Router mixes discovery, search, generation, and log/conversation access; responsibilities are broad.
# - Agent generation spans multiple concerns (ideation, validation, persistence); keep extracting into dedicated services.
# - Module-level dependencies injected at startup; implicit globals make testing harder.
"""Agent-related API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import json
import logging

from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail
from src.application.agents import (
    AgentNotFound,
    AgentUseCases,
)
from src.interfaces.database import Database
from src.infrastructure.agents import ConversationStoreAgentReaderAdapter
from src.infrastructure.capabilities.sql_repository import SqlCapabilityRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents")


# === Request/Response Models ===


class GenerateAgentRequest(BaseModel):
    """Request to generate and register an agent from a description."""
    description: str = Field(..., description="Natural language description of desired agent")
    context: Optional[str] = Field(None, description="Additional context about use case")


class SearchAgentsRequest(BaseModel):
    """Request for semantic agent search."""
    query: str = Field(..., description="Search query")
    limit: int = Field(10, description="Max results")
    category: Optional[str] = Field(None, description="Filter by category")
    capabilities: Optional[List[str]] = Field(None, description="Filter by capabilities")


# === Capabilities Response Models ===


class CapabilityInfo(BaseModel):
    """Information about an available capability."""
    name: str
    description: str


class CapabilitiesResponse(BaseModel):
    """Response listing available capabilities, types, and categories."""
    capabilities: List[CapabilityInfo]
    agent_types: List[str]
    categories: List[str]


# === Search Response Models ===


class AgentSearchResult(BaseModel):
    """A single agent search result."""
    id: str
    name: str
    version: str
    type: Optional[str] = None
    description: Optional[str] = None
    brief: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    similarity: float


class SearchAgentsResponse(BaseModel):
    """Response from agent semantic search."""
    agents: List[AgentSearchResult]
    query: str
    total: int


# Dependencies (injected at startup)
conversation_store: Optional[Any] = None
database: Optional[Database] = None


def get_database() -> Database:
    """Get the database instance."""
    if database is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


def get_agent_use_cases(
    db: Database = Depends(get_database),
) -> AgentUseCases:
    """Provide application-layer agent use cases."""
    conversation_reader = (
        ConversationStoreAgentReaderAdapter(conversation_store)
        if conversation_store is not None
        else None
    )
    return AgentUseCases(
        database=db,
        capability_repository=SqlCapabilityRepository(db),
        conversation_reader=conversation_reader,
    )


# === Public Discovery Endpoints ===


@router.get("/capabilities", response_model=CapabilitiesResponse, tags=["agent-discovery"])
async def list_capabilities(
    use_cases: AgentUseCases = Depends(get_agent_use_cases),
):
    """
    List available agent capabilities, types, and categories.

    This is a public discovery endpoint - no authentication required.
    Use this to understand what options are available when creating agents.
    """
    result = use_cases.list_discovery_capabilities()
    return CapabilitiesResponse(
        capabilities=[CapabilityInfo(**cap) for cap in result["capabilities"]],
        agent_types=result["agent_types"],
        categories=result["categories"],
    )


@router.get("/search", response_model=SearchAgentsResponse, tags=["agent-discovery"])
async def search_agents(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    min_similarity: float = Query(0.5, ge=0, le=1, description="Minimum similarity threshold"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    tags: Optional[str] = Query(None, description="Comma-separated tags filter"),
    include_system: bool = Query(True, description="Include system capabilities"),
    current_user: AuthUser = Depends(auth_middleware.require_permission("agents", "search")),
    use_cases: AgentUseCases = Depends(get_agent_use_cases),
):
    """
    Search for capabilities using hybrid semantic/keyword search.

    Uses embeddings for semantic similarity and falls back to keyword search.
    For example: "an agent that creates meal plans" or "social media monitoring".

    Note: This endpoint now searches the unified capabilities_agents table.
    The 'category' parameter has been replaced with 'domain' for consistency.
    """
    try:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        org_id = current_user.metadata.get("organization_id") if current_user.metadata else None

        result = await use_cases.search_agents(
            query=q,
            limit=limit,
            min_similarity=min_similarity,
            domain=domain,
            tags=tags_list,
            include_system=include_system,
            organization_id=str(org_id) if org_id else None,
        )

        return SearchAgentsResponse(
            agents=[AgentSearchResult(**agent) for agent in result["agents"]],
            query=result["query"],
            total=result["total"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent search failed: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.get("/{agent_id}/logs")
async def get_agent_logs(
    agent_id: str,
    limit: int = 100,
    current_user: AuthUser = Depends(auth_middleware.require_permission("agents", "view"))
):
    """Get logs for a specific agent."""
    # TODO: Implement log streaming
    return {"agent_id": agent_id, "logs": [], "message": "Log streaming not yet implemented"}


@router.get("/{agent_id}/conversations")
async def get_agent_conversations(
    agent_id: str,
    workflow_id: Optional[str] = None,
    current_user: AuthUser = Depends(auth_middleware.require_permission("agents", "view")),
    use_cases: AgentUseCases = Depends(get_agent_use_cases),
):
    """Get conversations for a specific agent."""
    try:
        return await use_cases.get_agent_conversations(agent_id=agent_id, workflow_id=workflow_id)
    except AgentNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as e:
        logger.error(f"Error fetching agent conversations: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


# === Agent Generation Endpoint (SSE streaming) ===


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/generate", tags=["agent-generation"])
async def generate_agent(
    request: GenerateAgentRequest,
    current_user: AuthUser = Depends(auth_middleware.require_auth()),
    use_cases: AgentUseCases = Depends(get_agent_use_cases),
):
    """
    Generate and register an agent from a natural language description.

    Streams SSE progress events through each phase:
    ideating → generating → validating → registering → complete.

    Returns the registered capability in the final 'complete' event.
    """
    async def event_stream():
        try:
            org_id = current_user.metadata.get("organization_id") if current_user.metadata else None
            async for event_type, data in use_cases.generate_agent_events(
                description=request.description,
                context=request.context,
                user_id=current_user.id,
                organization_id=org_id,
            ):
                yield _sse_event(event_type, data)
        except Exception as e:
            logger.error(f"Agent generation failed: {e}", exc_info=True)
            yield _sse_event("error", {"message": f"Agent generation failed: {str(e)}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
