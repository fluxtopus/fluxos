"""
EventTriggerWorker: Subscribes to external webhook events and triggers actions.

This worker follows the established pattern (WeatherOrchestrator) but is generic:
1. Subscribes to external.webhook.* events on the event bus
2. Looks up the source configuration to find the registered callback
3. Executes the callback via CallbackEngine (task/agent actions)

The callback configuration determines what happens when an event arrives:
- execute_task: Executes a task template with event data
- spawn_agent: Creates a new agent
- call_api: Makes an HTTP call
- etc.
"""

import asyncio
import json
import os
from typing import Optional, Set
import redis.asyncio as redis
import structlog

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from src.event_bus.redis_event_bus import RedisEventBus
from src.event_bus.callback_engine import CallbackEngine
from src.interfaces.event_bus import Event, EventSubscription, Callback, CallbackTrigger, CallbackAction, CallbackConstraints
from src.core.config import settings

if TYPE_CHECKING:
    from src.application.triggers import TriggerUseCases
    from src.infrastructure.triggers.trigger_event_publisher import TriggerEventPublisher

logger = structlog.get_logger(__name__)

# Lua script for safe lock release (only release if we own it)
RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class EventTriggerWorker:
    """
    Worker that subscribes to external webhook events and triggers actions.

    Follows the pattern established by WeatherOrchestrator:
    - Subscribe to event patterns
    - Listen on Redis notify channel
    - Handle events via CallbackEngine

    Also integrates with TriggerUseCases to execute Tasks based on event triggers.
    """

    def __init__(
        self,
        event_bus: RedisEventBus,
        trigger_use_cases: Optional["TriggerUseCases"] = None,
        event_publisher: Optional["TriggerEventPublisher"] = None,
    ):
        self.event_bus = event_bus
        self._trigger_use_cases = trigger_use_cases
        self._event_publisher = event_publisher
        self._redis_client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tasks: Set[asyncio.Task] = set()
        # Use unique subscriber ID per process to prevent confusion in logs
        # Note: All workers still receive events, deduplication happens via Redis lock
        self._subscriber_id = f"event-trigger-worker-{os.getpid()}"
        self._callback_engine: Optional[CallbackEngine] = None
        # Lock TTL in seconds (5 minutes)
        self._lock_ttl = 300

    async def start(self):
        """Start the event trigger worker."""
        if self._running:
            return

        logger.info("Starting EventTriggerWorker")

        # Ensure event bus is started
        await self.event_bus.start()

        # Subscribe to external webhook events
        sub = EventSubscription(
            subscriber_id=self._subscriber_id,
            event_pattern="external.webhook.*"
        )
        await self.event_bus.subscribe(sub)
        logger.info("EventTriggerWorker subscribed to external.webhook.*")

        # Subscribe to integration events (from Mimic gateway)
        integration_sub = EventSubscription(
            subscriber_id=self._subscriber_id,
            event_pattern="external.integration.*"
        )
        await self.event_bus.subscribe(integration_sub)
        logger.info("EventTriggerWorker subscribed to external.integration.*")

        # Prepare Redis pubsub for notifications
        self._redis_client = await redis.from_url(
            self.event_bus.redis_url,
            decode_responses=True
        )
        self._pubsub = self._redis_client.pubsub()

        # Listen on the subscriber's notify channel
        channel = f"{self.event_bus.key_prefix}:notify:{self._subscriber_id}"
        await self._pubsub.subscribe(channel)
        logger.info(f"EventTriggerWorker listening on channel: {channel}")

        # Initialize CallbackEngine
        self._callback_engine = CallbackEngine()
        await self._callback_engine.initialize()

        self._running = True
        self._task = asyncio.create_task(self._listen_loop())

        logger.info("EventTriggerWorker started")

    async def stop(self):
        """Stop the event trigger worker."""
        logger.info("Stopping EventTriggerWorker")
        self._running = False

        # Cancel the main task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Cancel any pending handler tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Cleanup
        if self._pubsub:
            await self._pubsub.close()
        if self._redis_client:
            await self._redis_client.close()
        if self._callback_engine:
            await self._callback_engine.cleanup()

        logger.info("EventTriggerWorker stopped")

    async def _listen_loop(self):
        """Main loop listening for event notifications."""
        try:
            async for message in self._pubsub.listen():
                if message.get("type") != "message":
                    continue

                event_id = message.get("data")
                try:
                    event = await self.event_bus.get_event_by_id(event_id)
                    if event:
                        # Process in background task to not block the loop
                        task = asyncio.create_task(self._handle_event(event))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                except Exception as e:
                    logger.error(
                        f"EventTriggerWorker failed to handle event: {e}",
                        exc_info=True
                    )

        except asyncio.CancelledError:
            return

    async def _handle_event(self, event: Event):
        """
        Handle an incoming webhook event with distributed lock to prevent duplicates.

        Multiple Gunicorn workers may receive the same event notification.
        We use a Redis lock to ensure only one worker processes each event.

        1. Acquire distributed lock for this event
        2. Extract source_id from event metadata
        3. Look up source configuration and registered callback
        4. Execute callback via CallbackEngine
        5. Release lock
        """
        # Acquire distributed lock to prevent duplicate processing
        lock_key = f"tentackl:lock:event:{event.id}"
        lock_acquired = await self._redis_client.set(
            lock_key,
            self._subscriber_id,
            nx=True,  # Only set if doesn't exist
            ex=self._lock_ttl  # Auto-expire after TTL
        )

        if not lock_acquired:
            logger.debug(
                "Skipping duplicate event (already being processed)",
                event_id=event.id,
                worker=self._subscriber_id
            )
            return

        try:
            await self._process_event_with_lock(event, lock_key)
        except Exception as e:
            logger.error(
                "Error processing event",
                event_id=event.id,
                error=str(e),
                exc_info=True
            )
        finally:
            # Release lock only if we own it (using Lua script for atomicity)
            await self._redis_client.eval(
                RELEASE_LOCK_SCRIPT,
                1,
                lock_key,
                self._subscriber_id
            )

    async def _process_event_with_lock(self, event: Event, lock_key: str):
        """Process event after lock has been acquired."""
        source_id = event.metadata.get("source_id")

        # Process source-based callbacks (existing behavior)
        if source_id:
            await self._process_source_callback(event, source_id)

        # Also check TaskTriggerRegistry for matching tasks
        await self._process_task_triggers(event)

    async def _process_source_callback(self, event: Event, source_id: str):
        """Process source-based callbacks (original behavior)."""
        try:
            logger.info(
                "Processing webhook event",
                event_id=event.id,
                event_type=event.event_type,
                source_id=source_id,
                worker=self._subscriber_id
            )

            # Look up source configuration from Redis
            source_config = await self._get_source_config(source_id)
            if not source_config:
                logger.warning(
                    "Source config not found",
                    source_id=source_id
                )
                return

            # Check if source is active
            if not source_config.get("active", True):
                logger.warning(
                    "Source is inactive",
                    source_id=source_id
                )
                return

            # Get the callback configuration from the source
            callback = await self._get_callback_for_source(source_config, event)
            if not callback:
                logger.warning(
                    "No callback configured for source",
                    source_id=source_id
                )
                return

            # Execute the callback
            result = await self._callback_engine.execute_callback(callback, event)

            if result.success:
                logger.info(
                    "Webhook event processed successfully",
                    event_id=event.id,
                    source_id=source_id,
                    results=result.results
                )
            else:
                logger.warning(
                    "Callback execution failed",
                    event_id=event.id,
                    source_id=source_id,
                    errors=result.errors
                )

        except Exception as e:
            logger.error(
                "Error in source callback processing",
                event_id=event.id,
                source_id=source_id,
                error=str(e),
                exc_info=True
            )

    async def _process_task_triggers(self, event: Event):
        """Check trigger registry for tasks that should be triggered by this event."""
        if not self._trigger_use_cases:
            return

        try:
            # Find tasks with matching triggers for this event
            matching_task_ids = await self._trigger_use_cases.find_matching_tasks(event)

            if not matching_task_ids:
                return

            logger.info(
                "Found task triggers for event",
                event_id=event.id,
                event_type=event.event_type,
                matching_tasks=len(matching_task_ids),
            )

            # Execute each matching task
            for task_id in matching_task_ids:
                execution_id = str(uuid.uuid4())
                try:
                    trigger_config = await self._trigger_use_cases.get_trigger_config(
                        task_id=task_id,
                    )

                    # Publish matched event
                    if self._event_publisher:
                        await self._event_publisher.publish_matched(
                            task_id=task_id,
                            event_id=event.id,
                            event_type=event.event_type,
                            event_data={"preview": str(event.data)[:200] if event.data else None},
                        )

                    # Evaluate JSONLogic condition if present
                    condition = trigger_config.get("condition") if trigger_config else None
                    if condition:
                        if not self._evaluate_jsonlogic_condition(condition, event):
                            logger.debug(
                                "Task trigger condition not met",
                                task_id=task_id,
                                event_id=event.id,
                            )
                            continue

                    # Record execution start in history
                    started_at = datetime.utcnow().isoformat() + "Z"
                    await self._trigger_use_cases.add_execution_to_history(
                        task_id=task_id,
                        execution={
                            "id": execution_id,
                            "event_id": event.id,
                            "task_execution_id": None,
                            "status": "running",
                            "started_at": started_at,
                        },
                    )

                    # Publish executed event
                    if self._event_publisher:
                        await self._event_publisher.publish_executed(
                            task_id=task_id,
                            event_id=event.id,
                            execution_id=execution_id,
                        )

                    # Execute the task via execute_task action
                    callback = Callback(
                        id=f"task-trigger-{task_id[:8]}",
                        trigger=CallbackTrigger(event_type=event.event_type),
                        actions=[
                            CallbackAction(
                                action_type="execute_task",
                                config={"task_id": task_id}
                            )
                        ],
                        constraints=CallbackConstraints()
                    )

                    result = await self._callback_engine.execute_callback(callback, event)

                    if result.success:
                        logger.info(
                            "Task triggered successfully",
                            task_id=task_id,
                            event_id=event.id,
                        )

                        # Update history with completion
                        completed_at = datetime.utcnow().isoformat() + "Z"
                        await self._trigger_use_cases.update_execution_in_history(
                            task_id=task_id,
                            execution_id=execution_id,
                            updates={
                                "status": "completed",
                                "completed_at": completed_at,
                            },
                        )

                        # Publish completed event
                        if self._event_publisher:
                            await self._event_publisher.publish_completed(
                                task_id=task_id,
                                event_id=event.id,
                                execution_id=execution_id,
                                result={"preview": str(result.results)[:200] if result.results else None},
                            )
                    else:
                        logger.warning(
                            "Task trigger execution failed",
                            task_id=task_id,
                            event_id=event.id,
                            errors=result.errors,
                        )

                        # Update history with failure
                        completed_at = datetime.utcnow().isoformat() + "Z"
                        error_msg = str(result.errors[0]) if result.errors else "Unknown error"
                        await self._trigger_use_cases.update_execution_in_history(
                            task_id=task_id,
                            execution_id=execution_id,
                            updates={
                                "status": "failed",
                                "completed_at": completed_at,
                                "error": error_msg,
                            },
                        )

                        # Publish failed event
                        if self._event_publisher:
                            await self._event_publisher.publish_failed(
                                task_id=task_id,
                                event_id=event.id,
                                execution_id=execution_id,
                                error=error_msg,
                            )

                except Exception as e:
                    logger.error(
                        "Error executing task trigger",
                        task_id=task_id,
                        event_id=event.id,
                        error=str(e),
                        exc_info=True,
                    )

                    # Update history with failure
                    completed_at = datetime.utcnow().isoformat() + "Z"
                    await self._trigger_use_cases.update_execution_in_history(
                        task_id=task_id,
                        execution_id=execution_id,
                        updates={
                            "status": "failed",
                            "completed_at": completed_at,
                            "error": str(e),
                        },
                    )

                    # Publish failed event
                    if self._event_publisher:
                        await self._event_publisher.publish_failed(
                            task_id=task_id,
                            event_id=event.id,
                            execution_id=execution_id,
                            error=str(e),
                        )

        except Exception as e:
            logger.error(
                "Error processing task triggers",
                event_id=event.id,
                error=str(e),
                exc_info=True,
            )

    def _evaluate_jsonlogic_condition(self, condition: dict, event: Event) -> bool:
        """
        Evaluate a JSONLogic condition against event data.

        Args:
            condition: JSONLogic condition dict
            event: The event to evaluate against

        Returns:
            True if condition is met, False otherwise
        """
        try:
            from json_logic import jsonLogic

            # Build data context from event
            data = {
                "event": {
                    "id": event.id,
                    "type": event.event_type,
                    "source": event.source,
                },
                "data": event.data or {},
                "metadata": event.metadata or {},
            }

            result = jsonLogic(condition, data)
            return bool(result)

        except ImportError:
            logger.warning("json_logic not installed, skipping condition evaluation")
            return True
        except Exception as e:
            logger.warning(
                "Error evaluating JSONLogic condition",
                error=str(e),
            )
            return False

    async def _get_source_config(self, source_id: str) -> Optional[dict]:
        """
        Retrieve source configuration from Redis.

        Source config is stored at: tentackl:gateway:source:{source_id}
        """
        try:
            source_key = f"tentackl:gateway:source:{source_id}"
            source_data = await self._redis_client.hgetall(source_key)

            if not source_data:
                return None

            # Parse JSON fields
            config = json.loads(source_data.get("config", "{}"))

            return {
                "id": source_data.get("id"),
                "name": source_data.get("name"),
                "source_type": source_data.get("source_type"),
                "config": config,
                "active": source_data.get("active", "True") == "True"
            }

        except Exception as e:
            logger.error(f"Failed to get source config: {e}")
            return None

    async def _get_callback_for_source(self, source_config: dict, event: Event) -> Optional[Callback]:
        """
        Build a callback based on the source configuration.

        The callback action is determined by what's in the source config:
        - callback → use the explicit callback config
        """
        config = source_config.get("config", {})

        # Check for explicit callback configuration
        if "callback" in config:
            callback_config = config["callback"]
            return Callback(
                id=f"webhook-{source_config.get('id', 'unknown')}",
                trigger=CallbackTrigger(
                    event_type=event.event_type,
                    condition=callback_config.get("condition")
                ),
                actions=[
                    CallbackAction(
                        action_type=action.get("type"),
                        config=action.get("config", {})
                    )
                    for action in callback_config.get("actions", [])
                ],
                constraints=CallbackConstraints()
            )

        return None
