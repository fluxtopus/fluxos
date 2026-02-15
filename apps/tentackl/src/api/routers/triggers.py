"""
# REVIEW:
# - Lazy-initialized TaskTriggerRegistry singleton in router; lifecycle not managed.
# - SSE streams open Redis pubsub per connection; ensure close on disconnect to avoid leaks.
Triggers API - Manage event-driven task triggers.

Endpoints:
- GET /api/triggers - List all triggers for the org
- GET /api/triggers/{task_id} - Get a specific trigger
- GET /api/triggers/{task_id}/events - SSE stream of trigger events
- GET /api/triggers/{task_id}/history - Recent trigger executions
- DELETE /api/triggers/{task_id} - Remove a trigger
- PATCH /api/triggers/{task_id} - Enable/disable a trigger
"""

import asyncio
import json
from typing import List, Literal, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog
import redis.asyncio as redis

from src.api.auth_middleware import auth_middleware, AuthUser
from src.application.triggers import TriggerNotFound, TriggerUpdateError, TriggerUseCases
from src.infrastructure.triggers.trigger_registry_adapter import TriggerRegistryAdapter
from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry
from src.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


def _get_org_id(user: AuthUser) -> str:
    """Extract organization_id from AuthUser metadata."""
    org_id = user.metadata.get("organization_id") if user.metadata else None
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")
    return org_id

# Shared registry instance
_trigger_registry: Optional[TaskTriggerRegistry] = None


async def get_trigger_registry() -> TaskTriggerRegistry:
    """Get or create the trigger registry instance."""
    global _trigger_registry
    if _trigger_registry is None:
        _trigger_registry = TaskTriggerRegistry()
        await _trigger_registry.initialize()
    return _trigger_registry


def get_trigger_use_cases(
    registry: TaskTriggerRegistry = Depends(get_trigger_registry),
) -> TriggerUseCases:
    """Provide application-layer trigger use cases."""
    return TriggerUseCases(registry=TriggerRegistryAdapter(registry))


class TriggerResponse(BaseModel):
    """Response model for a single trigger."""
    task_id: str
    organization_id: str
    user_id: Optional[str] = None
    event_pattern: str
    source_filter: Optional[str] = None
    condition: Optional[dict] = None
    enabled: bool = True
    type: str = "event"
    scope: Literal["org", "user"] = "org"


class TriggerListResponse(BaseModel):
    """Response model for trigger list."""
    triggers: List[TriggerResponse]
    count: int


class TriggerUpdateRequest(BaseModel):
    """Request model for updating a trigger."""
    enabled: Optional[bool] = None


class TriggerExecution(BaseModel):
    """Model for a trigger execution history entry."""
    id: str
    event_id: str
    task_execution_id: Optional[str] = None
    status: Literal["running", "completed", "failed"]
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class TriggerHistoryResponse(BaseModel):
    """Response model for trigger history."""
    executions: List[TriggerExecution]
    count: int


def _make_trigger_response(task_id: str, config: dict) -> TriggerResponse:
    """Convert trigger config to response model with computed scope."""
    user_id = config.get("user_id")
    scope: Literal["org", "user"] = "user" if user_id else "org"
    return TriggerResponse(
        task_id=task_id,
        organization_id=config.get("organization_id", ""),
        user_id=user_id,
        event_pattern=config.get("event_pattern", ""),
        source_filter=config.get("source_filter"),
        condition=config.get("condition"),
        enabled=config.get("enabled", True),
        type=config.get("type", "event"),
        scope=scope,
    )


@router.get("", response_model=TriggerListResponse)
async def list_triggers(
    scope: Optional[Literal["all", "org", "user"]] = "all",
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
) -> TriggerListResponse:
    """
    List all triggers for the authenticated user's organization.

    Query params:
    - scope: Filter by trigger scope ("all", "org", "user")
    """
    org_id = _get_org_id(auth_user)

    triggers = await use_cases.list_triggers(org_id, auth_user.id, scope)

    return TriggerListResponse(
        triggers=[_make_trigger_response(t["task_id"], t) for t in triggers],
        count=len(triggers),
    )


@router.get("/{task_id}", response_model=TriggerResponse)
async def get_trigger(
    task_id: str,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
) -> TriggerResponse:
    """
    Get a specific trigger by task ID.
    """
    org_id = _get_org_id(auth_user)

    try:
        config = await use_cases.get_trigger(task_id, org_id, auth_user.id)
        return _make_trigger_response(task_id, config)
    except TriggerNotFound:
        raise HTTPException(status_code=404, detail="Trigger not found")


