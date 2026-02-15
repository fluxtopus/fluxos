"""Redis-based implementation of the Budget Controller."""

import json
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.exceptions import RedisError

from ..interfaces.budget_controller import (
    BudgetControllerInterface,
    BudgetConfig,
    ResourceLimit,
    ResourceUsage,
    ResourceType,
    BudgetExceededError
)
from ..core.config import settings
import structlog

logger = structlog.get_logger(__name__)


class RedisBudgetController(BudgetControllerInterface):
    """Redis-based budget controller with atomic operations."""
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "budget",
        db: int = 5  # Dedicated DB for budgets
    ):
        self.redis_url = redis_url or settings.REDIS_URL
        self.key_prefix = key_prefix
        self.db = db
        self._client: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()
    
    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = redis.from_url(
                        self.redis_url,
                        db=self.db,
                        decode_responses=True
                    )
        return self._client
    
    def _make_key(self, budget_id: str, suffix: Optional[str] = None) -> str:
        """Create a Redis key."""
        parts = [self.key_prefix, budget_id]
        if suffix:
            parts.append(suffix)
        return ":".join(parts)
    
    @asynccontextmanager
    async def _transaction(self, client: redis.Redis):
        """Execute operations in a transaction."""
        async with client.pipeline(transaction=True) as pipe:
            yield pipe
            await pipe.execute()
    
    async def create_budget(
        self,
        budget_id: str,
        config: BudgetConfig
    ) -> None:
        """Create a new budget configuration."""
        try:
            client = await self._get_client()
            
            # Store budget config
            config_data = {
                "owner": config.owner,
                "created_at": config.created_at.isoformat(),
                "metadata": json.dumps(config.metadata),
                "limits": json.dumps([
                    {
                        "resource_type": limit.resource_type.value,
                        "limit": limit.limit,
                        "period": limit.period,
                        "hard_limit": limit.hard_limit
                    }
                    for limit in config.limits
                ])
            }
            
            await client.hset(
                self._make_key(budget_id, "config"),
                mapping=config_data
            )
            
            # Initialize usage counters
            for limit in config.limits:
                await client.set(
                    self._make_key(budget_id, f"usage:{limit.resource_type.value}"),
                    0
                )
            
            logger.info(
                "Budget created",
                budget_id=budget_id,
                owner=config.owner,
                limits=[l.resource_type.value for l in config.limits]
            )
            
        except RedisError as e:
            logger.error("Failed to create budget", error=str(e), budget_id=budget_id)
            raise
    
    async def check_budget(
        self,
        budget_id: str,
        resource_type: ResourceType,
        amount: float
    ) -> bool:
        """Check if a resource usage would exceed budget."""
        try:
            client = await self._get_client()
            
            # Get current usage
            usage_key = self._make_key(budget_id, f"usage:{resource_type.value}")
            current = float(await client.get(usage_key) or 0)
            
            # Get limit
            config = await self.get_budget_config(budget_id)
            if not config:
                logger.warning("Budget not found", budget_id=budget_id)
                return False
            
            limit = next(
                (l for l in config.limits if l.resource_type == resource_type),
                None
            )
            
            if not limit:
                logger.warning(
                    "No limit configured for resource",
                    budget_id=budget_id,
                    resource_type=resource_type.value
                )
                return True  # No limit means unlimited
            
            return (current + amount) <= limit.limit
            
        except RedisError as e:
            logger.error("Failed to check budget", error=str(e), budget_id=budget_id)
            raise
    
    async def consume_budget(
        self,
        budget_id: str,
        resource_type: ResourceType,
        amount: float
    ) -> ResourceUsage:
        """Consume budget for a resource."""
        try:
            client = await self._get_client()
            
            # Get config first to check limits
            config = await self.get_budget_config(budget_id)
            if not config:
                raise ValueError(f"Budget {budget_id} not found")
            
            limit_config = next(
                (l for l in config.limits if l.resource_type == resource_type),
                None
            )
            
            if not limit_config:
                # No limit means unlimited
                return ResourceUsage(
                    resource_type=resource_type,
                    current=amount,
                    limit=float('inf'),
                    percentage=0.0,
                    exceeded=False
                )
            
            # Atomic increment and check
            usage_key = self._make_key(budget_id, f"usage:{resource_type.value}")
            
            # Use Lua script for atomic check and increment
            lua_script = """
                local key = KEYS[1]
                local amount = tonumber(ARGV[1])
                local limit = tonumber(ARGV[2])
                local hard_limit = ARGV[3] == '1'
                
                local current = tonumber(redis.call('GET', key) or 0)
                local new_total = current + amount
                
                if hard_limit and new_total > limit then
                    return {tostring(current), 0}  -- Don't increment
                else
                    redis.call('SET', key, tostring(new_total))
                    return {tostring(new_total), 1}  -- Incremented
                end
            """
            
            result = await client.eval(
                lua_script,
                1,
                usage_key,
                amount,
                limit_config.limit,
                '1' if limit_config.hard_limit else '0'
            )
            
            new_value = float(result[0])
            incremented = result[1]
            
            usage = ResourceUsage(
                resource_type=resource_type,
                current=new_value,
                limit=limit_config.limit,
                percentage=(new_value / limit_config.limit) * 100,
                exceeded=new_value > limit_config.limit
            )
            
            if not incremented and limit_config.hard_limit:
                raise BudgetExceededError(
                    resource_type=resource_type,
                    current=new_value + amount,
                    limit=limit_config.limit
                )
            
            # Log warning if soft limit exceeded
            if usage.exceeded and not limit_config.hard_limit:
                logger.warning(
                    "Soft budget limit exceeded",
                    budget_id=budget_id,
                    resource_type=resource_type.value,
                    current=new_value,
                    limit=limit_config.limit
                )
            
            return usage
            
        except RedisError as e:
            logger.error("Failed to consume budget", error=str(e), budget_id=budget_id)
            raise
    
    async def get_usage(
        self,
        budget_id: str,
        resource_type: Optional[ResourceType] = None
    ) -> List[ResourceUsage]:
        """Get current usage for a budget."""
        try:
            client = await self._get_client()
            
            config = await self.get_budget_config(budget_id)
            if not config:
                return []
            
            usage_list = []
            
            for limit in config.limits:
                if resource_type and limit.resource_type != resource_type:
                    continue
                
                usage_key = self._make_key(budget_id, f"usage:{limit.resource_type.value}")
                current = float(await client.get(usage_key) or 0)
                
                usage = ResourceUsage(
                    resource_type=limit.resource_type,
                    current=current,
                    limit=limit.limit,
                    percentage=(current / limit.limit) * 100 if limit.limit > 0 else 0,
                    exceeded=current > limit.limit
                )
                usage_list.append(usage)
            
            return usage_list
            
        except RedisError as e:
            logger.error("Failed to get usage", error=str(e), budget_id=budget_id)
            raise
    
    async def reset_budget(
        self,
        budget_id: str,
        resource_type: Optional[ResourceType] = None
    ) -> None:
        """Reset usage counters for a budget."""
        try:
            client = await self._get_client()
            
            if resource_type:
                # Reset specific resource
                usage_key = self._make_key(budget_id, f"usage:{resource_type.value}")
                await client.set(usage_key, 0)
            else:
                # Reset all resources
                config = await self.get_budget_config(budget_id)
                if config:
                    for limit in config.limits:
                        usage_key = self._make_key(
                            budget_id,
                            f"usage:{limit.resource_type.value}"
                        )
                        await client.set(usage_key, 0)
            
            logger.info(
                "Budget reset",
                budget_id=budget_id,
                resource_type=resource_type.value if resource_type else "all"
            )
            
        except RedisError as e:
            logger.error("Failed to reset budget", error=str(e), budget_id=budget_id)
            raise
    
    async def set_limit(
        self,
        budget_id: str,
        limit: ResourceLimit
    ) -> None:
        """Update a resource limit for a budget."""
        try:
            client = await self._get_client()
            
            config = await self.get_budget_config(budget_id)
            if not config:
                raise ValueError(f"Budget {budget_id} not found")
            
            # Update limit in config
            updated_limits = [
                l for l in config.limits
                if l.resource_type != limit.resource_type
            ]
            updated_limits.append(limit)
            
            config.limits = updated_limits
            await self.create_budget(budget_id, config)
            
            logger.info(
                "Budget limit updated",
                budget_id=budget_id,
                resource_type=limit.resource_type.value,
                new_limit=limit.limit
            )
            
        except RedisError as e:
            logger.error("Failed to set limit", error=str(e), budget_id=budget_id)
            raise
    
    async def get_budget_config(
        self,
        budget_id: str
    ) -> Optional[BudgetConfig]:
        """Get budget configuration."""
        try:
            client = await self._get_client()
            
            config_data = await client.hgetall(self._make_key(budget_id, "config"))
            if not config_data:
                return None
            
            limits_data = json.loads(config_data.get("limits", "[]"))
            limits = [
                ResourceLimit(
                    resource_type=ResourceType(l["resource_type"]),
                    limit=l["limit"],
                    period=l.get("period"),
                    hard_limit=l.get("hard_limit", True)
                )
                for l in limits_data
            ]
            
            return BudgetConfig(
                limits=limits,
                owner=config_data["owner"],
                created_at=datetime.fromisoformat(config_data["created_at"]),
                metadata=json.loads(config_data.get("metadata", "{}"))
            )
            
        except RedisError as e:
            logger.error("Failed to get budget config", error=str(e), budget_id=budget_id)
            raise
    
    async def delete_budget(
        self,
        budget_id: str
    ) -> None:
        """Delete a budget configuration."""
        try:
            client = await self._get_client()
            
            # Get all keys for this budget
            pattern = self._make_key(budget_id, "*")
            keys = []
            async for key in client.scan_iter(pattern):
                keys.append(key)
            
            if keys:
                await client.delete(*keys)
            
            logger.info("Budget deleted", budget_id=budget_id, keys_deleted=len(keys))
            
        except RedisError as e:
            logger.error("Failed to delete budget", error=str(e), budget_id=budget_id)
            raise
    
    async def create_child_budget(
        self,
        parent_budget_id: str,
        child_budget_id: str,
        config: BudgetConfig
    ) -> None:
        """Create a child budget that inherits and is constrained by parent limits."""
        try:
            # Get parent config
            parent_config = await self.get_budget_config(parent_budget_id)
            if not parent_config:
                raise ValueError(f"Parent budget {parent_budget_id} not found")
            
            # Validate child limits don't exceed parent
            for child_limit in config.limits:
                parent_limit = next(
                    (l for l in parent_config.limits 
                     if l.resource_type == child_limit.resource_type),
                    None
                )
                if parent_limit and child_limit.limit > parent_limit.limit:
                    raise ValueError(
                        f"Child limit for {child_limit.resource_type.value} "
                        f"({child_limit.limit}) exceeds parent limit ({parent_limit.limit})"
                    )
            
            # Create child budget
            await self.create_budget(child_budget_id, config)
            
            # Store parent-child relationship
            client = await self._get_client()
            await client.sadd(
                self._make_key(parent_budget_id, "children"),
                child_budget_id
            )
            await client.set(
                self._make_key(child_budget_id, "parent"),
                parent_budget_id
            )
            
            logger.info(
                "Child budget created",
                parent_id=parent_budget_id,
                child_id=child_budget_id
            )
            
        except RedisError as e:
            logger.error(
                "Failed to create child budget",
                error=str(e),
                parent_id=parent_budget_id,
                child_id=child_budget_id
            )
            raise
    
    async def get_budget_hierarchy(
        self,
        budget_id: str
    ) -> Dict[str, Any]:
        """Get the budget hierarchy tree."""
        try:
            client = await self._get_client()
            
            config = await self.get_budget_config(budget_id)
            if not config:
                return {}
            
            # Get parent
            parent_id = await client.get(self._make_key(budget_id, "parent"))
            
            # Get children
            children_ids = await client.smembers(self._make_key(budget_id, "children"))
            
            # Build hierarchy
            hierarchy = {
                "id": budget_id,
                "config": config,
                "parent": parent_id,
                "children": []
            }
            
            # Recursively get children
            for child_id in children_ids:
                child_hierarchy = await self.get_budget_hierarchy(child_id)
                hierarchy["children"].append(child_hierarchy)
            
            return hierarchy
            
        except RedisError as e:
            logger.error(
                "Failed to get budget hierarchy",
                error=str(e),
                budget_id=budget_id
            )
            raise
    
    async def health_check(self) -> bool:
        """Check if the budget controller is healthy."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.error("Budget controller health check failed", error=str(e))
            return False
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None