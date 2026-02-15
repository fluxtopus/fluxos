"""
# REVIEW:
# - Router is very large (create, execute, checkpoint management, previews, preferences) and overlaps with checkpoints/preferences routes.
# - Runtime wiring now goes through shared task providers; router should eventually depend on narrower per-endpoint use cases.
API routes for autonomous task delegation.

Provides endpoints for:
- Creating and managing delegation plans
- Executing plans with checkpoint support
- Approving/rejecting checkpoints
- Managing user preferences
"""

from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import uuid
import structlog

from src.domain.checkpoints import CheckpointState
from src.domain.tasks import InvalidTransitionError
from src.application.tasks import TaskUseCases
from src.application.checkpoints import CheckpointUseCases
from src.application.tasks.providers import (
    get_task_use_cases as provider_get_task_use_cases,
    get_checkpoint_use_cases as provider_get_checkpoint_use_cases,
    shutdown_task_runtime,
)
from src.domain.tasks.models import Task, TaskStep, TaskStatus
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail


logger = structlog.get_logger()

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

async def get_task_use_cases() -> TaskUseCases:
    """Provide application-layer task use cases."""
    return await provider_get_task_use_cases()


async def get_checkpoint_use_cases() -> CheckpointUseCases:
    """Provide application-layer checkpoint use cases."""
    return await provider_get_checkpoint_use_cases()


# === Request/Response Models ===


class CreateTaskRequest(BaseModel):
    """Request to create a new task."""
    goal: str = Field(..., description="Natural language goal description", min_length=10)
    constraints: Optional[Dict[str, Any]] = Field(default=None, description="Optional constraints")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata")
    auto_start: bool = Field(default=True, description="Automatically start execution after creation")


class CreateTaskWithStepsRequest(BaseModel):
    """Request to create a task with pre-defined steps."""
    goal: str = Field(..., description="Natural language goal description")
    steps: List[Dict[str, Any]] = Field(..., description="List of step definitions")
    constraints: Optional[Dict[str, Any]] = Field(default=None, description="Optional constraints")


class TaskStepResponse(BaseModel):
    """Response model for a plan step."""
    id: str
    name: str
    description: str
    agent_type: str
    domain: Optional[str] = None
    status: str
    inputs: Dict[str, Any]
    outputs: Optional[Union[Dict[str, Any], List[Any], str]] = None
    depends_on: List[str] = []
    checkpoint_required: bool = False
    retry_count: int = 0
    error_message: Optional[str] = None


class TaskMetadataResponse(BaseModel):
    """Metadata for scheduled tasks."""
    scheduled_workflow_id: Optional[str] = None
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None
    next_scheduled_run: Optional[str] = None
    automation_id: Optional[str] = None
    template_task_id: Optional[str] = None

    class Config:
        extra = "allow"


class TaskResponse(BaseModel):
    """Response model for a task."""
    id: str
    goal: str
    status: str
    source: Optional[str] = None
    steps: List[TaskStepResponse]
    progress_percentage: float
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Optional[TaskMetadataResponse] = None
    # Fast path data retrieval results
    # Can be either:
    # - Dict with {object_type, data, total_count} (new structured format)
    # - List[Dict] (legacy format from older tasks)
    result_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    result_count: Optional[int] = None
    # Error message if planning failed
    planning_error: Optional[str] = None


class ExecuteTaskRequest(BaseModel):
    """Request to execute a task."""
    run_to_completion: bool = Field(
        default=False,
        description="If true, auto-approve all checkpoints"
    )


class ExecutionResponse(BaseModel):
    """Response from task execution."""
    task_id: str
    status: str
    steps_completed: int
    steps_total: int
    checkpoint: Optional[Dict[str, Any]] = None
    findings: List[Dict[str, Any]] = []
    error: Optional[str] = None


class CheckpointResponse(BaseModel):
    """Response for a checkpoint."""
    task_id: str
    step_id: str
    checkpoint_name: str
    description: str
    decision: str
    preview_data: Dict[str, Any]
    checkpoint_type: str = "approval"
    questions: Optional[List[str]] = None
    alternatives: Optional[List[Dict[str, Any]]] = None
    context_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApproveCheckpointRequest(BaseModel):
    """Request to approve a checkpoint."""
    feedback: Optional[str] = Field(default=None, description="Optional feedback")
    learn_preference: bool = Field(default=True, description="Learn this as preference")


