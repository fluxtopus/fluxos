# REVIEW: This module mixes cache interface and a concrete Redis implementation,
# REVIEW: and methods assume `self.client` is always initialized. Consider
# REVIEW: separating interface/implementation and adding connection guards.
from abc import ABC, abstractmethod
from typing import Any, Optional, List
import redis.asyncio as redis
import json
from src.core.config import settings
import structlog

logger = structlog.get_logger()


class CacheInterface(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def expire(self, key: str, seconds: int) -> bool:
        pass


class RedisCache(CacheInterface):
    def __init__(self):
        self.client: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Connect to Redis"""
        try:
            self.client = redis.from_url(
                settings.REDIS_URL,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS
            )
            await self.client.ping()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
            logger.info("Redis cache disconnected")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except json.JSONDecodeError:
            # Return raw value if not JSON
            return value
        except Exception as e:
            logger.error(f"Cache get error", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache"""
        try:
            if not isinstance(value, str):
                value = json.dumps(value)
            
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
                
            logger.debug(f"Cache set", key=key, ttl=ttl)
        except Exception as e:
            logger.error(f"Cache set error", key=key, error=str(e))
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            result = await self.client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Cache delete error", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error", key=key, error=str(e))
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key"""
        try:
            return bool(await self.client.expire(key, seconds))
        except Exception as e:
            logger.error(f"Cache expire error", key=key, error=str(e))
            return False
    
    async def lpush(self, key: str, *values: Any) -> int:
        """Push values to list"""
        try:
            json_values = [json.dumps(v) for v in values]
            return await self.client.lpush(key, *json_values)
        except Exception as e:
            logger.error(f"Cache lpush error", key=key, error=str(e))
            return 0
    
    async def lrange(self, key: str, start: int, stop: int) -> List[Any]:
        """Get range from list"""
        try:
            values = await self.client.lrange(key, start, stop)
            return [json.loads(v) for v in values]
        except Exception as e:
            logger.error(f"Cache lrange error", key=key, error=str(e))
            return []
