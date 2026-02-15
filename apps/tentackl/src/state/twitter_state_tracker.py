"""
Twitter State Tracker for daily post count management.

This module provides Redis-based tracking of daily post counts for Twitter/X API,
enforcing the 3 posts per day limit with automatic date-based key rotation.
"""

from datetime import datetime, timedelta
from typing import Optional
import redis.asyncio as redis_async
import structlog
import os

logger = structlog.get_logger()


class TwitterStateTracker:
    """
    Tracks daily post counts for Twitter/X API with Redis.
    
    Uses date-based keys that automatically expire at midnight to enforce
    daily posting limits.
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        db: int = 0,
        key_prefix: str = "twitter:posts:count",
        daily_limit: int = 3
    ):
        """
        Initialize Twitter State Tracker.
        
        Args:
            redis_url: Redis connection URL (defaults to REDIS_URL env var)
            db: Redis database number
            key_prefix: Prefix for Redis keys
            daily_limit: Maximum posts allowed per day (default: 3)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.db = db
        self.key_prefix = key_prefix
        self.daily_limit = daily_limit
        self._redis_client: Optional[redis_async.Redis] = None
    
    async def _get_redis(self) -> redis_async.Redis:
        """Get or create Redis client."""
        if self._redis_client is None:
            self._redis_client = await redis_async.from_url(
                self.redis_url,
                db=self.db,
                decode_responses=True
            )
        return self._redis_client
    
    async def close(self):
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None
    
    def _get_date_key(self, date: Optional[datetime] = None) -> str:
        """
        Generate Redis key for a specific date.
        
        Args:
            date: Date to generate key for (defaults to today)
            
        Returns:
            Redis key string in format: twitter:posts:count:YYYY-MM-DD
        """
        if date is None:
            date = datetime.utcnow()
        date_str = date.strftime("%Y-%m-%d")
        return f"{self.key_prefix}:{date_str}"
    
    def _seconds_until_midnight(self) -> int:
        """Calculate seconds until next midnight UTC."""
        now = datetime.utcnow()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((tomorrow - now).total_seconds())
    
    async def check_daily_limit(self, date: Optional[datetime] = None) -> bool:
        """
        Check if daily post limit has been reached.
        
        Args:
            date: Date to check (defaults to today)
            
        Returns:
            True if limit not reached, False if limit exceeded
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_date_key(date)
            count = await redis_client.get(key)
            current_count = int(count) if count else 0
            return current_count < self.daily_limit
        except Exception as e:
            logger.error("Failed to check daily limit", error=str(e))
            # Fail open - allow posting if we can't check
            return True
    
    async def get_remaining_posts(self, date: Optional[datetime] = None) -> int:
        """
        Get remaining posts available for the day.
        
        Args:
            date: Date to check (defaults to today)
            
        Returns:
            Number of posts remaining (0 if limit reached)
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_date_key(date)
            count = await redis_client.get(key)
            current_count = int(count) if count else 0
            remaining = max(0, self.daily_limit - current_count)
            return remaining
        except Exception as e:
            logger.error("Failed to get remaining posts", error=str(e))
            return 0
    
    async def get_post_count(self, date: Optional[datetime] = None) -> int:
        """
        Get current post count for the day.
        
        Args:
            date: Date to check (defaults to today)
            
        Returns:
            Current post count
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_date_key(date)
            count = await redis_client.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error("Failed to get post count", error=str(e))
            return 0
    
    async def increment_post_count(self, date: Optional[datetime] = None) -> int:
        """
        Increment post count for the day.
        
        Args:
            date: Date to increment (defaults to today)
            
        Returns:
            New post count after increment
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_date_key(date)
            
            # Use pipeline for atomic operation
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, self._seconds_until_midnight())
            results = await pipe.execute()
            
            new_count = results[0]
            logger.info("Incremented post count", key=key, count=new_count)
            return new_count
        except Exception as e:
            logger.error("Failed to increment post count", error=str(e))
            raise
    
    async def reset_count(self, date: Optional[datetime] = None) -> None:
        """
        Reset post count for a specific date (useful for testing).
        
        Args:
            date: Date to reset (defaults to today)
        """
        try:
            redis_client = await self._get_redis()
            key = self._get_date_key(date)
            await redis_client.delete(key)
            logger.info("Reset post count", key=key)
        except Exception as e:
            logger.error("Failed to reset post count", error=str(e))
            raise

