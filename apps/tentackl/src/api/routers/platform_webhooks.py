"""
# REVIEW:
# - Endpoints are described as internal but no auth/signature verification is enforced yet.
# - Router still owns broad orchestration use cases (task creation + execution + checkpoint resolution).
API routes for platform webhooks.

Platform webhooks are internal endpoints that trigger platform-level
automations like support handling, health monitoring, and billing alerts.
"""

import hmac
import os

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header, status
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional, List
import re
from datetime import datetime
from enum import Enum
import structlog

from src.application.tasks import TaskUseCases
from src.application.checkpoints import CheckpointUseCases
from src.application.tasks.providers import (
    get_task_use_cases as provider_get_task_use_cases,
    get_checkpoint_use_cases as provider_get_checkpoint_use_cases,
)
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail


logger = structlog.get_logger(__name__)

PLATFORM_WEBHOOK_KEY = os.getenv(
    "TENTACKL_PLATFORM_WEBHOOK_KEY",
    os.getenv("PLATFORM_WEBHOOK_KEY", ""),
)


async def require_platform_webhook_auth(
    x_platform_webhook_key: Optional[str] = Header(None, alias="X-Platform-Webhook-Key"),
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
) -> None:
    """Require service-to-service auth for platform webhook endpoints."""
    if not PLATFORM_WEBHOOK_KEY:
        logger.warning("Platform webhook key not configured, rejecting request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform webhook auth not configured",
        )

    provided = x_platform_webhook_key or x_internal_key
    if not provided or not hmac.compare_digest(provided, PLATFORM_WEBHOOK_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid platform webhook key",
        )


router = APIRouter(
    prefix="/api/platform/webhooks",
    tags=["platform-webhooks"],
    dependencies=[Depends(require_platform_webhook_auth)],
)

async def get_task_use_cases() -> TaskUseCases:
    """Provide application-layer task use cases."""
    return await provider_get_task_use_cases()


async def get_checkpoint_use_cases() -> CheckpointUseCases:
    """Provide application-layer checkpoint use cases."""
    return await provider_get_checkpoint_use_cases()


# === Request/Response Models ===


class TicketSource(str, Enum):
    """Source of the support ticket."""
    EMAIL = "email"
    FORM = "form"
    API = "api"
    GITHUB = "github"


