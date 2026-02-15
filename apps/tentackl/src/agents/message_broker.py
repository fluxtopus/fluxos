# REVIEW:
# - In-memory broker only; no persistence or backpressure strategy beyond queue size.
# - No cleanup of subscribers on agent removal.
from typing import Dict, List, Optional, Callable
from collections import defaultdict
import asyncio
from src.agents.base import AgentMessage
import structlog

logger = structlog.get_logger()


class MessageBroker:
    """Handles inter-agent communication (SRP - only message passing)"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._routing_table: Dict[str, str] = {}  # agent_id -> topic
        self._running = False
        self._task = None
    
    async def start(self) -> None:
        """Start message broker"""
        self._running = True
        self._task = asyncio.create_task(self._process_messages())
        logger.info("Message broker started")
    
    async def stop(self) -> None:
        """Stop message broker"""
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        logger.info("Message broker stopped")
    
    async def publish(self, message: AgentMessage) -> None:
        """Publish a message"""
        await self._message_queue.put(message)
        logger.debug(
            "Message published",
            sender=message.sender_id,
            recipient=message.recipient_id,
            type=message.message_type
        )
    
    def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to a topic"""
        self._subscribers[topic].append(callback)
        logger.debug(f"Subscribed to topic: {topic}")
    
    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """Unsubscribe from a topic"""
        if callback in self._subscribers[topic]:
            self._subscribers[topic].remove(callback)
            logger.debug(f"Unsubscribed from topic: {topic}")
    
    def register_agent(self, agent_id: str, topic: str) -> None:
        """Register agent to topic mapping"""
        self._routing_table[agent_id] = topic
        logger.debug(f"Agent {agent_id} registered to topic {topic}")
    
    async def _process_messages(self) -> None:
        """Process message queue"""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                
                # Route to specific recipient
                if message.recipient_id:
                    topic = self._routing_table.get(message.recipient_id)
                    if topic:
                        await self._deliver_to_topic(topic, message)
                    else:
                        logger.warning(
                            f"No topic found for recipient {message.recipient_id}"
                        )
                else:
                    # Broadcast message
                    await self._broadcast(message)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error processing message", error=str(e))
    
    async def _deliver_to_topic(self, topic: str, message: AgentMessage) -> None:
        """Deliver message to topic subscribers"""
        callbacks = self._subscribers.get(topic, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(
                    f"Error in message callback",
                    topic=topic,
                    error=str(e)
                )
    
    async def _broadcast(self, message: AgentMessage) -> None:
        """Broadcast message to all subscribers"""
        for topic, callbacks in self._subscribers.items():
            await self._deliver_to_topic(topic, message)
