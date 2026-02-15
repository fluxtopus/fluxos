"""
# REVIEW:
# - Uses module-level providers; router-level dependency injection is still global-state driven.
# - Runtime dependency injection is still global-state driven and should move to a composition root container.
API routes for task checkpoints.

Provides endpoints for:
- Listing all pending checkpoints for a user
- Resolving interactive checkpoints (INPUT, MODIFY, SELECT, QA)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

from src.application.checkpoints import (
    CheckpointNotFound,
    CheckpointUseCases,
    CheckpointValidationError,
)
from src.application.tasks.providers import (
    get_checkpoint_use_cases as provider_get_checkpoint_use_cases,
)
from src.domain.checkpoints import CheckpointState
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail


logger = structlog.get_logger()

router = APIRouter(prefix="/api/checkpoints", tags=["checkpoints"])


async def get_checkpoint_use_cases() -> CheckpointUseCases:
    """Provide application-layer checkpoint use cases."""
    return await provider_get_checkpoint_use_cases()


# === Response Models ===


class CheckpointResponseModel(BaseModel):
    """Response for a checkpoint."""
    task_id: str
    step_id: str
    checkpoint_name: str
    description: str
    decision: str
    preview_data: Dict[str, Any]
    created_at: datetime
    expires_at: Optional[datetime] = None
    # Interactive checkpoint fields
    checkpoint_type: str = "approval"
    input_schema: Optional[Dict[str, Any]] = None
    questions: Optional[List[str]] = None
    alternatives: Optional[List[Dict[str, Any]]] = None
    modifiable_fields: Optional[List[str]] = None
    context_data: Optional[Dict[str, Any]] = None


class ResolveCheckpointRequest(BaseModel):
    """Request to resolve an interactive checkpoint."""
    decision: str = Field(..., description="approved or rejected")
    feedback: Optional[str] = Field(None, description="Optional user feedback")
    inputs: Optional[Dict[str, Any]] = Field(None, description="User inputs for INPUT type")
    modified_inputs: Optional[Dict[str, Any]] = Field(None, description="Modified inputs for MODIFY type")
    selected_alternative: Optional[int] = Field(None, description="Selected option index for SELECT type")
    answers: Optional[Dict[str, str]] = Field(None, description="Answers for QA type")
    learn_preference: bool = Field(True, description="Whether to learn this as a preference")


# === Endpoints ===


@router.get("", response_model=List[CheckpointResponseModel])
async def get_all_checkpoints(
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "view")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Get all pending checkpoints for the current user."""
    checkpoints = await use_cases.list_pending(user.id)
    return [_checkpoint_to_response(c) for c in checkpoints]


@router.get("/{task_id}/{step_id}", response_model=CheckpointResponseModel)
async def get_checkpoint(
    task_id: str,
    step_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "view")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Get a specific checkpoint by task and step ID."""
    try:
        checkpoint = await use_cases.get_checkpoint(task_id, step_id)
        return _checkpoint_to_response(checkpoint)
    except CheckpointNotFound:
        raise HTTPException(status_code=404, detail="Checkpoint not found")


@router.post("/{task_id}/{step_id}/resolve", response_model=CheckpointResponseModel)
async def resolve_checkpoint(
    task_id: str,
    step_id: str,
    request: ResolveCheckpointRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "respond")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """
    Resolve an interactive checkpoint.

    Supports all checkpoint types:
    - APPROVAL: Send decision only
    - INPUT: Send decision + inputs (validated against input_schema)
    - MODIFY: Send decision + modified_inputs
    - SELECT: Send decision + selected_alternative (0-indexed)
    - QA: Send decision + answers (dict of question: answer)
    """
    try:
        checkpoint = await use_cases.resolve_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id=user.id,
            decision=request.decision,
            feedback=request.feedback,
            inputs=request.inputs,
            modified_inputs=request.modified_inputs,
            selected_alternative=request.selected_alternative,
            answers=request.answers,
            learn_preference=request.learn_preference,
        )

        return _checkpoint_to_response(checkpoint)

    except CheckpointValidationError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))
    except Exception as e:
        logger.error("resolve_checkpoint_failed", error=str(e), task_id=task_id, step_id=step_id)
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


# === Helper Functions ===


def _checkpoint_to_response(checkpoint: CheckpointState) -> CheckpointResponseModel:
    """Convert CheckpointState to response model."""
    return CheckpointResponseModel(
        task_id=checkpoint.plan_id,
        step_id=checkpoint.step_id,
        checkpoint_name=checkpoint.checkpoint_name,
        description=checkpoint.description,
        decision=checkpoint.decision.value,
        preview_data=checkpoint.preview_data,
        created_at=checkpoint.created_at,
        expires_at=checkpoint.expires_at,
        # Interactive checkpoint fields
        checkpoint_type=checkpoint.checkpoint_type.value if checkpoint.checkpoint_type else "approval",
        input_schema=checkpoint.input_schema,
        questions=checkpoint.questions,
        alternatives=checkpoint.alternatives,
        modifiable_fields=checkpoint.modifiable_fields,
        context_data=checkpoint.context_data,
    )
