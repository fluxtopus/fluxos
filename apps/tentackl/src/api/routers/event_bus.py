# REVIEW:
# - Global event_bus injected at startup; no fallback or lazy init; tight coupling to app lifecycle.
# - Subscriber_id and patterns are accepted unchecked; could allow unbounded subscription growth.
"""API routes for Event Bus operations."""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from src.interfaces.event_bus import (
    EventSubscription,
)
from src.database.conversation_store import ConversationStore
from src.event_bus.redis_event_bus import RedisEventBus
from src.application.events import EventBusUseCases
from src.infrastructure.events import RedisEventBusAdapter, OrchestratorConversationAdapter
from src.api.error_helpers import safe_error_detail

# Authentication
from src.api.auth_middleware import (
    auth_middleware,
    AuthUser,
    inkpass_check_permission,
    inkpass_validate_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/event-bus", tags=["event-bus"])

# Event Bus instance (initialized in app startup)
event_bus: Optional[RedisEventBus] = None
conversation_store: Optional[ConversationStore] = None
event_bus_use_cases: Optional[EventBusUseCases] = None


def get_event_bus() -> RedisEventBus:
    """Get the event bus instance."""
    if not event_bus:
        raise HTTPException(status_code=503, detail="Event bus not initialized")
    return event_bus


def get_event_bus_use_cases() -> EventBusUseCases:
    """Get event-bus use cases composed from runtime adapters."""
    global event_bus_use_cases
    if event_bus_use_cases is not None:
        return event_bus_use_cases

    bus = get_event_bus()
    conversation_ops = (
        OrchestratorConversationAdapter(conversation_store)
        if conversation_store is not None
        else None
    )
    event_bus_use_cases = EventBusUseCases(
        event_bus_ops=RedisEventBusAdapter(bus),
        conversation_ops=conversation_ops,
    )
    return event_bus_use_cases


class PublishEventRequest(BaseModel):
    """Request to publish an event."""
    source: str = Field(..., description="Event source identifier")
    event_type: str = Field(..., description="Type of event")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    workflow_id: Optional[str] = Field(None, description="Associated workflow ID")
    agent_id: Optional[str] = Field(None, description="Associated agent ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Event metadata")


class PublishEventResponse(BaseModel):
    """Response from publishing an event."""
    success: bool
    event_id: str
    timestamp: str


class CreateSubscriptionRequest(BaseModel):
    """Request to create an event subscription."""
    subscriber_id: str = Field(..., description="ID of the subscriber (agent/component)")
    event_pattern: str = Field(..., description="Pattern to match events (supports wildcards)")
    filter: Optional[Dict[str, Any]] = Field(None, description="Optional event filter")
    transform: Optional[Dict[str, Any]] = Field(None, description="Optional data transformation")


class CreateSubscriptionResponse(BaseModel):
    """Response from creating a subscription."""
    success: bool
    subscription_id: str


class SendMessageRequest(BaseModel):
    """Request to send a message to an orchestrator."""
    message: str = Field(..., description="Message content")
    sender_id: Optional[str] = Field("web_user", description="Sender identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class SendMessageResponse(BaseModel):
    """Response from sending a message."""
    success: bool
    event_id: str
    message: str = "Message sent successfully"


@router.post("/publish", response_model=PublishEventResponse)
async def publish_event(
    request: PublishEventRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("events", "publish"))
):
    """Publish an event to the event bus."""
    try:
        use_cases = get_event_bus_use_cases()
        success, event_id, timestamp = await use_cases.publish_event(
            source=request.source,
            event_type=request.event_type,
            data=request.data,
            metadata=request.metadata or {},
            workflow_id=request.workflow_id,
            agent_id=request.agent_id,
        )
        return PublishEventResponse(
            success=success,
            event_id=event_id,
            timestamp=timestamp.isoformat(),
        )
    except Exception as e:
        logger.error(f"Error publishing event: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.post("/subscribe", response_model=CreateSubscriptionResponse)
async def create_subscription(
    request: CreateSubscriptionRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("events", "view"))
):
    """Create a new event subscription."""
    try:
        use_cases = get_event_bus_use_cases()
        subscription_id = await use_cases.create_subscription(
            subscriber_id=request.subscriber_id,
            event_pattern=request.event_pattern,
            event_filter=request.filter,
            transform=request.transform,
        )
        return CreateSubscriptionResponse(
            success=True,
            subscription_id=subscription_id
        )
        
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.delete("/subscribe/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("events", "view"))
):
    """Delete an event subscription."""
    try:
        use_cases = get_event_bus_use_cases()
        success = await use_cases.delete_subscription(subscription_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        return {"success": True, "message": "Subscription deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subscription: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.get("/subscriptions")
async def list_subscriptions(
    subscriber_id: Optional[str] = None,
    current_user: AuthUser = Depends(auth_middleware.require_permission("events", "view"))
):
    """List event subscriptions."""
    try:
        use_cases = get_event_bus_use_cases()
        subscriptions = await use_cases.list_subscriptions(subscriber_id)
        
        return {
            "subscriptions": subscriptions,
        }
        
    except Exception as e:
        logger.error(f"Error listing subscriptions: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.post("/orchestrator/{workflow_id}/message", response_model=SendMessageResponse)
async def send_message_to_orchestrator(
    workflow_id: str,
    request: SendMessageRequest,
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "control"))
):
    """Send a message to an orchestrator agent via the event bus."""
    try:
        use_cases = get_event_bus_use_cases()
        success, event_id = await use_cases.send_orchestrator_message(
            workflow_id=workflow_id,
            message=request.message,
            sender_id=request.sender_id or "web_user",
            metadata=request.metadata or {},
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send message")
        logger.info("User message sent to orchestrator", workflow_id=workflow_id)
        return SendMessageResponse(
            success=True,
            event_id=event_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message to orchestrator: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.get("/orchestrator/{workflow_id}/conversations")
async def get_orchestrator_conversations(
    workflow_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """Get conversation history for the orchestrator chat."""
    try:
        use_cases = get_event_bus_use_cases()
        return await use_cases.get_orchestrator_conversation_history(workflow_id)
    except Exception as e:
        logger.error(f"Error fetching orchestrator conversations: {e}")
        raise HTTPException(status_code=500, detail=safe_error_detail(str(e)))


@router.websocket("/ws/events/{subscriber_id}")
async def event_stream(websocket: WebSocket, subscriber_id: str):
    """WebSocket endpoint for real-time event streaming."""
    authorization = websocket.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        await websocket.close(code=4401, reason="Authentication required")
        return

    try:
        user = await inkpass_validate_token(token)
        if not user:
            await websocket.close(code=4401, reason="Invalid credentials")
            return

        can_view_events = await inkpass_check_permission(
            token=token,
            resource="events",
            action="view",
        )
        if not can_view_events:
            await websocket.close(code=4403, reason="Permission denied")
            return

        requested_pattern = websocket.query_params.get("pattern") or "external.webhook.*"
        can_admin_events = await inkpass_check_permission(
            token=token,
            resource="events",
            action="admin",
        )
        if requested_pattern == "*" and not can_admin_events:
            await websocket.close(code=4403, reason="Wildcard subscriptions require events:admin")
            return
    except Exception as e:
        logger.error("WebSocket auth failed", error=str(e))
        await websocket.close(code=1011, reason="Authentication error")
        return

    await websocket.accept()
    logger.info(
        f"🔌 Event stream connected for subscriber '{subscriber_id}'",
        user_id=user.id,
        pattern=requested_pattern,
    )
    
    try:
        # Create subscription for all events
        bus = get_event_bus()
        subscription = EventSubscription(
            subscriber_id=f"ws_{subscriber_id}",
            event_pattern=requested_pattern,
        )
        
        sub_id = await bus.subscribe(subscription)
        
        # Keep connection alive and forward events
        while True:
            try:
                # Check for events in subscriber queue
                # (This is simplified - in production would use proper queue consumer)
                data = await websocket.receive_json()
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
        
        # Cleanup subscription
        await bus.unsubscribe(sub_id)
        
    except Exception as e:
        logger.error(f"Event stream error for '{subscriber_id}': {e}")
    finally:
        logger.info(f"🔌 Event stream disconnected for subscriber '{subscriber_id}'")
