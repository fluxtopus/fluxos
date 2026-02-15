# REVIEW: Redis caching is inconsistent: keys are stored in a single hash
# REVIEW: but TTL is set on a different key (`api_keys:{key_hash}`), so entries
# REVIEW: never expire. Also, cache hits still trigger a DB query, reducing
# REVIEW: the benefit of Redis. Consider fixing TTL and returning cached data
# REVIEW: without a DB round-trip when safe.
"""Repository for API key management with dual-storage (PostgreSQL + Redis)."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import structlog
import redis.asyncio as redis_async
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.auth_models import APIKeyModel
from src.interfaces.database import Database
from src.core.config import settings

logger = structlog.get_logger()

# Redis URL from environment
REDIS_URL = settings.REDIS_URL


class APIKeyRepository:
    """
    Repository for API key operations with dual-storage strategy.
    
    - PostgreSQL: Primary durable storage (source of truth)
    - Redis: Cache layer for fast retrieval
    - Graceful fallback to PostgreSQL if Redis is unavailable
    """
    
    def __init__(self, database: Database, redis_url: Optional[str] = None):
        self.db = database
        self.redis_url = redis_url or REDIS_URL
        self._redis_client: Optional[redis_async.Redis] = None
    
    async def _get_redis(self) -> Optional[redis_async.Redis]:
        """Get Redis client, returning None if connection fails."""
        try:
            if self._redis_client is None:
                self._redis_client = await redis_async.from_url(
                    self.redis_url,
                    decode_responses=True
                )
            # Test connection
            await self._redis_client.ping()
            return self._redis_client
        except Exception as e:
            logger.warning("Redis connection failed, using PostgreSQL only", error=str(e))
            return None
    
    async def _close_redis(self):
        """Close Redis connection."""
        if self._redis_client:
            try:
                await self._redis_client.aclose()
            except Exception:
                pass
            self._redis_client = None
    
    def _hash_key(self, api_key: str) -> str:
        """Generate SHA256 hash of API key."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def _serialize_key_data(self, key_model: APIKeyModel) -> str:
        """Serialize API key model to JSON for Redis storage."""
        return json.dumps({
            "key_hash": key_model.key_hash,
            "service_name": key_model.service_name,
            "scopes": key_model.scopes or [],
            "created_at": key_model.created_at.isoformat() if key_model.created_at else None,
            "expires_at": key_model.expires_at.isoformat() if key_model.expires_at else None,
            "is_active": key_model.is_active,
            "last_used_at": key_model.last_used_at.isoformat() if key_model.last_used_at else None,
            "created_by": key_model.created_by,
            "metadata": key_model.extra_metadata or {}
        })
    
    def _deserialize_key_data(self, data: str) -> Optional[Dict[str, Any]]:
        """Deserialize JSON data from Redis to dict."""
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Failed to deserialize API key data", error=str(e))
            return None
    
    async def create_api_key(
        self,
        api_key: str,
        service_name: str,
        scopes: List[str],
        expires_in_days: Optional[int] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a new API key in PostgreSQL and cache in Redis.
        
        Args:
            api_key: The plain API key (will be hashed)
            service_name: Service identifier
            scopes: List of permission scopes
            expires_in_days: Optional expiration in days
            created_by: Optional creator identifier
            metadata: Optional metadata dict
            
        Returns:
            True if successful, False otherwise
        """
        key_hash = self._hash_key(api_key)
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Create in PostgreSQL first (source of truth)
        try:
            async with self.db.get_session() as session:
                key_model = APIKeyModel(
                    key_hash=key_hash,
                    service_name=service_name,
                    scopes=scopes,
                    created_at=datetime.utcnow(),
                    expires_at=expires_at,
                    is_active=True,
                        created_by=created_by,
                        extra_metadata=metadata or {}
                )
                
                session.add(key_model)
                await session.commit()
                await session.refresh(key_model)
                
                logger.info(
                    "Created API key in PostgreSQL",
                    service_name=service_name,
                    key_hash=key_hash[:8] + "..."
                )
                
                # Cache in Redis (non-blocking)
                redis_client = await self._get_redis()
                if redis_client:
                    try:
                        key_data = self._serialize_key_data(key_model)
                        await redis_client.hset("api_keys", key_hash, key_data)
                        
                        # Set expiration if needed
                        if expires_at:
                            ttl = int((expires_at - datetime.utcnow()).total_seconds())
                            await redis_client.expire(f"api_keys:{key_hash}", ttl)
                        
                        logger.debug("Cached API key in Redis", key_hash=key_hash[:8] + "...")
                    except Exception as e:
                        logger.warning("Failed to cache API key in Redis", error=str(e))
                        # Continue - PostgreSQL is source of truth
                
                return True
                
        except Exception as e:
            logger.error("Failed to create API key", error=str(e))
            return False
    
    async def get_api_key_by_hash(self, key_hash: str) -> Optional[APIKeyModel]:
        """
        Get API key by hash, checking Redis first, then PostgreSQL.
        
        Args:
            key_hash: SHA256 hash of the API key
            
        Returns:
            APIKeyModel if found, None otherwise
        """
        # Try Redis cache first
        redis_client = await self._get_redis()
        if redis_client:
            try:
                key_data = await redis_client.hget("api_keys", key_hash)
                if key_data:
                    data = self._deserialize_key_data(key_data)
                    if data:
                        # Convert back to model
                        async with self.db.get_session() as session:
                            result = await session.execute(
                                select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
                            )
                            key_model = result.scalar_one_or_none()
                            if key_model:
                                logger.debug("API key found in Redis cache", key_hash=key_hash[:8] + "...")
                                return key_model
            except Exception as e:
                logger.debug("Redis lookup failed, falling back to PostgreSQL", error=str(e))
        
        # Fallback to PostgreSQL
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
                )
                key_model = result.scalar_one_or_none()
                
                if key_model:
                    # Populate Redis cache for next time
                    redis_client = await self._get_redis()
                    if redis_client:
                        try:
                            key_data = self._serialize_key_data(key_model)
                            await redis_client.hset("api_keys", key_hash, key_data)
                            logger.debug("Populated Redis cache from PostgreSQL", key_hash=key_hash[:8] + "...")
                        except Exception as e:
                            logger.debug("Failed to populate Redis cache", error=str(e))
                    
                    logger.debug("API key found in PostgreSQL", key_hash=key_hash[:8] + "...")
                    return key_model
                
                return None
                
        except Exception as e:
            logger.error("Failed to get API key from PostgreSQL", error=str(e))
            return None
    
    async def validate_api_key(self, api_key: str) -> Optional[APIKeyModel]:
        """
        Validate an API key and return the model if valid.
        
        Args:
            api_key: The plain API key to validate
            
        Returns:
            APIKeyModel if valid and active, None otherwise
        """
        key_hash = self._hash_key(api_key)
        key_model = await self.get_api_key_by_hash(key_hash)
        
        if not key_model:
            return None
        
        # Check if expired
        if key_model.expires_at and key_model.expires_at < datetime.utcnow():
            logger.debug("API key expired", key_hash=key_hash[:8] + "...")
            return None
        
        # Check if active
        if not key_model.is_active:
            logger.debug("API key is inactive", key_hash=key_hash[:8] + "...")
            return None
        
        # Update last_used_at (async, non-blocking)
        try:
            async with self.db.get_session() as session:
                await session.execute(
                    update(APIKeyModel)
                    .where(APIKeyModel.key_hash == key_hash)
                    .values(last_used_at=datetime.utcnow())
                )
                await session.commit()
        except Exception as e:
            logger.debug("Failed to update last_used_at", error=str(e))
        
        return key_model
    
    async def revoke_api_key(self, api_key: str) -> bool:
        """
        Revoke an API key (mark as inactive).
        
        Args:
            api_key: The plain API key to revoke
            
        Returns:
            True if revoked, False if not found
        """
        key_hash = self._hash_key(api_key)
        
        # Update in PostgreSQL
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    update(APIKeyModel)
                    .where(APIKeyModel.key_hash == key_hash)
                    .values(is_active=False)
                )
                await session.commit()
                
                if result.rowcount == 0:
                    return False
                
                logger.info("Revoked API key in PostgreSQL", key_hash=key_hash[:8] + "...")
                
                # Invalidate Redis cache
                redis_client = await self._get_redis()
                if redis_client:
                    try:
                        await redis_client.hdel("api_keys", key_hash)
                        logger.debug("Invalidated API key in Redis cache", key_hash=key_hash[:8] + "...")
                    except Exception as e:
                        logger.debug("Failed to invalidate Redis cache", error=str(e))
                
                return True
                
        except Exception as e:
            logger.error("Failed to revoke API key", error=str(e))
            return False
    
    async def list_api_keys(
        self,
        service_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[APIKeyModel]:
        """
        List API keys with optional filters.
        
        Args:
            service_name: Filter by service name
            is_active: Filter by active status
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of APIKeyModel instances
        """
        try:
            async with self.db.get_session() as session:
                stmt = select(APIKeyModel)
                
                if service_name:
                    stmt = stmt.where(APIKeyModel.service_name == service_name)
                
                if is_active is not None:
                    stmt = stmt.where(APIKeyModel.is_active == is_active)
                
                stmt = stmt.order_by(APIKeyModel.created_at.desc())
                stmt = stmt.limit(limit).offset(offset)
                
                result = await session.execute(stmt)
                return list(result.scalars().all())
                
        except Exception as e:
            logger.error("Failed to list API keys", error=str(e))
            return []
