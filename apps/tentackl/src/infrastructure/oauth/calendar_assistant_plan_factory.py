# REVIEW: The calendar task is hard-coded as Python with embedded prompts,
# REVIEW: making it hard to iterate or localize. Consider defining this as a
# REVIEW: task template/config and reusing shared builders rather than
# REVIEW: duplicating task construction logic.
"""
Calendar Assistant Delegation Plan Factory

Creates delegation plans for the calendar assistant workflow:
1. Fetch emails from Gmail (last 24h, calendar-related)
2. Extract calendar events using LLM
3. Create events in Google Calendar
4. Send daily digest notification

This factory creates structured plans that can be executed by the delegation
orchestrator with checkpoint support for risky operations.
"""

from typing import Dict, Any, Optional
import uuid
import structlog

from src.domain.tasks.models import (
    Task,
    TaskStep,
    StepStatus,
    TaskStatus,
    CheckpointConfig,
    ApprovalType,
    FallbackConfig,
)


logger = structlog.get_logger()


def create_calendar_plan(
    user_id: str,
    organization_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Task:
    """
    Create a calendar assistant delegation plan.

    The plan consists of 4 steps:
    1. Gmail Fetch - Retrieve calendar-related emails from last 24h
    2. Event Extract - Use LLM to extract event details
    3. Calendar Create - Create events in Google Calendar
    4. Send Digest - Notify user with daily digest (placeholder)

    Args:
        user_id: User ID to create plan for
        organization_id: Optional organization ID
        metadata: Optional metadata for the plan

    Returns:
        Task ready for execution

    Example:
        >>> plan = create_calendar_plan(user_id="user123")
        >>> # Plan can now be saved and executed by delegation orchestrator
    """
    logger.info(
        "Creating calendar assistant plan",
        user_id=user_id,
        organization_id=organization_id,
    )

    # Generate unique step IDs
    step_ids = {
        "gmail_fetch": f"step_{str(uuid.uuid4())[:8]}",
        "event_extract": f"step_{str(uuid.uuid4())[:8]}",
        "calendar_create": f"step_{str(uuid.uuid4())[:8]}",
        "send_digest": f"step_{str(uuid.uuid4())[:8]}",
    }

    # Step 1: Fetch emails from Gmail
    step_gmail_fetch = TaskStep(
        id=step_ids["gmail_fetch"],
        name="Fetch Calendar Emails",
        description="Retrieve calendar-related emails from Gmail in the last 24 hours",
        agent_type="gmail_fetch",
        domain="google",
        inputs={
            "user_id": user_id,
            "time_range": "24h",
            "filters": {
                "query": "subject:(calendar OR meeting OR appointment OR event) OR body:(calendar OR meeting OR appointment)",
                "max_results": 50,
            },
        },
        outputs={},
        dependencies=[],
        status=StepStatus.PENDING,
        checkpoint_required=False,  # Safe read operation
        is_critical=True,
        max_retries=3,
        fallback_config=FallbackConfig(
            apis=["gmail_api_fallback"],
            strategies=["use_cached_emails"],
        ),
    )

    # Step 2: Extract calendar events using LLM
    step_event_extract = TaskStep(
        id=step_ids["event_extract"],
        name="Extract Calendar Events",
        description="Use LLM to analyze emails and extract event details (title, time, location, attendees)",
        agent_type="event_extract",
        domain="google",
        inputs={
            "user_id": user_id,
            "emails": "{{gmail_fetch.outputs.emails}}",  # Template variable
            "extraction_prompt": """
Analyze the following emails and extract calendar events.
For each event, identify:
- Event title
- Start date/time
- End date/time (or duration)
- Location (if specified)
- Attendees (if specified)
- Description/notes

Return events as structured JSON array.
""",
        },
        outputs={},
        dependencies=[step_ids["gmail_fetch"]],
        status=StepStatus.PENDING,
        checkpoint_required=False,  # LLM analysis is safe
        is_critical=True,
        max_retries=2,
        fallback_config=FallbackConfig(
            models=[
                "anthropic/claude-3-5-sonnet",
                "openai/gpt-4o",
                "anthropic/claude-3-haiku",
            ],
            strategies=["simple_pattern_extraction"],
        ),
    )

    # Step 3: Create events in Google Calendar
    step_calendar_create = TaskStep(
        id=step_ids["calendar_create"],
        name="Create Calendar Events",
        description="Create extracted events in Google Calendar",
        agent_type="calendar_create",
        domain="google",
        inputs={
            "user_id": user_id,
            "events": "{{event_extract.outputs.events}}",  # Template variable
            "calendar_id": "primary",
            "send_notifications": False,  # Don't spam attendees
        },
        outputs={},
        dependencies=[step_ids["event_extract"]],
        status=StepStatus.PENDING,
        checkpoint_required=True,  # External API write - requires approval
        checkpoint_config=CheckpointConfig(
            name="calendar_event_creation",
            description="Review and approve calendar events before creation",
            approval_type=ApprovalType.EXPLICIT,
            timeout_minutes=120,  # 2 hour timeout
            preference_key="calendar_assistant.auto_approve_events",
            required_approvers=1,
            preview_fields=["events", "calendar_id"],
        ),
        is_critical=True,
        max_retries=1,  # Don't retry writes without approval
        fallback_config=FallbackConfig(
            strategies=["skip_duplicate_events", "merge_similar_events"],
        ),
    )

    # Step 4: Send daily digest notification (placeholder)
    step_send_digest = TaskStep(
        id=step_ids["send_digest"],
        name="Send Daily Digest",
        description="Send notification with summary of created events",
        agent_type="mimic_notify",
        domain=None,  # Cross-domain: uses Mimic service
        inputs={
            "user_id": user_id,
            "notification_type": "calendar_digest",
            "template": "calendar_assistant_daily",
            "data": {
                "created_events": "{{calendar_create.outputs.created_events}}",
                "skipped_events": "{{calendar_create.outputs.skipped_events}}",
                "errors": "{{calendar_create.outputs.errors}}",
            },
        },
        outputs={},
        dependencies=[step_ids["calendar_create"]],
        status=StepStatus.PENDING,
        checkpoint_required=False,  # Notification is non-critical
        is_critical=False,  # Can skip if notification fails
        max_retries=2,
        fallback_config=FallbackConfig(
            strategies=["email_fallback", "skip_notification"],
        ),
    )

    # Create the plan document
    plan = Task(
        id=str(uuid.uuid4()),
        version=1,
        user_id=user_id,
        organization_id=organization_id,
        goal="Automatically detect calendar events from emails and add them to Google Calendar",
        constraints={
            "max_events_per_run": 20,
            "require_approval_for_creation": True,
            "skip_past_events": True,
            "dedup_window_days": 7,
        },
        success_criteria=[
            "All calendar-related emails analyzed",
            "Events extracted with >90% accuracy",
            "No duplicate events created",
            "User notified of results",
        ],
        steps=[
            step_gmail_fetch,
            step_event_extract,
            step_calendar_create,
            step_send_digest,
        ],
        accumulated_findings=[],
        current_step_index=0,
        status=TaskStatus.READY,
        tree_id=None,  # Will be set when execution starts
        parent_task_id=None,
        metadata={
            **(metadata or {}),
            "plan_type": "calendar_assistant",
            "automation_level": "semi_automatic",  # Requires approval for writes
            "recurring": True,  # Can be scheduled to run periodically
        },
    )

    logger.info(
        "Calendar assistant plan created",
        plan_id=plan.id,
        user_id=user_id,
        step_count=len(plan.steps),
    )

    return plan


def create_calendar_plan_from_dict(
    user_id: str,
    plan_config: Dict[str, Any],
) -> Task:
    """
    Create a calendar plan with custom configuration.

    Allows overriding default settings for advanced use cases.

    Args:
        user_id: User ID to create plan for
        plan_config: Configuration dictionary with optional overrides:
            - time_range: Email fetch time range (default: "24h")
            - max_events: Maximum events to process (default: 20)
            - auto_approve: Skip checkpoint if True (default: False)
            - notification_enabled: Send digest notification (default: True)

    Returns:
        Task with custom configuration
    """
    # Extract config with defaults
    time_range = plan_config.get("time_range", "24h")
    max_events = plan_config.get("max_events", 20)
    auto_approve = plan_config.get("auto_approve", False)
    notification_enabled = plan_config.get("notification_enabled", True)

    # Create base plan
    plan = create_calendar_plan(
        user_id=user_id,
        organization_id=plan_config.get("organization_id"),
        metadata=plan_config.get("metadata"),
    )

    # Apply overrides
    # Update gmail_fetch time_range
    plan.steps[0].inputs["time_range"] = time_range

    # Update constraints
    plan.constraints["max_events_per_run"] = max_events

    # Auto-approve if configured
    if auto_approve:
        calendar_step = plan.steps[2]  # calendar_create step
        calendar_step.checkpoint_required = False
        calendar_step.checkpoint_config = None
        plan.metadata["automation_level"] = "fully_automatic"

    # Remove digest notification if disabled
    if not notification_enabled:
        plan.steps = plan.steps[:3]  # Remove send_digest step

    logger.info(
        "Custom calendar assistant plan created",
        plan_id=plan.id,
        user_id=user_id,
        time_range=time_range,
        auto_approve=auto_approve,
        notification_enabled=notification_enabled,
    )

    return plan