class RejectCheckpointRequest(BaseModel):
    """Request to reject a checkpoint."""
    reason: str = Field(..., description="Reason for rejection", min_length=5)
    learn_preference: bool = Field(default=True, description="Learn this as preference")


class ResolveQACheckpointRequest(BaseModel):
    """Request to resolve a QA checkpoint with question/answer pairs."""
    answers: Dict[str, str] = Field(..., description="Answers keyed by checkpoint question")
    feedback: Optional[str] = Field(default=None, description="Optional additional feedback")
    learn_preference: bool = Field(default=True, description="Learn this as preference")


class PreviewRequest(BaseModel):
    """Request to generate a plan preview without persistence."""
    goal: str = Field(..., description="Business goal to generate a plan for", min_length=10, max_length=1000)


class PreviewStepResponse(BaseModel):
    """A step in a preview plan."""
    id: str
    name: str
    display_name: str
    description: str
    agent_type: str
    is_scheduled: bool = False
    depends_on: List[str] = []


class PreviewResponse(BaseModel):
    """Response for a plan preview (not persisted)."""
    id: str
    goal: str
    status: str = "preview"
    steps: List[PreviewStepResponse]
    has_more_steps: bool = False


# === Task Endpoints ===


@router.post("", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    request: CreateTaskRequest,
    raw_request: Request,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "create")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Create a new task from a goal.

    Returns immediately with a PLANNING-status task stub. Planning runs
    in the background — use GET /{task_id}/observe to watch progress via SSE.
    """
    org_id = user.metadata.get("organization_id") if user.metadata else None
    logger.info(
        "Creating task",
        user_id=user.id,
        goal=request.goal[:50],
        organization_id=org_id,
        user_metadata=user.metadata,
    )

    # Inject user_token into constraints so the planner can fetch user integrations
    constraints = dict(request.constraints or {})
    auth_header = raw_request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        constraints["user_token"] = auth_header[len("Bearer "):]

    try:
        task = await use_cases.create_task(
            user_id=user.id,
            organization_id=org_id,
            goal=request.goal,
            constraints=constraints,
            metadata=request.metadata,
            auto_start=request.auto_start,
        )
        return _task_to_response(task)
    except Exception as e:
        logger.error("Failed to create task", error=str(e))
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.post("/preview", response_model=PreviewResponse)
async def preview_plan(
    request: PreviewRequest,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
):
    """
    Generate a plan preview without creating a real task.

    Calls the planner LLM to decompose the goal into steps, but does NOT
    persist anything to the database or Redis. Returns a random UUID so the
    frontend can reference the preview, but it is not a real task ID.
    """
    from src.infrastructure.tasks.task_planner_agent import TaskPlannerAgent

    logger.info(
        "Generating plan preview",
        user_id=auth_user.id,
        goal=request.goal[:50],
    )

    try:
        planner = TaskPlannerAgent()
        all_steps = await planner.generate_delegation_steps(
            request.goal, skip_validation=True
        )
        capped = all_steps[:5]
        return PreviewResponse(
            id=str(uuid.uuid4()),
            goal=request.goal,
            steps=[
                PreviewStepResponse(
                    id=s.id,
                    name=s.name,
                    display_name=_humanize_step_name(s.name),
                    description=s.description,
                    agent_type=s.agent_type,
                    is_scheduled=_is_scheduled_step(s.agent_type),
                    depends_on=s.dependencies,
                )
                for s in capped
            ],
            has_more_steps=len(all_steps) > 5,
        )
    except Exception as e:
        logger.error("Failed to generate plan preview", error=str(e))
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.post("/with-steps", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_with_steps(
    request: CreateTaskWithStepsRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "create")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Create a task with pre-defined steps.

    Useful when steps are generated externally or for testing.
    """
    logger.info(
        "Creating task with steps",
        user_id=user.id,
        goal=request.goal[:50],
        step_count=len(request.steps),
    )

    try:
        task = await use_cases.create_task_with_steps(
            user_id=user.id,
            organization_id=user.metadata.get("organization_id"),
            goal=request.goal,
            steps=request.steps,
            constraints=request.constraints,
        )
        return _task_to_response(task)
    except Exception as e:
        logger.error("Failed to create task", error=str(e))
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """Get a task by ID."""
    task = await use_cases.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if task.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return _task_to_response(task)


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """List tasks for the current user."""
    task_status = None
    if status:
        try:
            task_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    tasks = await use_cases.list_tasks(user.id, status=task_status, limit=limit)
    return [_task_to_response(t) for t in tasks]


