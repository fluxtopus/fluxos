# REVIEW: Registry keeps an in-memory cache that can drift in multi-process
# REVIEW: deployments with no invalidation strategy. The persistence is Redis,
# REVIEW: but matching still relies on local cache or redis sets, which may
# REVIEW: become stale after restarts or updates from other workers. Consider
# REVIEW: a shared index (or pub/sub invalidation) and explicit cache TTLs.
"""
TaskTriggerRegistry: Registry mapping event patterns to Task IDs.

This registry enables event-driven task execution by:
1. Indexing tasks by their trigger event patterns
2. Efficiently finding tasks that match incoming events
3. Persisting trigger configurations in Redis

Redis key format:
- tentackl:triggers:pattern:{pattern} -> Set of task IDs
- tentackl:triggers:task:{task_id} -> JSON trigger config

Pattern matching supports glob-style wildcards:
- "external.integration.*" matches "external.integration.webhook"
- "external.webhook.stripe" matches exactly
"""

import asyncio
import fnmatch
import json
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
import structlog
import redis.asyncio as redis

from src.interfaces.event_bus import Event
from src.core.config import settings

logger = structlog.get_logger(__name__)


class TaskTriggerRegistry:
    """
    Registry that maps event patterns to Task IDs within organizations.

    Uses Redis for persistence + in-memory cache for fast lookups.

    Key format (org-scoped):
    - tentackl:triggers:org:{org_id}:pattern:{pattern} -> Set of task IDs
    - tentackl:triggers:task:{task_id} -> JSON trigger config (includes org_id)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "tentackl:triggers",
    ):
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        self._key_prefix = key_prefix
        self._initialized = False

        # In-memory cache for fast pattern lookups
        # Maps (org_id, pattern) -> set of task_ids
        self._pattern_cache: Dict[tuple, Set[str]] = {}
        # Maps task_id -> trigger config (includes org_id)
        self._config_cache: Dict[str, dict] = {}

    async def initialize(self) -> None:
        """Initialize the registry with Redis connection."""
        if self._initialized:
            return

        self._redis_client = await redis.from_url(
            self._redis_url,
            decode_responses=True
        )
        self._initialized = True
        logger.info("TaskTriggerRegistry initialized")

    async def _ensure_initialized(self) -> None:
        """Ensure the registry is initialized."""
        if not self._initialized:
            await self.initialize()

    async def register_trigger(
        self,
        task_id: str,
        organization_id: str,
        trigger_config: dict,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Register a task to be triggered by events matching the pattern.

        Args:
            task_id: The task ID to register
            organization_id: The organization ID (triggers are org-scoped)
            trigger_config: Trigger configuration with:
                - type: "event" | "schedule" | "manual"
                - event_pattern: Event pattern to match (glob-style)
                - source_filter: Optional source prefix filter
                - condition: Optional JSONLogic condition
                - enabled: Whether trigger is active
            user_id: Optional user ID for user-scoped triggers

        Returns:
            True if registered successfully
        """
        await self._ensure_initialized()

        event_pattern = trigger_config.get("event_pattern")
        if not event_pattern:
            logger.warning(
                "Cannot register trigger without event_pattern",
                task_id=task_id,
            )
            return False

        if not trigger_config.get("enabled", True):
            logger.debug(
                "Skipping disabled trigger",
                task_id=task_id,
                event_pattern=event_pattern,
            )
            return False

        # Include org_id and user_id in the stored config
        config_with_org = {
            **trigger_config,
            "organization_id": organization_id,
            "user_id": user_id,
        }

        try:
            # Store trigger config
            config_key = f"{self._key_prefix}:task:{task_id}"
            await self._redis_client.set(
                config_key,
                json.dumps(config_with_org),
            )

            # Add task to org-scoped pattern set
            pattern_key = f"{self._key_prefix}:org:{organization_id}:pattern:{event_pattern}"
            await self._redis_client.sadd(pattern_key, task_id)

            # Update in-memory cache
            self._config_cache[task_id] = config_with_org
            cache_key = (organization_id, event_pattern)
            if cache_key not in self._pattern_cache:
                self._pattern_cache[cache_key] = set()
            self._pattern_cache[cache_key].add(task_id)

            logger.info(
                "Registered task trigger",
                task_id=task_id,
                organization_id=organization_id,
                event_pattern=event_pattern,
                source_filter=trigger_config.get("source_filter"),
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to register trigger",
                task_id=task_id,
                error=str(e),
            )
            return False

    async def unregister_trigger(self, task_id: str) -> bool:
        """
        Remove a task's trigger registration.

        Args:
            task_id: The task ID to unregister

        Returns:
            True if unregistered successfully
        """
        await self._ensure_initialized()

        try:
            # Get current config to find pattern and org
            config_key = f"{self._key_prefix}:task:{task_id}"
            config_json = await self._redis_client.get(config_key)

            if config_json:
                config = json.loads(config_json)
                event_pattern = config.get("event_pattern")
                organization_id = config.get("organization_id")

                # Remove from org-scoped pattern set
                if event_pattern and organization_id:
                    pattern_key = f"{self._key_prefix}:org:{organization_id}:pattern:{event_pattern}"
                    await self._redis_client.srem(pattern_key, task_id)

                    # Update in-memory cache
                    cache_key = (organization_id, event_pattern)
                    if cache_key in self._pattern_cache:
                        self._pattern_cache[cache_key].discard(task_id)
                        if not self._pattern_cache[cache_key]:
                            del self._pattern_cache[cache_key]

            # Remove config
            await self._redis_client.delete(config_key)

            # Remove from config cache
            self._config_cache.pop(task_id, None)

            logger.info("Unregistered task trigger", task_id=task_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to unregister trigger",
                task_id=task_id,
                error=str(e),
            )
            return False

    async def find_matching_tasks(
        self,
        event: Event,
        organization_id: Optional[str] = None,
    ) -> List[str]:
        """
        Find all task IDs that should be triggered by this event.

        Matches event type against registered patterns using glob matching.
        Also applies source_filter if configured.

        Args:
            event: The incoming event
            organization_id: Organization to scope the search (from event metadata)

        Returns:
            List of task IDs that should be triggered
        """
        await self._ensure_initialized()

        # Get org from parameter or event metadata
        org_id = organization_id or event.metadata.get("organization_id")
        if not org_id:
            logger.debug(
                "No organization_id for event, skipping task trigger lookup",
                event_id=event.id,
            )
            return []

        matching_task_ids: Set[str] = set()
        event_type = event.event_type
        event_source = event.source

        try:
            # Check org-scoped patterns
            pattern_prefix = f"{self._key_prefix}:org:{org_id}:pattern:"
            cursor = 0

            while True:
                cursor, keys = await self._redis_client.scan(
                    cursor=cursor,
                    match=f"{pattern_prefix}*",
                    count=100,
                )

                for key in keys:
                    pattern = key[len(pattern_prefix):]

                    # Check if event type matches pattern
                    if self._matches_pattern(event_type, pattern):
                        # Get all task IDs for this pattern
                        task_ids = await self._redis_client.smembers(key)

                        for task_id in task_ids:
                            # Check source filter if configured
                            config = await self.get_trigger_config(task_id)
                            if config:
                                source_filter = config.get("source_filter")
                                if source_filter:
                                    # Check if event source starts with filter
                                    if not event_source.startswith(source_filter):
                                        continue

                                # Only include enabled triggers
                                if config.get("enabled", True):
                                    matching_task_ids.add(task_id)

                if cursor == 0:
                    break

            logger.debug(
                "Found matching tasks for event",
                event_type=event_type,
                organization_id=org_id,
                matching_count=len(matching_task_ids),
            )
            return list(matching_task_ids)

        except Exception as e:
            logger.error(
                "Error finding matching tasks",
                event_type=event_type,
                organization_id=org_id,
                error=str(e),
            )
            return []

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """
        Check if an event type matches a pattern.

        Supports glob-style wildcards:
        - * matches any single segment
        - ** would match multiple segments (not implemented yet)

        Examples:
        - "external.integration.webhook" matches "external.integration.*"
        - "external.webhook.stripe" matches "external.webhook.stripe"
        """
        # Convert glob pattern to fnmatch pattern
        # Replace dots with temporary marker, then use fnmatch
        return fnmatch.fnmatch(event_type, pattern)

    async def get_trigger_config(self, task_id: str) -> Optional[dict]:
        """
        Get the trigger configuration for a task.

        Args:
            task_id: The task ID

        Returns:
            Trigger configuration dict or None if not found
        """
        await self._ensure_initialized()

        # Check cache first
        if task_id in self._config_cache:
            return self._config_cache[task_id]

        try:
            config_key = f"{self._key_prefix}:task:{task_id}"
            config_json = await self._redis_client.get(config_key)

            if config_json:
                config = json.loads(config_json)
                # Update cache
                self._config_cache[task_id] = config
                return config

            return None

        except Exception as e:
            logger.error(
                "Error getting trigger config",
                task_id=task_id,
                error=str(e),
            )
            return None

    async def load_all_triggers(self) -> int:
        """
        Load all triggers from Redis into memory cache on startup.

        Returns:
            Number of triggers loaded
        """
        await self._ensure_initialized()

        count = 0
        try:
            # Scan for all task config keys
            config_prefix = f"{self._key_prefix}:task:"
            cursor = 0

            while True:
                cursor, keys = await self._redis_client.scan(
                    cursor=cursor,
                    match=f"{config_prefix}*",
                    count=100,
                )

                for key in keys:
                    task_id = key[len(config_prefix):]
                    config_json = await self._redis_client.get(key)

                    if config_json:
                        config = json.loads(config_json)
                        self._config_cache[task_id] = config

                        event_pattern = config.get("event_pattern")
                        organization_id = config.get("organization_id")

                        if event_pattern and organization_id and config.get("enabled", True):
                            cache_key = (organization_id, event_pattern)
                            if cache_key not in self._pattern_cache:
                                self._pattern_cache[cache_key] = set()
                            self._pattern_cache[cache_key].add(task_id)
                            count += 1

                if cursor == 0:
                    break

            logger.info(
                "Loaded task triggers from Redis",
                count=count,
                patterns=len(self._pattern_cache),
            )
            return count

        except Exception as e:
            logger.error("Error loading triggers", error=str(e))
            return 0

    async def get_all_triggers(self) -> List[Dict[str, Any]]:
        """
        Get all registered triggers.

        Returns:
            List of trigger configurations with task_id included
        """
        await self._ensure_initialized()

        triggers = []
        try:
            config_prefix = f"{self._key_prefix}:task:"
            cursor = 0

            while True:
                cursor, keys = await self._redis_client.scan(
                    cursor=cursor,
                    match=f"{config_prefix}*",
                    count=100,
                )

                for key in keys:
                    task_id = key[len(config_prefix):]
                    config_json = await self._redis_client.get(key)

                    if config_json:
                        config = json.loads(config_json)
                        triggers.append({
                            "task_id": task_id,
                            **config,
                        })

                if cursor == 0:
                    break

            return triggers

        except Exception as e:
            logger.error("Error getting all triggers", error=str(e))
            return []

    async def get_triggers_for_org(self, organization_id: str) -> List[Dict[str, Any]]:
        """
        Get all triggers for a specific organization.

        Args:
            organization_id: The organization ID

        Returns:
            List of trigger configurations for the org
        """
        all_triggers = await self.get_all_triggers()
        return [
            t for t in all_triggers
            if t.get("organization_id") == organization_id
        ]

    async def get_triggers_for_user(
        self,
        organization_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get triggers visible to a specific user.

        Returns:
            - All org-level triggers (user_id is null)
            - User's personal triggers (user_id matches)

        Args:
            organization_id: The organization ID
            user_id: The user ID

        Returns:
            List of trigger configurations visible to the user
        """
        all_triggers = await self.get_all_triggers()
        return [
            t for t in all_triggers
            if t.get("organization_id") == organization_id
            and (t.get("user_id") is None or t.get("user_id") == user_id)
        ]

    async def get_trigger_history(
        self,
        task_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get recent execution history for a trigger.

        Args:
            task_id: The task ID
            limit: Maximum number of executions to return

        Returns:
            List of execution history entries
        """
        await self._ensure_initialized()

        try:
            history_key = f"{self._key_prefix}:history:{task_id}"
            # Get recent executions from Redis list (stored newest first)
            raw_entries = await self._redis_client.lrange(history_key, 0, limit - 1)

            executions = []
            for entry in raw_entries:
                try:
                    executions.append(json.loads(entry))
                except json.JSONDecodeError:
                    logger.warning(
                        "Invalid JSON in trigger history",
                        task_id=task_id,
                        entry=entry,
                    )

            return executions

        except Exception as e:
            logger.error(
                "Error getting trigger history",
                task_id=task_id,
                error=str(e),
            )
            return []

    async def add_execution_to_history(
        self,
        task_id: str,
        execution: Dict[str, Any],
        max_history: int = 100,
    ) -> bool:
        """
        Add an execution entry to the trigger's history.

        Args:
            task_id: The task ID
            execution: Execution data with id, event_id, status, started_at, etc.
            max_history: Maximum history entries to keep

        Returns:
            True if added successfully
        """
        await self._ensure_initialized()

        try:
            history_key = f"{self._key_prefix}:history:{task_id}"

            # Push to front of list (newest first)
            await self._redis_client.lpush(history_key, json.dumps(execution))

            # Trim to max history
            await self._redis_client.ltrim(history_key, 0, max_history - 1)

            return True

        except Exception as e:
            logger.error(
                "Error adding execution to history",
                task_id=task_id,
                error=str(e),
            )
            return False

    async def update_execution_in_history(
        self,
        task_id: str,
        execution_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update an execution entry in the trigger's history.

        Args:
            task_id: The task ID
            execution_id: The execution ID to update
            updates: Fields to update (status, completed_at, error, etc.)

        Returns:
            True if updated successfully
        """
        await self._ensure_initialized()

        try:
            history_key = f"{self._key_prefix}:history:{task_id}"

            # Get all entries
            raw_entries = await self._redis_client.lrange(history_key, 0, -1)

            for i, entry in enumerate(raw_entries):
                try:
                    execution = json.loads(entry)
                    if execution.get("id") == execution_id:
                        # Update the entry
                        execution.update(updates)
                        await self._redis_client.lset(
                            history_key, i, json.dumps(execution)
                        )
                        return True
                except json.JSONDecodeError:
                    continue

            return False

        except Exception as e:
            logger.error(
                "Error updating execution in history",
                task_id=task_id,
                execution_id=execution_id,
                error=str(e),
            )
            return False

    async def update_trigger(
        self,
        task_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update a trigger configuration.

        Args:
            task_id: The task ID
            updates: Fields to update

        Returns:
            True if updated successfully
        """
        await self._ensure_initialized()

        try:
            config = await self.get_trigger_config(task_id)
            if not config:
                logger.warning(
                    "Cannot update non-existent trigger",
                    task_id=task_id,
                )
                return False

            old_pattern = config.get("event_pattern")
            organization_id = config.get("organization_id")
            new_config = {**config, **updates}
            new_pattern = new_config.get("event_pattern")

            # If pattern changed, update org-scoped pattern sets
            if old_pattern != new_pattern and organization_id:
                # Remove from old pattern set
                if old_pattern:
                    old_pattern_key = f"{self._key_prefix}:org:{organization_id}:pattern:{old_pattern}"
                    await self._redis_client.srem(old_pattern_key, task_id)
                    old_cache_key = (organization_id, old_pattern)
                    if old_cache_key in self._pattern_cache:
                        self._pattern_cache[old_cache_key].discard(task_id)

                # Add to new pattern set
                if new_pattern:
                    new_pattern_key = f"{self._key_prefix}:org:{organization_id}:pattern:{new_pattern}"
                    await self._redis_client.sadd(new_pattern_key, task_id)
                    new_cache_key = (organization_id, new_pattern)
                    if new_cache_key not in self._pattern_cache:
                        self._pattern_cache[new_cache_key] = set()
                    self._pattern_cache[new_cache_key].add(task_id)

            # Store updated config
            config_key = f"{self._key_prefix}:task:{task_id}"
            await self._redis_client.set(
                config_key,
                json.dumps(new_config),
            )

            # Update cache
            self._config_cache[task_id] = new_config

            logger.info(
                "Updated task trigger",
                task_id=task_id,
                updates=updates,
            )
            return True

        except Exception as e:
            logger.error(
                "Error updating trigger",
                task_id=task_id,
                error=str(e),
            )
            return False

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._redis_client:
            await self._redis_client.aclose()
        self._pattern_cache.clear()
        self._config_cache.clear()
        self._initialized = False
        logger.info("TaskTriggerRegistry cleaned up")