class SupportTicketRequest(BaseModel):
    """Request to process a support ticket."""
    ticket_id: str = Field(..., description="Unique ticket identifier")
    customer_email: str = Field(..., description="Customer email address")
    subject: str = Field(..., description="Ticket subject line", min_length=1, max_length=500)
    body: str = Field(..., description="Ticket body/description", min_length=1)
    source: TicketSource = Field(default=TicketSource.API, description="Ticket source")
    priority_hint: Optional[str] = Field(None, description="Priority hint from source system")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("customer_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v


class SupportTicketResponse(BaseModel):
    """Response from support ticket processing."""
    success: bool
    task_id: str
    message: str
    estimated_response_time: str = "24 hours"


class TaskStatusResponse(BaseModel):
    """Status of a platform task."""
    task_id: str
    status: str
    progress_percentage: float
    steps_completed: int
    steps_total: int
    checkpoint_pending: bool = False
    findings: List[Dict[str, Any]] = []


# === Support Ticket Endpoint ===


@router.post(
    "/support",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process a support ticket",
    description="""
    Receives a support ticket and triggers the support automation task.

    The automation will:
    1. Fetch customer context from InkPass
    2. Analyze recent errors and execution history
    3. Categorize and prioritize the ticket
    4. Send auto-acknowledgment email via Mimic
    5. Generate context summary for support agent
    6. Update ticket with priority and context

    The task runs asynchronously. Use GET /platform/tasks/{task_id} to check status.
    """
)
async def process_support_ticket(
    request: SupportTicketRequest,
    background_tasks: BackgroundTasks,
    use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """
    Process a support ticket through the automation task.

    This endpoint is designed for manual testing and internal use.
    For production, add webhook signature verification.
    """
    logger.info(
        "Received support ticket",
        ticket_id=request.ticket_id,
        customer_email=request.customer_email,
        source=request.source.value,
    )

    # Build the goal for the task planner
    # NOTE: We specify available subagents to guide the planner
    goal = f"""Process support ticket #{request.ticket_id} from customer {request.customer_email}.

Subject: {request.subject}

Body:
{request.body}

Requirements:
1. Fetch customer context (account info, recent errors, execution history) using support:get_customer_context
2. Analyze the ticket to categorize (bug, billing, feature request, how-to, other) using analyze
3. Estimate priority/severity (critical, high, medium, low) using analyze
4. Generate auto-acknowledgment email content using compose
5. Send the acknowledgment email to customer using support:send_support_email
6. Generate context summary for support agent using compose

Available subagent types and their expected inputs:
- support:get_customer_context - Fetches customer account info, recent errors, and execution history
  REQUIRED inputs: {{"customer_email": "{request.customer_email}"}}
- support:send_support_email - Sends emails via Mimic notification service
  REQUIRED inputs: {{"to": "<recipient_email>", "ticket_id": "<ticket_id>", "body": "<email_body>"}}
- analyze - Analyzes and categorizes data
  REQUIRED inputs: {{"data": "<data_to_analyze>"}}
- compose - Generates text content from templates or instructions
  REQUIRED inputs: {{"content": "<prompt_or_template>", "format": "<email|report|text>"}}
- http_fetch - Makes HTTP API calls
  REQUIRED inputs: {{"url": "<url>", "method": "GET|POST"}}

Be helpful and professional in all communications."""

    # Build constraints for the task
    constraints = {
        "ticket_id": request.ticket_id,
        "customer_email": request.customer_email,
        "source": request.source.value,
        "priority_hint": request.priority_hint,
        "notification_channel": "email",  # Email only as decided
        "auto_send_acknowledgment": True,
    }

    try:
        # Create the task (planner will generate steps)
        task = await use_cases.create_task(
            user_id="platform-support-automation",  # Platform service user
            organization_id="aios-platform",
            goal=goal,
            constraints=constraints,
            metadata={
                "ticket_metadata": request.metadata,
                "workflow_type": "support_automation",
                "created_at": datetime.utcnow().isoformat(),
            }
        )

        # Start execution in background
        background_tasks.add_task(
            _execute_task_background,
            use_cases,
            task.id,
        )

        logger.info(
            "Support ticket task created",
            task_id=task.id,
            ticket_id=request.ticket_id,
            steps_count=len(task.steps),
        )

        return SupportTicketResponse(
            success=True,
            task_id=task.id,
            message=f"Support ticket #{request.ticket_id} is being processed",
            estimated_response_time="24 hours",
        )

    except Exception as e:
        logger.error(
            "Failed to create support ticket task",
            ticket_id=request.ticket_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(f"Failed to process support ticket: {str(e)}")
        )


async def _execute_task_background(use_cases: TaskUseCases, task_id: str) -> None:
    """Execute a task in the background."""
    try:
        logger.info("Starting background task execution", task_id=task_id)

        result = await use_cases.execute_task(
            task_id=task_id,
            user_id="platform-support-automation",
            run_to_completion=False,  # Stop at checkpoints
        )

        logger.info(
            "Background task execution completed",
            task_id=task_id,
            status=result.status,
            steps_completed=result.steps_completed,
        )

    except Exception as e:
        logger.error(
            "Background task execution failed",
            task_id=task_id,
            error=str(e),
        )


# === Task Status Endpoint ===


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get platform task status",
)
async def get_task_status(
    task_id: str,
    use_cases: TaskUseCases = Depends(get_task_use_cases),
    checkpoint_use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Get the status of a platform task."""
    task = await use_cases.get_task(task_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task not found: {task_id}"
        )

    # Check for pending checkpoints
    checkpoints = await checkpoint_use_cases.list_pending("platform-support-automation")
    checkpoint_pending = any(c.plan_id == task_id for c in checkpoints)

    # Convert findings
    findings = []
    for step in task.steps:
        if step.outputs and isinstance(step.outputs, dict):
            if "findings" in step.outputs:
                findings.extend(step.outputs["findings"])

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value,
        progress_percentage=task.get_progress_percentage(),
        steps_completed=sum(1 for s in task.steps if s.status.value == "completed"),
        steps_total=len(task.steps),
        checkpoint_pending=checkpoint_pending,
        findings=findings,
    )


# === Checkpoint Management ===


@router.post(
    "/tasks/{task_id}/approve/{step_id}",
    summary="Approve a checkpoint",
)
async def approve_checkpoint(
    task_id: str,
    step_id: str,
    feedback: Optional[str] = None,
    checkpoint_use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
    task_use_cases: TaskUseCases = Depends(get_task_use_cases),
):
    """Approve a pending checkpoint and continue execution."""
    try:
        await checkpoint_use_cases.approve_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id="platform-support-automation",
            feedback=feedback,
        )

        # Continue execution after approval
        result = await task_use_cases.execute_task(
            task_id=task_id,
            user_id="platform-support-automation",
            run_to_completion=False,
        )

        return {
            "success": True,
            "message": "Checkpoint approved, execution continued",
            "status": result.status,
            "steps_completed": result.steps_completed,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))


@router.post(
    "/tasks/{task_id}/reject/{step_id}",
    summary="Reject a checkpoint",
)
async def reject_checkpoint(
    task_id: str,
    step_id: str,
    reason: str,
    checkpoint_use_cases: CheckpointUseCases = Depends(get_checkpoint_use_cases),
):
    """Reject a pending checkpoint."""
    try:
        await checkpoint_use_cases.reject_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id="platform-support-automation",
            reason=reason,
        )

        return {
            "success": True,
            "message": f"Checkpoint rejected: {reason}",
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=safe_error_detail(str(e)))
