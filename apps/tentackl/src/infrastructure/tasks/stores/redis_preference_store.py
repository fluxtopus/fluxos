# REVIEW: Preference storage is Redis-only with no TTL/eviction strategy and
# REVIEW: similarity scans iterate over all prefs per key. As usage grows this
# REVIEW: can become slow. Consider indexing or offloading to a DB with query
# REVIEW: capabilities and explicit lifecycle policies.
"""
Redis-based implementation of PreferenceStoreInterface.

Provides fast read/write for user preferences used in checkpoint auto-approval.
Preferences are learned from user decisions and matched against future contexts.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import redis.asyncio as redis
import structlog

from src.interfaces.preference_store import (
    PreferenceStoreInterface,
    UserPreference,
    PreferenceMatch,
    PreferenceNotFoundError,
    PreferenceValidationError,
    extract_pattern,
    calculate_match_score,
)


logger = structlog.get_logger()


class RedisPreferenceStore(PreferenceStoreInterface):
    """
    Redis-based preference store for checkpoint auto-approval.

    Key Structure:
    - pref:{pref_id} - Hash with preference JSON
    - pref:user:{user_id}:prefs - Sorted set of pref IDs by last_used
    - pref:user:{user_id}:key:{pref_key} - Set of pref IDs for quick lookup
    - pref:high_confidence - Sorted set of high confidence prefs (>= 0.9)
    """

    AUTO_APPROVAL_THRESHOLD = 0.9  # Minimum confidence for auto-approval

    def __init__(
        self,
        redis_url: str = None,
        db: int = 0,
        key_prefix: str = "tentackl:preference",
        connection_pool_size: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        """
        Initialize Redis preference store.

        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for all Redis keys
            connection_pool_size: Size of connection pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.db = db
        self.key_prefix = key_prefix
        self.connection_pool_size = connection_pool_size
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout

        self._redis_pool = None
        self._is_connected = False

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection from pool."""
        if not self._is_connected:
            await self._connect()
        return redis.Redis(connection_pool=self._redis_pool)

    async def _connect(self) -> None:
        """Establish Redis connection pool."""
        try:
            self._redis_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                db=self.db,
                max_connections=self.connection_pool_size,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=True,
            )

            # Test connection
            client = redis.Redis(connection_pool=self._redis_pool)
            await client.ping()
            await client.aclose()

            self._is_connected = True
            logger.info(
                "Connected to Redis for preference store",
                redis_url=self.redis_url,
                db=self.db,
            )

        except Exception as e:
            logger.error("Failed to connect to Redis preference store", error=str(e))
            raise

    async def _disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._redis_pool:
            await self._redis_pool.disconnect()
            self._is_connected = False
            logger.info("Disconnected from Redis preference store")

    # Key generation helpers

    def _pref_key(self, pref_id: str) -> str:
        """Key for preference document."""
        return f"{self.key_prefix}:pref:{pref_id}"

    def _user_prefs_key(self, user_id: str) -> str:
        """Key for user's preferences index."""
        return f"{self.key_prefix}:user:{user_id}:prefs"

    def _user_pref_key_index(self, user_id: str, pref_key: str) -> str:
        """Key for user's preferences by preference_key."""
        return f"{self.key_prefix}:user:{user_id}:key:{pref_key}"

    def _high_confidence_key(self) -> str:
        """Key for high confidence preferences index."""
        return f"{self.key_prefix}:high_confidence"

    def _serialize_pref(self, pref: UserPreference) -> str:
        """Serialize preference to JSON."""
        return json.dumps(pref.to_dict())

    def _deserialize_pref(self, data: str) -> UserPreference:
        """Deserialize preference from JSON."""
        try:
            return UserPreference.from_dict(json.loads(data))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise PreferenceValidationError(f"Invalid preference data: {e}")

    # Interface implementation

    async def record_decision(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
        decision: str,
    ) -> UserPreference:
        """
        Record a user decision and learn from it.

        If a similar preference exists, reinforce it.
        Otherwise, create a new preference.
        """
        client = await self._get_redis()

        try:
            # Extract generalizable pattern from context
            pattern = extract_pattern(context)

            # Check for existing similar preference
            existing = await self._find_similar_preference(
                client, user_id, preference_key, pattern, decision
            )

            if existing:
                # Reinforce existing preference
                existing.increment_usage()
                await self._save_preference(client, existing)

                logger.info(
                    "Reinforced existing preference",
                    preference_id=existing.id,
                    preference_key=preference_key,
                    usage_count=existing.usage_count,
                    confidence=existing.confidence,
                )

                return existing

            # Create new preference
            pref = UserPreference(
                user_id=user_id,
                preference_key=preference_key,
                pattern=pattern,
                decision=decision,
                confidence=1.0,
                usage_count=1,
                metadata={"original_context": context},
            )

            await self._save_preference(client, pref)

            logger.info(
                "Created new preference",
                preference_id=pref.id,
                preference_key=preference_key,
                decision=decision,
            )

            return pref

        finally:
            await client.aclose()

    async def _find_similar_preference(
        self,
        client: redis.Redis,
        user_id: str,
        preference_key: str,
        pattern: Dict[str, Any],
        decision: str,
    ) -> Optional[UserPreference]:
        """Find an existing preference with similar pattern."""
        key_index = self._user_pref_key_index(user_id, preference_key)
        pref_ids = await client.smembers(key_index)

        best_match = None
        best_score = 0.0

        for pref_id in pref_ids:
            pref_data = await client.get(self._pref_key(pref_id))
            if not pref_data:
                continue

            pref = self._deserialize_pref(pref_data)

            # Must have same decision
            if pref.decision != decision:
                continue

            # Calculate pattern match score
            score = calculate_match_score(pref.pattern, pattern)

            # If patterns match well (>80%), consider it similar
            if score >= 0.8 and score > best_score:
                best_match = pref
                best_score = score

        return best_match

    async def _save_preference(
        self, client: redis.Redis, pref: UserPreference
    ) -> None:
        """Save a preference with all indexes."""
        pref_key = self._pref_key(pref.id)
        user_key = self._user_prefs_key(pref.user_id)
        pref_key_index = self._user_pref_key_index(pref.user_id, pref.preference_key)
        high_conf_key = self._high_confidence_key()
        last_used_score = pref.last_used.timestamp()

        serialized = self._serialize_pref(pref)

        async with client.pipeline(transaction=True) as pipe:
            # Store preference
            pipe.set(pref_key, serialized)

            # Index by user (sorted by last_used)
            pipe.zadd(user_key, {pref.id: last_used_score})

            # Index by user + preference_key
            pipe.sadd(pref_key_index, pref.id)

            # Index high confidence preferences
            if pref.confidence >= self.AUTO_APPROVAL_THRESHOLD:
                pipe.zadd(
                    high_conf_key,
                    {f"{pref.user_id}:{pref.id}": pref.confidence},
                )
            else:
                # Remove if confidence dropped below threshold
                pipe.zrem(high_conf_key, f"{pref.user_id}:{pref.id}")

            await pipe.execute()

    async def find_matching_preference(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
        confidence_threshold: float = 0.9,
    ) -> Optional[PreferenceMatch]:
        """
        Find a preference that matches the given context.

        Used to determine if a checkpoint can be auto-approved.
        """
        client = await self._get_redis()

        try:
            key_index = self._user_pref_key_index(user_id, preference_key)
            pref_ids = await client.smembers(key_index)

            if not pref_ids:
                return PreferenceMatch(
                    matched=False,
                    reason="No preferences found for this checkpoint type",
                )

            best_match = None
            best_pattern_score = 0.0
            best_pref = None

            for pref_id in pref_ids:
                pref_data = await client.get(self._pref_key(pref_id))
                if not pref_data:
                    continue

                pref = self._deserialize_pref(pref_data)

                # Skip low confidence preferences
                if pref.confidence < confidence_threshold:
                    continue

                # Calculate how well the pattern matches
                pattern_score = calculate_match_score(pref.pattern, context)

                # All pattern fields must match (score = 1.0)
                if pattern_score == 1.0:
                    if pref.confidence > (best_match.confidence if best_match else 0):
                        best_match = pref
                        best_pattern_score = pattern_score
                        best_pref = pref

            if best_match:
                # Determine if we should auto-approve
                can_auto_approve = (
                    best_match.confidence >= confidence_threshold
                    and best_pattern_score == 1.0
                )

                return PreferenceMatch(
                    matched=True,
                    preference=best_match,
                    confidence=best_match.confidence,
                    pattern_match_score=best_pattern_score,
                    auto_approve=can_auto_approve,
                    reason=f"Matched preference with {best_match.usage_count} similar decisions",
                )

            return PreferenceMatch(
                matched=False,
                reason="No matching preference found with sufficient confidence",
            )

        finally:
            await client.aclose()

    async def get_user_preferences(
        self,
        user_id: str,
        preference_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[UserPreference]:
        """Get all preferences for a user."""
        client = await self._get_redis()

        try:
            if preference_key:
                # Get preferences for specific key
                key_index = self._user_pref_key_index(user_id, preference_key)
                pref_ids = await client.smembers(key_index)
            else:
                # Get all user preferences (sorted by last_used, descending)
                user_key = self._user_prefs_key(user_id)
                pref_ids = await client.zrevrange(user_key, 0, limit - 1)

            preferences = []
            for pref_id in pref_ids:
                pref_data = await client.get(self._pref_key(pref_id))
                if pref_data:
                    preferences.append(self._deserialize_pref(pref_data))

            # Sort by last_used descending
            preferences.sort(key=lambda p: p.last_used, reverse=True)
            return preferences[:limit]

        finally:
            await client.aclose()

    async def get_preference(self, preference_id: str) -> Optional[UserPreference]:
        """Get a specific preference by ID."""
        client = await self._get_redis()

        try:
            pref_data = await client.get(self._pref_key(preference_id))

            if not pref_data:
                return None

            return self._deserialize_pref(pref_data)

        finally:
            await client.aclose()

    async def update_preference(
        self, preference_id: str, updates: Dict[str, Any]
    ) -> bool:
        """Update a preference."""
        client = await self._get_redis()

        try:
            pref_data = await client.get(self._pref_key(preference_id))

            if not pref_data:
                raise PreferenceNotFoundError(f"Preference not found: {preference_id}")

            pref = self._deserialize_pref(pref_data)

            # Apply updates
            for key, value in updates.items():
                if hasattr(pref, key):
                    setattr(pref, key, value)

            await self._save_preference(client, pref)

            logger.debug(
                "Updated preference",
                preference_id=preference_id,
                updates=list(updates.keys()),
            )

            return True

        except PreferenceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to update preference",
                preference_id=preference_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    async def delete_preference(self, preference_id: str) -> bool:
        """Delete a preference."""
        client = await self._get_redis()

        try:
            pref_data = await client.get(self._pref_key(preference_id))

            if not pref_data:
                return False

            pref = self._deserialize_pref(pref_data)

            async with client.pipeline(transaction=True) as pipe:
                # Delete preference
                pipe.delete(self._pref_key(preference_id))

                # Remove from user index
                pipe.zrem(self._user_prefs_key(pref.user_id), preference_id)

                # Remove from preference_key index
                pipe.srem(
                    self._user_pref_key_index(pref.user_id, pref.preference_key),
                    preference_id,
                )

                # Remove from high confidence index
                pipe.zrem(
                    self._high_confidence_key(),
                    f"{pref.user_id}:{preference_id}",
                )

                await pipe.execute()

            logger.info("Deleted preference", preference_id=preference_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to delete preference",
                preference_id=preference_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    async def increment_usage(self, preference_id: str) -> bool:
        """Increment the usage count of a preference."""
        client = await self._get_redis()

        try:
            pref_data = await client.get(self._pref_key(preference_id))

            if not pref_data:
                raise PreferenceNotFoundError(f"Preference not found: {preference_id}")

            pref = self._deserialize_pref(pref_data)
            pref.increment_usage()

            await self._save_preference(client, pref)

            logger.debug(
                "Incremented preference usage",
                preference_id=preference_id,
                usage_count=pref.usage_count,
                confidence=pref.confidence,
            )

            return True

        except PreferenceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to increment preference usage",
                preference_id=preference_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    async def cleanup_unused_preferences(
        self, user_id: str, unused_days: int = 90
    ) -> int:
        """Clean up preferences that haven't been used recently."""
        client = await self._get_redis()

        try:
            cutoff = datetime.utcnow() - timedelta(days=unused_days)
            cutoff_score = cutoff.timestamp()

            user_key = self._user_prefs_key(user_id)

            # Get old preference IDs
            old_ids = await client.zrangebyscore(user_key, "-inf", cutoff_score)

            cleaned = 0
            for pref_id in old_ids:
                if await self.delete_preference(pref_id):
                    cleaned += 1

            logger.info(
                "Cleaned up unused preferences",
                user_id=user_id,
                unused_days=unused_days,
                cleaned_count=cleaned,
            )

            return cleaned

        except Exception as e:
            logger.error(
                "Failed to cleanup unused preferences",
                user_id=user_id,
                error=str(e),
            )
            return 0
        finally:
            await client.aclose()

    async def health_check(self) -> bool:
        """Check if the preference store is healthy."""
        try:
            client = await self._get_redis()
            test_key = f"{self.key_prefix}:health"
            await client.set(test_key, "ok", ex=60)
            result = await client.get(test_key)
            await client.delete(test_key)
            await client.aclose()
            return result == "ok"
        except Exception as e:
            logger.error("Preference store health check failed", error=str(e))
            return False

    # Additional utility methods

    async def get_high_confidence_preferences(
        self, limit: int = 100
    ) -> List[UserPreference]:
        """Get all high confidence preferences for auto-approval."""
        client = await self._get_redis()

        try:
            high_conf_key = self._high_confidence_key()

            # Get entries sorted by confidence (descending)
            entries = await client.zrevrange(high_conf_key, 0, limit - 1)

            preferences = []
            for entry in entries:
                user_id, pref_id = entry.split(":", 1)
                pref_data = await client.get(self._pref_key(pref_id))
                if pref_data:
                    preferences.append(self._deserialize_pref(pref_data))

            return preferences

        finally:
            await client.aclose()

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        """Get preference statistics for a user."""
        client = await self._get_redis()

        try:
            user_key = self._user_prefs_key(user_id)

            # Total preferences
            total = await client.zcard(user_key)

            # Get all preferences to calculate stats
            prefs = await self.get_user_preferences(user_id, limit=1000)

            # Stats by decision type
            approved = sum(1 for p in prefs if p.decision == "approved")
            rejected = sum(1 for p in prefs if p.decision == "rejected")

            # High confidence count
            high_conf = sum(1 for p in prefs if p.confidence >= self.AUTO_APPROVAL_THRESHOLD)

            # Average confidence
            avg_confidence = (
                sum(p.confidence for p in prefs) / len(prefs) if prefs else 0
            )

            # Total usage
            total_usage = sum(p.usage_count for p in prefs)

            return {
                "total": total,
                "approved": approved,
                "rejected": rejected,
                "high_confidence": high_conf,
                "average_confidence": round(avg_confidence, 3),
                "total_usage": total_usage,
            }

        finally:
            await client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._disconnect()
