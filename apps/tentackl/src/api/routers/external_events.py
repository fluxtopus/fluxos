# REVIEW:
# - Router owns auth, idempotency, gateway dispatch, and persistence; many responsibilities in one module.
# - Uses a module-level Redis client without lifecycle cleanup; connection leaks are possible.
# - Authentication logic is separate from auth_middleware and may drift in policy/behavior.
"""API routes for external event publishing via Event Gateway."""

from fastapi import APIRouter, HTTPException, Header, Request, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging
import asyncio
import redis.asyncio as redis_async

from src.interfaces.event_bus import (
    EventSource, EventSourceType, RawEvent, Event
)
from src.event_bus.event_gateway import EventGateway
from src.event_bus.redis_event_bus import RedisEventBus
from src.interfaces.database import Database
from src.database.external_event_models import ExternalPublisher
from src.api.rate_limiter import rate_limit_webhook
from src.api.auth_middleware import auth_middleware, AuthUser
from src.core.config import settings
from src.api.error_helpers import safe_error_detail
from sqlalchemy import select
import hashlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["external-events"])

# Component instances (initialized in app startup)
event_gateway: Optional[EventGateway] = None
event_bus: Optional[RedisEventBus] = None
database: Optional[Database] = None
redis_client: Optional[redis_async.Redis] = None

# Idempotency key TTL in seconds (5 minutes)
IDEMPOTENCY_TTL = 300


async def get_redis_client() -> redis_async.Redis:
    """Get or create Redis client for idempotency checks."""
    global redis_client
    if redis_client is None:
        redis_client = await redis_async.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client


def get_event_gateway() -> EventGateway:
    """Get the event gateway instance."""
    if not event_gateway:
        raise HTTPException(status_code=503, detail="Event gateway not initialized")
    return event_gateway


def get_event_bus() -> RedisEventBus:
    """Get the event bus instance."""
    if not event_bus:
        raise HTTPException(status_code=503, detail="Event bus not initialized")
    return event_bus


def get_database() -> Database:
    """Get the database instance."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


class WebhookEventRequest(BaseModel):
    """Request body for webhook events."""
    event_type: str = Field(..., description="Type of event")
    data: Dict[str, Any] = Field(..., description="Event payload")
    workflow_id: Optional[str] = Field(None, description="Target workflow ID")
    agent_id: Optional[str] = Field(None, description="Target agent ID")
    timestamp: Optional[datetime] = Field(None, description="Event timestamp")
    
    @validator('data')
    def validate_data_size(cls, v):
        """Validate event data size."""
        data_str = json.dumps(v)
        if len(data_str) > 1024 * 1024:  # 1MB limit
            raise ValueError("Event data exceeds 1MB limit")
        return v


class WebhookEventResponse(BaseModel):
    """Response from webhook event."""
    success: bool
    event_id: str
    message: str = "Event received"


class RegisterSourceRequest(BaseModel):
    """Request to register an event source."""
    name: str = Field(..., description="Source name")
    source_type: str = Field(..., description="Source type (webhook, websocket, message_queue)")
    endpoint: Optional[str] = Field(None, description="Webhook endpoint path")
    authentication_type: str = Field("api_key", description="Authentication type")
    rate_limit_requests: Optional[int] = Field(100, description="Max requests per window")
    rate_limit_window_seconds: Optional[int] = Field(60, description="Rate limit window in seconds")
    required_fields: List[str] = Field(default_factory=list, description="Required fields in event data")
    active: bool = Field(True, description="Whether source is active")


class RegisterSourceResponse(BaseModel):
    """Response from source registration."""
    success: bool
    source_id: str
    api_key: Optional[str] = Field(None, description="Generated API key (only shown once)")


async def authenticate_webhook(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    x_api_key: Optional[str] = Header(None),
    x_webhook_signature: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Authenticate webhook request."""
    credentials = {}
    
    if x_api_key:
        credentials['api_key'] = x_api_key
    if authorization:
        credentials['bearer_token'] = authorization.credentials
    
    if x_webhook_signature:
        credentials['signature'] = x_webhook_signature
        
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication credentials provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return credentials


