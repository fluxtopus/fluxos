"""Redis-based implementation of the Event Bus interfaces."""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
import redis.asyncio as redis
import fnmatch

from src.interfaces.event_bus import (
    EventBusInterface, EventGatewayInterface, CallbackEngineInterface,
    Event, EventSubscription, EventSource, RawEvent, 
    Callback, CallbackResult, EventValidationError,
    EventPublishError, SubscriptionError
)
from src.interfaces.state_store import StateStoreInterface
from src.interfaces.context_manager import ContextManagerInterface
from src.agents.factory import AgentFactory
from src.core.config import settings
from src.event_bus.event_filter import EventFilter, EventTransformer
from src.monitoring.metrics import MetricsCollector, event_bus_messages, redis_operations
from src.monitoring.error_monitor import get_error_monitor

logger = logging.getLogger(__name__)


class RedisEventBus(EventBusInterface):
    """Redis-based Event Bus implementation."""

    def __init__(self, redis_url: str = None, db: int = 0, key_prefix: str = "tentackl:eventbus"):
        self.redis_url = redis_url or settings.REDIS_URL
        self.db = db
        self.key_prefix = key_prefix
        self._redis_client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._listeners: Dict[str, Set[str]] = {}  # event_pattern -> subscription_ids
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
        self._event_filter = EventFilter()
        self._event_transformer = EventTransformer()
        # In-memory callback handlers by subscription id (for simple subscribe(pattern, callback) usage)
        self._callback_handlers: Dict[str, List] = {}
        self._callback_patterns: List[tuple[str, str]] = []  # (pattern, subscription_id)
        # Track whether a pattern used pattern subscription ('p') or normal ('s')
        self._pattern_modes: Dict[str, str] = {}
        # Lock to ensure only one coroutine reads from pub/sub connection at a time
        self._pubsub_lock: Optional[asyncio.Lock] = None
    
    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if not self._redis_client:
            self._redis_client = await redis.from_url(
                self.redis_url,
                db=self.db,
                decode_responses=True
            )
            self._pubsub = self._redis_client.pubsub()
    
    async def start(self):
        """Start the event bus listener."""
        # Prevent multiple starts
        if self._running:
            logger.warning("Event bus already running, ignoring start request")
            return

        await self._ensure_connection()
        self._running = True
        self._pubsub_lock = asyncio.Lock()
        self._listener_task = asyncio.create_task(self._listen_for_events())
        logger.info("Event bus started")
    
    async def stop(self):
        """Stop the event bus."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.aclose()
        if self._redis_client:
            await self._redis_client.aclose()
        
        logger.info("Event bus stopped")
    
    async def publish(self, event: Event) -> bool:
        """Publish an event to the bus."""
        # Track request in error monitor
        error_monitor = get_error_monitor()
        if error_monitor:
            error_monitor.track_request("event_bus")
        
        try:
            await self._ensure_connection()

            # Track event processing
            with MetricsCollector.track_event_processing(event.event_type):
                # Serialize event
                event_data = {
                    "id": event.id,
                    "source": event.source,
                    "source_type": event.source_type.value,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "metadata": event.metadata,
                    "workflow_id": event.workflow_id,
                    "agent_id": event.agent_id
                }
                
                # First, directly notify any callback-based subscriptions (pattern matches)
                try:
                    for pattern, sub_id in list(self._callback_patterns):
                        if self._matches_pattern(event, pattern):
                            callbacks = self._callback_handlers.get(sub_id) or []
                            for cb in callbacks:
                                try:
                                    if asyncio.iscoroutinefunction(cb):
                                        await cb(event)
                                    else:
                                        cb(event)
                                except Exception as e:
                                    logger.error(f"Error in direct callback: {e}")
                except Exception as e:
                    logger.error(f"Error dispatching direct callbacks: {e}")

                # Publish to specific channels (for non-callback subscribers and history)
                channels = [
                    f"{self.key_prefix}:events:all",
                    f"{self.key_prefix}:events:type:{event.event_type}"
                ]
                
                if event.workflow_id:
                    channels.append(f"{self.key_prefix}:events:workflow:{event.workflow_id}")
                
                if event.agent_id:
                    channels.append(f"{self.key_prefix}:events:agent:{event.agent_id}")
                
                # Publish to all relevant channels
                for channel in channels:
                    with MetricsCollector.track_redis_operation("publish"):
                        await self._redis_client.publish(channel, json.dumps(event_data))
                
                # Store event for replay capability
                event_key = f"{self.key_prefix}:event:{event.id}"
                with MetricsCollector.track_redis_operation("setex"):
                    await self._redis_client.setex(
                        event_key,
                        86400,  # 24 hour TTL
                        json.dumps(event_data)
                    )
                
                # Add to event stream
                stream_key = f"{self.key_prefix}:stream:events"
                with MetricsCollector.track_redis_operation("xadd"):
                    await self._redis_client.xadd(
                        stream_key,
                        {"event": json.dumps(event_data)},
                        maxlen=10000  # Keep last 10k events
                    )
                
                # Track successful event
                MetricsCollector.track_event(event.event_type, event.source, "published")
                
                logger.debug(f"Published event {event.id} of type {event.event_type}")
                return True
            
        except Exception as e:
            # Track failed event
            MetricsCollector.track_event(event.event_type, event.source, "failed")
            logger.error(f"Failed to publish event: {e}")
            
            # Track error in error monitor
            if error_monitor:
                error_type = type(e).__name__.lower()
                error_monitor.track_error("event_bus", error_type, {
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "source": event.source,
                    "error": str(e)
                })
            
            raise EventPublishError(f"Failed to publish event: {e}")
    
    async def subscribe(self, subscription_or_pattern, callback=None) -> str:
        """Register an event subscription.

        Supports both:
          - subscribe(EventSubscription)
          - subscribe(pattern: str, callback: Callable[[Event], Awaitable|None])
        """
        try:
            await self._ensure_connection()

            if isinstance(subscription_or_pattern, EventSubscription):
                subscription = subscription_or_pattern
            else:
                # Convenience form: pattern + callback
                pattern = str(subscription_or_pattern)
                if callback is None:
                    raise SubscriptionError("Callback required when subscribing with a pattern string")
                subscription = EventSubscription(
                    subscriber_id=f"callback:{id(callback)}",
                    event_pattern=pattern,
                    filter=None,
                    transform=None,
                    callbacks=[],
                    active=True,
                )
                # Register handler
                self._callback_handlers[subscription.id] = [callback]
                self._callback_patterns.append((pattern, subscription.id))

            # Store subscription in memory
            self._subscriptions[subscription.id] = subscription

            # Persist metadata for non-callback subscriptions
            if subscription.id not in self._callback_handlers:
                sub_key = f"{self.key_prefix}:subscription:{subscription.id}"
                sub_data = {
                    "id": subscription.id,
                    "subscriber_id": subscription.subscriber_id,
                    "event_pattern": subscription.event_pattern,
                    "filter": json.dumps(subscription.filter) if subscription.filter else "",
                    "transform": json.dumps(subscription.transform) if subscription.transform else "",
                    "active": str(subscription.active),
                    "created_at": subscription.created_at.isoformat()
                }
                await self._redis_client.hset(sub_key, mapping=sub_data)

            # Track pattern listeners and subscribe to channels if new pattern
            # Only wire Redis listener for non-callback subscriptions
            if subscription.id not in self._callback_handlers:
                if subscription.event_pattern not in self._listeners:
                    self._listeners[subscription.event_pattern] = set()
                    await self._subscribe_to_pattern(subscription.event_pattern)
                self._listeners[subscription.event_pattern].add(subscription.id)

            logger.info(f"Registered subscription {subscription.id} for {subscription.subscriber_id}")
            return subscription.id

        except Exception as e:
            logger.error(f"Failed to create subscription: {e}")
            raise SubscriptionError(f"Failed to create subscription: {e}")
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Remove an event subscription."""
        try:
            await self._ensure_connection()
            
            # Get subscription
            subscription = self._subscriptions.get(subscription_id)
            if not subscription:
                return False
            
            # Remove from Redis if persisted
            if subscription_id not in self._callback_handlers:
                sub_key = f"{self.key_prefix}:subscription:{subscription_id}"
                await self._redis_client.delete(sub_key)
            
            # Remove from memory
            del self._subscriptions[subscription_id]
            
            # Update pattern listeners
            if subscription.event_pattern in self._listeners:
                self._listeners[subscription.event_pattern].discard(subscription_id)
                if not self._listeners[subscription.event_pattern]:
                    del self._listeners[subscription.event_pattern]
                    await self._unsubscribe_from_pattern(subscription.event_pattern)
            # Remove any callback handlers
            if subscription_id in self._callback_handlers:
                del self._callback_handlers[subscription_id]
                self._callback_patterns = [(p, sid) for (p, sid) in self._callback_patterns if sid != subscription_id]
            
            logger.info(f"Removed subscription {subscription_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False
    
    async def get_subscription(self, subscription_id: str) -> Optional[EventSubscription]:
        """Get a subscription by ID."""
        if subscription_id in self._subscriptions:
            return self._subscriptions[subscription_id]
        
        # Try to load from Redis
        await self._ensure_connection()
        sub_key = f"{self.key_prefix}:subscription:{subscription_id}"
        sub_data = await self._redis_client.hgetall(sub_key)
        
        if sub_data:
            # Reconstruct subscription
            # (simplified - would need full deserialization in production)
            return None
        
        return None
    
    async def list_subscriptions(self, subscriber_id: Optional[str] = None) -> List[EventSubscription]:
        """List all subscriptions."""
        subscriptions = list(self._subscriptions.values())
        
        if subscriber_id:
            subscriptions = [s for s in subscriptions if s.subscriber_id == subscriber_id]
        
        return subscriptions
    
    async def _subscribe_to_pattern(self, pattern: str):
        """Subscribe to Redis channels for a pattern.

        For wildcard patterns like 'external.webhook.*', we use Redis psubscribe
        with the wildcard in the channel name, e.g.:
        'tentackl:eventbus:events:type:external.webhook.*'

        This matches channels like:
        'tentackl:eventbus:events:type:external.webhook.order.created'
        """
        channels = []
        use_pattern_subscribe = False

        if pattern == "*":
            channels.append(f"{self.key_prefix}:events:all")
        elif pattern.startswith("workflow:"):
            workflow_id = pattern.split(":", 1)[1]
            channels.append(f"{self.key_prefix}:events:workflow:{workflow_id}")
            use_pattern_subscribe = "*" in workflow_id or "?" in workflow_id
        elif pattern.startswith("agent:"):
            agent_id = pattern.split(":", 1)[1]
            channels.append(f"{self.key_prefix}:events:agent:{agent_id}")
            use_pattern_subscribe = "*" in agent_id or "?" in agent_id
        else:
            # Event type pattern - check if it contains wildcards
            use_pattern_subscribe = "*" in pattern or "?" in pattern
            channels.append(f"{self.key_prefix}:events:type:{pattern}")

        for channel in channels:
            # Use psubscribe for wildcard patterns - Redis will match the channel pattern
            if use_pattern_subscribe:
                await self._pubsub.psubscribe(channel)
                self._pattern_modes[pattern] = "p"
                logger.debug(f"Pattern-subscribed to channel: {channel}")
            else:
                await self._pubsub.subscribe(channel)
                self._pattern_modes[pattern] = "s"
                logger.debug(f"Subscribed to channel: {channel}")
    
    async def _unsubscribe_from_pattern(self, pattern: str):
        """Unsubscribe from Redis channels for a pattern."""
        channels = []
        
        if pattern == "*":
            channels.append(f"{self.key_prefix}:events:all")
        elif pattern.startswith("workflow:"):
            workflow_id = pattern.split(":", 1)[1]
            channels.append(f"{self.key_prefix}:events:workflow:{workflow_id}")
        elif pattern.startswith("agent:"):
            agent_id = pattern.split(":", 1)[1]
            channels.append(f"{self.key_prefix}:events:agent:{agent_id}")
        else:
            channels.append(f"{self.key_prefix}:events:type:{pattern}")
        
        for channel in channels:
            mode = self._pattern_modes.get(pattern)
            if mode == "p":
                await self._pubsub.punsubscribe(channel)
            else:
                await self._pubsub.unsubscribe(channel)
        if pattern in self._pattern_modes:
            del self._pattern_modes[pattern]
    
    async def _listen_for_events(self):
        """Listen for events and route to subscribers."""
        logger.info("Starting event listener")

        while self._running:
            try:
                # Only poll Redis when we have real Redis-backed listeners registered
                # (callback-only subscriptions do not require pubsub polling)
                if self._pubsub and self._listeners and self._pubsub_lock:
                    try:
                        # Use lock to ensure only one coroutine reads from pub/sub at a time
                        async with self._pubsub_lock:
                            message = await asyncio.wait_for(
                                self._pubsub.get_message(ignore_subscribe_messages=True),
                                timeout=1.0
                            )

                        if message and message['type'] in ('message', 'pmessage'):
                            await self._handle_event_message(message)
                    except asyncio.TimeoutError:
                        continue
                else:
                    # No Redis-backed subscriptions yet, just wait
                    await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Error in event listener: {e}")
                await asyncio.sleep(1.0)
    
    async def _handle_event_message(self, message: dict):
        """Handle an incoming event message."""
        try:
            # Parse event data
            event_data = json.loads(message['data'])
            
            # Reconstruct event
            event = Event(
                id=event_data['id'],
                source=event_data['source'],
                event_type=event_data['event_type'],
                timestamp=datetime.fromisoformat(event_data['timestamp']),
                data=event_data['data'],
                metadata=event_data['metadata'],
                workflow_id=event_data.get('workflow_id'),
                agent_id=event_data.get('agent_id')
            )
            
            # Find matching subscriptions
            for pattern, subscription_ids in self._listeners.items():
                if self._matches_pattern(event, pattern):
                    for sub_id in subscription_ids:
                        subscription = self._subscriptions.get(sub_id)
                        if subscription and subscription.active:
                            await self._deliver_event(event, subscription)
                            
        except Exception as e:
            logger.error(f"Error handling event message: {e}")
    
    def _matches_pattern(self, event: Event, pattern: str) -> bool:
        """Check if event matches a subscription pattern."""
        if pattern == "*":
            return True
        elif pattern.startswith("workflow:"):
            workflow_id = pattern.split(":", 1)[1]
            return event.workflow_id == workflow_id
        elif pattern.startswith("agent:"):
            agent_id = pattern.split(":", 1)[1]
            return event.agent_id == agent_id
        else:
            # Event type pattern (supports wildcards)
            return fnmatch.fnmatch(event.event_type, pattern)
    
    async def _deliver_event(self, event: Event, subscription: EventSubscription):
        """Deliver event to a subscriber."""
        try:
            # Apply filters if any
            if subscription.filter and not self._apply_filter(event, subscription.filter):
                return
            
            # Apply transformations if any
            if subscription.transform:
                event = self._transform_event(event, subscription.transform)
            
            # If a direct callback is registered, invoke it
            callbacks = self._callback_handlers.get(subscription.id)
            if callbacks:
                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(event)
                        else:
                            cb(event)
                    except Exception as e:
                        logger.error(f"Error in subscription callback: {e}")
            else:
                # Fallback to enqueue + notify for subscriber workers
                subscriber_queue = f"{self.key_prefix}:queue:{subscription.subscriber_id}"
                await self._redis_client.lpush(
                    subscriber_queue,
                    json.dumps({
                        "event_id": event.id,
                        "subscription_id": subscription.id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )
                await self._redis_client.publish(
                    f"{self.key_prefix}:notify:{subscription.subscriber_id}",
                    event.id
                )
            
            logger.debug(f"Delivered event {event.id} to {subscription.subscriber_id}")
            
        except Exception as e:
            logger.error(f"Error delivering event to subscriber: {e}")
    
    async def replay_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        limit: int = 1000
    ) -> List[Event]:
        """
        Replay historical events from the event stream.
        
        Args:
            start_time: Start of time range (default: 24 hours ago)
            end_time: End of time range (default: now)
            event_types: Filter by event types
            workflow_id: Filter by workflow ID
            limit: Maximum number of events to return
            
        Returns:
            List[Event]: Historical events matching criteria
        """
        await self._ensure_connection()
        
        # Default time range
        if not start_time:
            start_time = datetime.utcnow() - timedelta(hours=24)
        if not end_time:
            end_time = datetime.utcnow()
        
        # Convert to timestamps for Redis
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        # Read from event stream
        stream_key = f"{self.key_prefix}:stream:events"
        # Use full range and filter in-process to avoid ID formatting pitfalls
        entries = await self._redis_client.xrange(
            stream_key,
            min='-',
            max='+',
            count=limit * 4  # Read extra to account for filtering by time and type
        )
        
        events = []
        for entry_id, data in entries:
            try:
                event_data = json.loads(data.get('event', '{}'))
                
                # Filter by event type
                if event_types and event_data.get('event_type') not in event_types:
                    continue
                    
                # Filter by workflow ID
                if workflow_id and event_data.get('workflow_id') != workflow_id:
                    continue
                
                # Reconstruct event
                event = Event(
                    id=event_data['id'],
                    source=event_data['source'],
                    event_type=event_data['event_type'],
                    timestamp=datetime.fromisoformat(event_data['timestamp']),
                    data=event_data['data'],
                    metadata=event_data['metadata'],
                    workflow_id=event_data.get('workflow_id'),
                    agent_id=event_data.get('agent_id')
                )
                
                # Filter by time window
                if event.timestamp < start_time or event.timestamp > end_time:
                    continue

                events.append(event)
                
                if len(events) >= limit:
                    break
                    
            except Exception as e:
                logger.error(f"Error parsing historical event: {e}")
                continue
        
        return events
    
    async def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """
        Retrieve a specific event by ID.
        
        Args:
            event_id: Event identifier
            
        Returns:
            Optional[Event]: The event if found
        """
        await self._ensure_connection()
        
        # Try to get from cache
        event_key = f"{self.key_prefix}:event:{event_id}"
        event_data = await self._redis_client.get(event_key)
        
        if event_data:
            try:
                data = json.loads(event_data)
                return Event(
                    id=data['id'],
                    source=data['source'],
                    event_type=data['event_type'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    data=data['data'],
                    metadata=data['metadata'],
                    workflow_id=data.get('workflow_id'),
                    agent_id=data.get('agent_id')
                )
            except Exception as e:
                logger.error(f"Error parsing event data: {e}")
        
        return None
    
    def _apply_filter(self, event: Event, filter_config: Dict[str, Any]) -> bool:
        """Apply filter to determine if event should be delivered."""
        return self._event_filter.matches(event, filter_config)
    
    def _transform_event(self, event: Event, transform_config: Dict[str, Any]) -> Event:
        """Transform event data before delivery."""
        return self._event_transformer.transform(event, transform_config)
