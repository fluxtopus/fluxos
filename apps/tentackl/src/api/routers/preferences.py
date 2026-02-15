"""
# REVIEW:
# - Router still depends on shared runtime lifecycle instead of a dedicated preferences runtime.
API routes for user preferences.

Provides endpoints for:
- Listing learned preferences
- Getting preference statistics
- Deleting preferences
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import structlog

from src.application.preferences import (
    PreferenceForbidden,
    PreferenceNotFound,
    PreferenceUseCases,
    PreferenceValidationError,
)
from src.infrastructure.preferences.preference_service_adapter import PreferenceServiceAdapter
from src.application.tasks.providers import get_task_runtime
from src.api.auth_middleware import auth_middleware, AuthUser
from src.interfaces.database import Database


logger = structlog.get_logger()

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# Database instance (injected at startup)
database: Optional[Database] = None


def get_database() -> Database:
    """Get database instance."""
    if database is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


async def get_preference_use_cases(
    db: Database = Depends(get_database),
) -> PreferenceUseCases:
    """Provide application-layer preference use cases."""
    runtime = await get_task_runtime()
    return PreferenceUseCases(preference_ops=PreferenceServiceAdapter(runtime, db))


# === Request/Response Models ===


class CreatePreferenceRequest(BaseModel):
    """Request to create a manual instruction preference."""
    preference_key: str
    instruction: str
    scope: str = "global"  # global, agent_type, task_type, task
    scope_value: Optional[str] = None


class CreatePreferenceResponse(BaseModel):
    """Response for created preference."""
    id: str
    preference_key: str
    instruction: str
    scope: str
    scope_value: Optional[str]
    created_at: datetime


class PreferenceResponse(BaseModel):
    """Response for a user preference (learned preferences)."""
    id: str
    preference_key: str
    decision: str
    confidence: float
    usage_count: int
    last_used: datetime
    created_at: datetime


class PreferenceStatsResponse(BaseModel):
    """Response for preference statistics."""
    total_preferences: int
    high_confidence: int
    approvals: int
    rejections: int
    avg_confidence: float
    total_usage: int


# === Endpoints ===


@router.get("", response_model=List[PreferenceResponse])
async def list_preferences(
    user: AuthUser = Depends(auth_middleware.require_permission("preferences", "view")),
    use_cases: PreferenceUseCases = Depends(get_preference_use_cases),
):
    """Get all learned preferences for the current user."""
    preferences = await use_cases.list_preferences(user.id)
    return [PreferenceResponse(**pref) for pref in preferences]


@router.get("/stats", response_model=PreferenceStatsResponse)
async def get_preference_stats(
    user: AuthUser = Depends(auth_middleware.require_permission("preferences", "view")),
    use_cases: PreferenceUseCases = Depends(get_preference_use_cases),
):
    """Get preference learning statistics."""
    stats = await use_cases.get_preference_stats(user.id)
    return PreferenceStatsResponse(**stats)


@router.delete("/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(
    preference_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("preferences", "update")),
    use_cases: PreferenceUseCases = Depends(get_preference_use_cases),
):
    """Delete a learned preference."""
    try:
        await use_cases.delete_preference(user.id, preference_id)
    except PreferenceNotFound:
        raise HTTPException(status_code=404, detail=f"Preference not found: {preference_id}")
    except PreferenceForbidden:
        raise HTTPException(status_code=403, detail="Access denied")


@router.post("", response_model=CreatePreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_preference(
    request: CreatePreferenceRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("preferences", "update")),
    use_cases: PreferenceUseCases = Depends(get_preference_use_cases),
):
    """
    Create a manual instruction preference.

    Instruction preferences are injected into agent prompts to customize behavior.

    Scope hierarchy (higher priority wins):
    - task: Applies to specific task ID
    - task_type: Applies to task category (e.g., "meal_planning")
    - agent_type: Applies to agent type (e.g., "compose")
    - global: Applies to all agents
    """
    # Get organization_id from user metadata
    organization_id = user.metadata.get("organization_id") if user.metadata else None
    try:
        created = await use_cases.create_preference(
            user_id=user.id,
            organization_id=organization_id,
            preference_key=request.preference_key,
            instruction=request.instruction,
            scope=request.scope,
            scope_value=request.scope_value,
        )
        return CreatePreferenceResponse(**created)
    except PreferenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
