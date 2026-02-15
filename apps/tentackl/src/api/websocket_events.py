"""WebSocket event streaming for real-time event delivery."""

import asyncio
import json
import logging
from typing import Dict, Set, Optional
from datetime import datetime
from fastapi import WebSocket
import redis.asyncio as redis_async

from src.interfaces.event_bus import Event, EventSubscription

logger = logging.getLogger(__name__)


class WebSocketEventManager:
    """Manages WebSocket connections for event streaming."""
    
    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis_url = redis_url
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.subscriptions: Dict[str, str] = {}  # subscriber_id -> subscription_id
        self.running = False
        self._tasks = []
    
    async def start(self):
        """Start the event manager."""
        self.running = True
        logger.info("WebSocket event manager started")
    
    async def stop(self):
        """Stop the event manager."""
        self.running = False
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("WebSocket event manager stopped")
    
    async def connect(self, websocket: WebSocket, subscriber_id: str):
        """Register a new WebSocket connection."""
        await websocket.accept()
        
        if subscriber_id not in self.connections:
            self.connections[subscriber_id] = set()
        
        self.connections[subscriber_id].add(websocket)
        logger.info(f"WebSocket connected for subscriber {subscriber_id}")
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "subscriber_id": subscriber_id
        })
    
    async def disconnect(self, websocket: WebSocket, subscriber_id: str):
        """Remove a WebSocket connection."""
        if subscriber_id in self.connections:
            self.connections[subscriber_id].discard(websocket)
            if not self.connections[subscriber_id]:
                del self.connections[subscriber_id]
                # Also clean up subscription if no more connections
                if subscriber_id in self.subscriptions:
                    del self.subscriptions[subscriber_id]
        
        logger.info(f"WebSocket disconnected for subscriber {subscriber_id}")
    
    async def subscribe_to_events(
        self,
        subscriber_id: str,
        event_pattern: str = "*",
        filter_config: Optional[Dict] = None
    ):
        """Create event subscription for a subscriber."""
        # Store subscription info
        self.subscriptions[subscriber_id] = {
            "pattern": event_pattern,
            "filter": filter_config
        }
        
        # Start event listener task
        task = asyncio.create_task(
            self._listen_for_events(subscriber_id, event_pattern, filter_config)
        )
        self._tasks.append(task)
        
        logger.info(f"Created event subscription for {subscriber_id}: pattern={event_pattern}")
    
    async def _listen_for_events(
        self,
        subscriber_id: str,
        event_pattern: str,
        filter_config: Optional[Dict] = None
    ):
        """Listen for events and forward to WebSocket clients."""
        redis_client = None
        pubsub = None
        
        try:
            # Connect to Redis
            redis_client = await redis_async.from_url(self.redis_url, decode_responses=True)
            pubsub = redis_client.pubsub()
            
            # Subscribe to event pattern
            channel_pattern = f"events:{event_pattern}"
            await pubsub.psubscribe(channel_pattern)
            
            logger.info(f"Listening for events on pattern: {channel_pattern}")
            
            # Listen for events
            async for message in pubsub.listen():
                if not self.running:
                    break
                
                if message['type'] in ['pmessage', 'message']:
                    try:
                        # Parse event data
                        event_data = json.loads(message['data'])
                        
                        # Apply filter if configured
                        if filter_config and not self._matches_filter(event_data, filter_config):
                            continue
                        
                        # Forward to connected WebSockets
                        await self._forward_event(subscriber_id, event_data)
                        
                    except Exception as e:
                        logger.error(f"Error processing event: {e}")
                        
        except asyncio.CancelledError:
            logger.info(f"Event listener cancelled for {subscriber_id}")
        except Exception as e:
            logger.error(f"Event listener error for {subscriber_id}: {e}")
        finally:
            if pubsub:
                await pubsub.unsubscribe()
                await pubsub.close()
            if redis_client:
                await redis_client.close()
    
    def _matches_filter(self, event_data: Dict, filter_config: Dict) -> bool:
        """Check if event matches filter criteria."""
        # Simple filter implementation - can be enhanced
        for field, expected_value in filter_config.items():
            if field not in event_data:
                return False
            if event_data[field] != expected_value:
                return False
        return True
    
    async def _forward_event(self, subscriber_id: str, event_data: Dict):
        """Forward event to all connected WebSockets for a subscriber."""
        if subscriber_id not in self.connections:
            return
        
        # Prepare event message
        message = {
            "type": "event",
            "timestamp": datetime.utcnow().isoformat(),
            "data": event_data
        }
        
        # Send to all connections
        disconnected = set()
        for websocket in self.connections[subscriber_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected websockets
        for ws in disconnected:
            await self.disconnect(ws, subscriber_id)
    
    async def broadcast_to_subscriber(self, subscriber_id: str, message: Dict):
        """Broadcast a message to all connections of a subscriber."""
        if subscriber_id in self.connections:
            await self._forward_event(subscriber_id, message)