@router.post("/webhook/{source_id}", response_model=WebhookEventResponse)
async def receive_webhook_event(
    source_id: str,
    request: WebhookEventRequest,
    raw_request: Request,
    _rate_limit: None = Depends(rate_limit_webhook(max_requests=10, window_seconds=60)),
    credentials: Dict[str, Any] = Depends(authenticate_webhook),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    """
    Receive webhook event from external source.

    Authentication methods:
    - API Key: X-API-Key header
    - Bearer Token: Authorization: Bearer <token>
    - HMAC Signature: X-Webhook-Signature header

    Idempotency:
    - X-Idempotency-Key header: Optional unique key to prevent duplicate processing
    - If not provided, a key is generated from source_id + request body hash
    - Duplicate requests within 5 minutes return 200 with already_processed status
    """
    try:
        gateway = get_event_gateway()
        bus = get_event_bus()
        redis = await get_redis_client()

        # Generate idempotency key if not provided
        if not x_idempotency_key:
            # Create deterministic key from source_id and request body
            body_bytes = await raw_request.body()
            body_hash = hashlib.sha256(body_bytes).hexdigest()[:16]
            x_idempotency_key = f"{source_id}:{body_hash}"

        # Check if already processed (fast Redis check)
        dedup_key = f"tentackl:webhook:processed:{x_idempotency_key}"
        is_new = await redis.set(dedup_key, "1", nx=True, ex=IDEMPOTENCY_TTL)

        if not is_new:
            # Already processed - return success to prevent external retries
            logger.info(
                f"Duplicate webhook request - already processed - source: {source_id}, key: {x_idempotency_key}"
            )
            return WebhookEventResponse(
                success=True,
                event_id=f"duplicate:{x_idempotency_key}",
                message="Event already processed (duplicate request)"
            )

        # Debug logging
        logger.info(f"Webhook request for source {source_id}")
        logger.info(f"Credentials provided: {list(credentials.keys())}")
        
        # Authenticate source
        auth_valid = await gateway.authenticate_source(source_id, credentials)
        logger.info(f"Authentication result: {auth_valid}")
        
        if not auth_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        # Get request headers for validation
        headers = dict(raw_request.headers)
        
        # Create raw event
        raw_event = RawEvent(
            source_id=source_id,
            data=request.data,  # Pass just the data field, not the entire request
            headers=headers,
            timestamp=request.timestamp or datetime.utcnow()
        )
        
        # Validate and normalize event
        try:
            event = await gateway.validate_event(raw_event)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=safe_error_detail(f"Event validation failed: {str(e)}")
            )
        
        # Override event type, data and IDs if provided
        if request.event_type:
            event.event_type = request.event_type
        # Ensure the original body is preserved as event data
        if request.data is not None:
            event.data = request.data
        if request.workflow_id:
            event.workflow_id = request.workflow_id
        if request.agent_id:
            event.agent_id = request.agent_id

        # Prefix event type with external.webhook. for routing to EventTriggerWorker
        # This allows the worker to subscribe to external.webhook.* pattern
        if not event.event_type.startswith("external.webhook."):
            event.event_type = f"external.webhook.{event.event_type}"

        # Publish to event bus
        success = await bus.publish(event)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to publish event"
            )
        
        logger.info(
            f"Webhook event received - source: {source_id}, event_id: {event.id}, type: {event.event_type}"
        )
        
        return WebhookEventResponse(
            success=True,
            event_id=event.id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.post("/sources/register", response_model=RegisterSourceResponse)
async def register_event_source(
    request: RegisterSourceRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("events", "admin"))
):
    """
    Register a new event source.

    Requires admin authentication via InkPass.
    """
    try:
        gateway = get_event_gateway()
        db = get_database()
        
        # Generate API key for the source
        import secrets
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hash_api_key(api_key)
        
        # Create event source
        source = EventSource(
            name=request.name,
            source_type=EventSourceType(request.source_type),
            config={
                "endpoint": request.endpoint,
                "required_fields": request.required_fields,
                "rate_limit": {
                    "max_requests": request.rate_limit_requests,
                    "window_seconds": request.rate_limit_window_seconds
                }
            },
            authentication={
                "type": request.authentication_type,
                "api_key": api_key  # Store the key
            },
            active=request.active
        )
        
        # For webhook sources, create ExternalPublisher record in database
        if request.source_type == "webhook":
            async with db.get_session() as session:
                # Check if name already exists
                result = await session.execute(
                    select(ExternalPublisher).where(ExternalPublisher.name == request.name)
                )
                if result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Source with this name already exists"
                    )
                
                # Create new publisher
                publisher = ExternalPublisher(
                    name=request.name,
                    api_key_hash=api_key_hash,
                    permissions=["publish_events"],
                    rate_limit=request.rate_limit_requests,
                    is_active=request.active
                )
                session.add(publisher)
                await session.commit()
                logger.info(f"Created ExternalPublisher record for {request.name}")
        
        # Register source in Redis
        success = await gateway.register_source(source)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to register source"
            )
        
        logger.info(f"Event source registered: {source.name} ({source.id})")
        
        return RegisterSourceResponse(
            success=True,
            source_id=source.id,
            api_key=api_key  # Return key only on creation
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering event source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.get("/sources")
async def list_event_sources(
    user: AuthUser = Depends(auth_middleware.require_permission("events", "admin"))
):
    """
    List registered event sources.

    Requires admin authentication via InkPass.
    """
    try:
        # For now, return empty list as we don't have a list method in gateway
        # This would be implemented by querying Redis for all sources
        return {
            "sources": [],
            "total": 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing event sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.post("/publish/batch")
async def publish_batch_events(
    events: List[WebhookEventRequest],
    user: AuthUser = Depends(auth_middleware.require_permission("events", "publish"))
):
    """
    Publish multiple events in a single request.
    
    Useful for bulk event ingestion.
    """
    try:
        # Limit batch size
        if len(events) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size exceeds limit of 100 events"
            )
        
        bus = get_event_bus()
        results = []
        
        for event_request in events:
            try:
                # Create event
                event = Event(
                    source="batch_api",
                    source_type=EventSourceType.WEBHOOK,
                    event_type=event_request.event_type,
                    data=event_request.data,
                    workflow_id=event_request.workflow_id,
                    agent_id=event_request.agent_id,
                    timestamp=event_request.timestamp or datetime.utcnow()
                )
                
                # Publish
                success = await bus.publish(event)
                
                results.append({
                    "event_type": event.event_type,
                    "event_id": event.id,
                    "success": success
                })
                
            except Exception as e:
                results.append({
                    "event_type": event_request.event_type,
                    "success": False,
                    "error": str(e)
                })
        
        # Calculate summary
        successful = sum(1 for r in results if r.get("success", False))
        
        return {
            "total": len(events),
            "successful": successful,
            "failed": len(events) - successful,
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch event publishing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.get("/replay")
async def replay_events(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    event_types: Optional[str] = None,  # Comma-separated list
    workflow_id: Optional[str] = None,
    limit: int = 100,
    user: AuthUser = Depends(auth_middleware.require_permission("events", "view"))
):
    """
    Replay historical events.
    
    Requires authentication.
    """
    try:
        bus = get_event_bus()
        
        # Parse event types
        event_type_list = None
        if event_types:
            event_type_list = [t.strip() for t in event_types.split(",")]
        
        # Replay events
        events = await bus.replay_events(
            start_time=start_time,
            end_time=end_time,
            event_types=event_type_list,
            workflow_id=workflow_id,
            limit=min(limit, 1000)  # Cap at 1000
        )
        
        # Convert to response format
        return {
            "events": [
                {
                    "id": event.id,
                    "source": event.source,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "workflow_id": event.workflow_id,
                    "agent_id": event.agent_id
                }
                for event in events
            ],
            "total": len(events)
        }
        
    except Exception as e:
        logger.error(f"Error replaying events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(str(e))
        )


@router.get("/health")
async def event_api_health():
    """Check health of event API components."""
    try:
        gateway = get_event_gateway()
        bus = get_event_bus()
        
        # Basic health check
        health = {
            "status": "healthy",
            "components": {
                "event_gateway": gateway._initialized,
                "event_bus": bus._running
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return health
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.websocket("/ws/{source_id}")
async def websocket_event_stream(
    websocket: WebSocket,
    source_id: str
):
    """
    WebSocket endpoint for real-time event streaming.
    
    Connect with: ws://localhost:8000/api/events/ws/{source_id}?api_key={your_api_key}
    
    Receive events in real-time as they are published.
    """
    # Get API key from query parameters
    api_key = websocket.query_params.get("api_key")
    
    # Authenticate the connection
    if api_key:
        gateway = get_event_gateway()
        auth_valid = await gateway.authenticate_source(source_id, {"api_key": api_key})
        if not auth_valid:
            await websocket.close(code=4001, reason="Authentication failed")
            return
    else:
        await websocket.close(code=4001, reason="API key required")
        return
    
    await websocket.accept()
    logger.info(f"WebSocket connected for source {source_id}")
    
    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "source_id": source_id,
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Connected to event stream"
    })
    
    # Subscribe to events for this source
    bus = get_event_bus()
    redis_client = None
    pubsub = None
    
    try:
        # Connect to Redis for event subscription
        import redis.asyncio as redis_async
        from src.core.config import settings
        redis_client = await redis_async.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        
        # Subscribe to all events - in a real system, we'd filter by source
        # For now, subscribe to all events channel
        # Note: The event bus uses "tentackl:eventbus" as prefix
        channel = "tentackl:eventbus:events:all"
        await pubsub.subscribe(channel)
        
        # Create tasks for listening to both Redis and WebSocket
        async def listen_redis():
            async for message in pubsub.listen():
                # Skip subscription confirmation messages
                if message['type'] == 'subscribe':
                    logger.info(f"Subscribed to Redis channel: {message['channel']}")
                    continue
                    
                if message['type'] == 'message':
                    try:
                        event_data = json.loads(message['data'])
                        event_source_id = (event_data.get("metadata") or {}).get("source_id")
                        if event_source_id != source_id:
                            continue
                        await websocket.send_json({
                            "type": "event",
                            "timestamp": datetime.utcnow().isoformat(),
                            "event": event_data
                        })
                        logger.info(f"Forwarded event to WebSocket: {event_data.get('id', 'unknown')}")
                    except Exception as e:
                        logger.error(f"Error forwarding event: {e}")
        
        async def listen_websocket():
            while True:
                try:
                    data = await websocket.receive_json()
                    if data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif data.get("type") == "subscribe":
                        # Handle subscription updates
                        pattern = data.get("pattern", "*")
                        await websocket.send_json({
                            "type": "subscription_updated",
                            "pattern": pattern
                        })
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"WebSocket receive error: {e}")
                    break
        
        # Run both listeners concurrently
        await asyncio.gather(
            listen_redis(),
            listen_websocket()
        )
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for source {source_id}")
    except Exception as e:
        logger.error(f"WebSocket error for source {source_id}: {e}")
        await websocket.close(code=1011, reason="Internal server error")
    finally:
        # Cleanup
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.close()
        if redis_client:
            await redis_client.close()
        logger.info(f"WebSocket cleanup completed for source {source_id}")