@router.post("/{task_id}/execute", response_model=ExecutionResponse)
async def execute_task(
    task_id: str,
    request: ExecuteTaskRequest = ExecuteTaskRequest(),
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "execute")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Execute a task.

    Runs until completion, checkpoint, or error.
    """
    logger.info(
        "Executing task",
        task_id=task_id,
        user_id=user.id,
        run_to_completion=request.run_to_completion,
    )

    try:
        result = await use_cases.execute_task(
            task_id=task_id,
            user_id=user.id,
            run_to_completion=request.run_to_completion,
        )
        return ExecutionResponse(
            task_id=result.plan_id,
            status=result.status,
            steps_completed=result.steps_completed,
            steps_total=result.steps_total,
            checkpoint=result.checkpoint,
            findings=result.findings,
            error=result.error,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))
    except Exception as e:
        logger.error("Task execution failed", error=str(e))
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.post("/{task_id}/start")
async def start_task(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "execute")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Start task execution asynchronously.

    Enqueues the first steps for execution and returns immediately.
    Use /observe to watch for real-time updates.

    Returns:
        - status: "started" or "already_executing" if task was already running
        - task_id: The task that was started
        - task: The current task state (optional)
        - message: Instructions on how to observe execution

    Error codes:
        - 400: Invalid request (bad task ID, not owner, etc.)
        - 409: Task is already executing (returns current task state)
        - 404: Task not found
    """
    logger.info(
        "Starting task async",
        task_id=task_id,
        user_id=user.id,
    )

    result = await use_cases.start_task(task_id=task_id, user_id=user.id)

    if result.get("status") == "already_executing":
        # Return 409 Conflict with current task state
        # This allows idempotent start calls - the frontend can continue observing
        return {
            "status": "already_executing",
            "task_id": task_id,
            "task": result.get("task"),
            "message": "Task is already executing. Connect to observe endpoint for updates.",
        }

    if result.get("status") == "error":
        error_msg = result.get("error", "Failed to start task")

        # Check if it's a "not found" error
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )

        # Check if it's a transition error (invalid state)
        current_status = result.get("current_status")
        if current_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot start task in {current_status} state: {error_msg}",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    return result


@router.get("/{task_id}/observe")
async def observe_task(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Observe task execution via Server-Sent Events.

    This is a pure observation endpoint - it does not execute any steps.
    Events are published by the worker via Redis pub/sub.

    Use POST /start first to begin execution, then connect here to observe.

    Event types:
        - connected: Initial connection established
        - task.step.started: A step began executing
        - task.step.completed: A step finished successfully
        - task.step.failed: A step failed
        - task.checkpoint.created: A checkpoint needs user approval
        - task.completed: Task finished successfully
        - task.failed: Task failed
        - heartbeat: Keep-alive ping (every 30 seconds)
    """
    async def event_generator():
        async for event in use_cases.observe_execution(task_id, user.id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/{task_id}/pause", response_model=TaskResponse)
async def pause_task(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "update")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """Pause a running task."""
    try:
        task = await use_cases.pause_task(task_id, user.id)
        return _task_to_response(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("tasks", "delete")),
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """Cancel a task permanently."""
    try:
        task = await use_cases.cancel_task(task_id, user.id)
        return _task_to_response(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))


# === Checkpoint Endpoints ===


@router.get("/{task_id}/checkpoints", response_model=List[CheckpointResponse])
async def get_task_checkpoints(
    task_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "view")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Get pending checkpoints for a task."""
    # Filter by task_id (plan_id) instead of user_id since checkpoints
    # may be created with system user during background execution
    checkpoints = await use_cases.list_pending_for_task(task_id)
    return [_checkpoint_to_response(c) for c in checkpoints]


@router.post("/{task_id}/checkpoints/{step_id}/approve", response_model=CheckpointResponse)
async def approve_checkpoint(
    task_id: str,
    step_id: str,
    request: ApproveCheckpointRequest = ApproveCheckpointRequest(),
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "resolve")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Approve a checkpoint."""
    logger.info(
        "Approving checkpoint",
        task_id=task_id,
        step_id=step_id,
        user_id=user.id,
    )

    try:
        checkpoint = await use_cases.approve_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id=user.id,
            feedback=request.feedback,
            learn_preference=request.learn_preference,
        )
        return _checkpoint_to_response(checkpoint)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))


@router.post("/{task_id}/checkpoints/{step_id}/reject", response_model=CheckpointResponse)
async def reject_checkpoint(
    task_id: str,
    step_id: str,
    request: RejectCheckpointRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("checkpoints", "resolve")),
    use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Reject a checkpoint."""
    logger.info(
        "Rejecting checkpoint",
        task_id=task_id,
        step_id=step_id,
        user_id=user.id,
        reason=request.reason,
    )

    try:
        checkpoint = await use_cases.reject_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id=user.id,
            reason=request.reason,
            learn_preference=request.learn_preference,
        )
        return _checkpoint_to_response(checkpoint)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=safe_error_detail(str(e)))