@router.get("/{task_id}/events")
async def trigger_events_stream(
    task_id: str,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
):
    """
    SSE stream of trigger events.

    Emits events when:
    - trigger.matched - Event matched pattern
    - trigger.executed - Task started
    - trigger.completed - Task completed
    - trigger.failed - Task failed
    """
    org_id = _get_org_id(auth_user)

    try:
        await use_cases.get_trigger(task_id, org_id, auth_user.id)
    except TriggerNotFound:
        raise HTTPException(status_code=404, detail="Trigger not found")

    async def event_generator():
        """Generate SSE events for trigger activity."""
        redis_client = None
        pubsub = None
        try:
            redis_client = await redis.from_url(
                settings.REDIS_URL,
                decode_responses=True
            )
            pubsub = redis_client.pubsub()

            # Subscribe to trigger events channel
            channel = f"tentackl:trigger:events:{task_id}"
            await pubsub.subscribe(channel)

            # Send initial connected event
            yield f"event: connected\ndata: {json.dumps({'task_id': task_id})}\n\n"

            # Listen for events with heartbeat
            heartbeat_interval = 30  # seconds
            last_heartbeat = asyncio.get_event_loop().time()

            async for message in pubsub.listen():
                current_time = asyncio.get_event_loop().time()

                # Send heartbeat if needed
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = current_time

                if message.get("type") != "message":
                    continue

                try:
                    data = json.loads(message.get("data", "{}"))
                    event_type = data.get("type", "trigger.event")
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                except json.JSONDecodeError:
                    logger.warning(
                        "Invalid JSON in trigger event",
                        task_id=task_id,
                        data=message.get("data"),
                    )

        except asyncio.CancelledError:
            logger.debug("Trigger SSE stream cancelled", task_id=task_id)
        except Exception as e:
            logger.error(
                "Error in trigger SSE stream",
                task_id=task_id,
                error=str(e),
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if pubsub:
                await pubsub.close()
            if redis_client:
                await redis_client.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}/history", response_model=TriggerHistoryResponse)
async def get_trigger_history(
    task_id: str,
    limit: int = 20,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "view")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
) -> TriggerHistoryResponse:
    """
    Get recent execution history for a trigger.
    """
    org_id = _get_org_id(auth_user)

    try:
        executions = await use_cases.get_trigger_history(
            task_id=task_id,
            org_id=org_id,
            user_id=auth_user.id,
            limit=limit,
        )
    except TriggerNotFound:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return TriggerHistoryResponse(
        executions=[TriggerExecution(**e) for e in executions],
        count=len(executions),
    )


@router.delete("/{task_id}")
async def delete_trigger(
    task_id: str,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "update")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
) -> dict:
    """
    Delete a trigger by task ID.
    """
    org_id = _get_org_id(auth_user)

    try:
        await use_cases.delete_trigger(task_id, org_id, auth_user.id)
    except TriggerNotFound:
        raise HTTPException(status_code=404, detail="Trigger not found")
    except TriggerUpdateError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    logger.info(
        "Trigger deleted",
        task_id=task_id,
        organization_id=org_id,
        user_id=auth_user.id,
    )

    return {"success": True, "task_id": task_id}


@router.patch("/{task_id}", response_model=TriggerResponse)
async def update_trigger(
    task_id: str,
    request: TriggerUpdateRequest,
    auth_user: AuthUser = Depends(auth_middleware.require_permission("tasks", "update")),
    use_cases: TriggerUseCases = Depends(get_trigger_use_cases),
) -> TriggerResponse:
    """
    Update a trigger (enable/disable).
    """
    org_id = _get_org_id(auth_user)

    try:
        updated_config = await use_cases.update_trigger(
            task_id=task_id,
            org_id=org_id,
            user_id=auth_user.id,
            enabled=request.enabled,
        )
    except TriggerNotFound:
        raise HTTPException(status_code=404, detail="Trigger not found")
    except TriggerUpdateError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    logger.info(
        "Trigger updated",
        task_id=task_id,
        updates={"enabled": request.enabled} if request.enabled is not None else {},
        organization_id=org_id,
    )

    return _make_trigger_response(task_id, updated_config)
