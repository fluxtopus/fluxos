"""Redis-based token validation cache for high-performance auth.

This module caches token validation results from InkPass to avoid hitting
rate limits (30 requests/min for /auth/me) during high-frequency UI navigation.

Cache Strategy:
- Key: SHA256 hash of token (first 32 chars)
- Value: JSON-serialized user data
- TTL: 10 minutes (configurable via TOKEN_CACHE_TTL env var)
- Storage: Redis DB 5 (Tentackl services)
"""

import hashlib
import json
from typing import Optional
import redis.asyncio as redis
import structlog
import os

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/5")
CACHE_TTL_SECONDS = int(os.getenv("TOKEN_CACHE_TTL", "600"))  # 10 minutes
CACHE_KEY_PREFIX = "tentackl:auth:token:"


class TokenCache:
    """Cache for validated token results.

    Stores InkPass validation responses in Redis to avoid network calls
    on every authenticated request.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    def _token_key(self, token: str) -> str:
        """Hash token to create cache key.

        We never store raw JWTs as keys - use SHA256 hash instead.
        Using first 32 chars of hash (128 bits) for reasonable key size.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        return f"{CACHE_KEY_PREFIX}{token_hash}"

    async def get(self, token: str) -> Optional[dict]:
        """Get cached user data for token.

        Returns:
            User data dict on cache hit, None on miss or error.

        Note:
            Fails open on errors - returns None so caller will
            fall back to InkPass validation.
        """
        try:
            client = await self._get_redis()
            key = self._token_key(token)
            data = await client.get(key)
            if data:
                logger.debug("Token cache hit", key_prefix=key[:25])
                return json.loads(data)
            logger.debug("Token cache miss", key_prefix=key[:25])
            return None
        except Exception as e:
            logger.warning("Token cache get failed", error=str(e))
            return None  # Fail open - will call InkPass

    async def set(self, token: str, user_data: dict) -> None:
        """Cache user data for token with TTL.

        Args:
            token: The JWT token (will be hashed for storage)
            user_data: User data dict from InkPass validation

        Note:
            Non-blocking - cache failures are logged but don't break auth.
        """
        try:
            client = await self._get_redis()
            key = self._token_key(token)
            await client.setex(key, CACHE_TTL_SECONDS, json.dumps(user_data))
            logger.debug("Token cached", key_prefix=key[:25], ttl=CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning("Token cache set failed", error=str(e))
            # Non-blocking - cache failure shouldn't break auth

    async def invalidate(self, token: str) -> None:
        """Remove token from cache.

        Called on logout to ensure token can't be used from cache
        after user explicitly logs out.
        """
        try:
            client = await self._get_redis()
            key = self._token_key(token)
            await client.delete(key)
            logger.debug("Token cache invalidated", key_prefix=key[:25])
        except Exception as e:
            logger.warning("Token cache invalidate failed", error=str(e))

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# Global instance
token_cache = TokenCache()