# === Preview Helpers ===


def _humanize_step_name(name: str) -> str:
    """Convert snake_case step name to a friendly display name."""
    return name.replace("_", " ").title()


def _is_scheduled_step(agent_type: str) -> bool:
    """Check if a step represents a scheduled/recurring action."""
    return agent_type in ("schedule_job", "scheduler")


# === Helper Functions ===


def _task_to_response(task: Task) -> TaskResponse:
    """Convert Task to response model."""
    # Build metadata response if present
    metadata_response = None
    if task.metadata:
        metadata_response = TaskMetadataResponse(
            scheduled_workflow_id=task.metadata.get("scheduled_workflow_id"),
            schedule_cron=task.metadata.get("schedule_cron"),
            schedule_timezone=task.metadata.get("schedule_timezone"),
            next_scheduled_run=task.metadata.get("next_scheduled_run"),
            automation_id=task.metadata.get("automation_id"),
            template_task_id=task.metadata.get("template_task_id"),
        )

    # Extract fast path result data if present
    result_data = None
    result_count = None
    if task.metadata and task.metadata.get("fast_path"):
        result_data = task.metadata.get("result_data")
        result_count = task.metadata.get("result_count")

    # Determine source from metadata (set by automation system) or default
    source = task.metadata.get("source") if task.metadata else None

    return TaskResponse(
        id=task.id,
        goal=task.goal,
        status=task.status.value,
        source=source,
        steps=[
            TaskStepResponse(
                id=s.id,
                name=s.name,
                description=s.description,
                agent_type=s.agent_type,
                domain=s.domain,
                status=s.status.value,
                inputs=s.inputs,
                outputs=s.outputs,
                depends_on=s.dependencies,
                checkpoint_required=s.checkpoint_required,
                retry_count=s.retry_count,
                error_message=s.error_message,
            )
            for s in task.steps
        ],
        progress_percentage=task.get_progress_percentage(),
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        metadata=metadata_response,
        result_data=result_data,
        result_count=result_count,
        planning_error=task.metadata.get("planning_error") if task.metadata else None,
    )


def _checkpoint_to_response(checkpoint: CheckpointState) -> CheckpointResponse:
    """Convert CheckpointState to response model."""
    return CheckpointResponse(
        task_id=checkpoint.plan_id,
        step_id=checkpoint.step_id,
        checkpoint_name=checkpoint.checkpoint_name,
        description=checkpoint.description,
        decision=checkpoint.decision.value,
        preview_data=checkpoint.preview_data,
        checkpoint_type=checkpoint.checkpoint_type.value,
        questions=checkpoint.questions,
        alternatives=checkpoint.alternatives,
        context_data=checkpoint.context_data,
        created_at=checkpoint.created_at,
        expires_at=checkpoint.expires_at,
    )


# === Startup/Shutdown ===


async def startup():
    """Initialize task runtime via shared providers."""
    await provider_get_task_use_cases()
    logger.info("Task runtime initialized")


async def shutdown():
    """Cleanup task runtime via shared providers."""
    await shutdown_task_runtime()
    logger.info("Task runtime cleaned up")
