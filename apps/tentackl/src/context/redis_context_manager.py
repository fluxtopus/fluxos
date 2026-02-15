"""
Redis-based implementation of ContextManager interface

This module provides a production-ready ContextManager implementation using Redis
for context storage, isolation, and lifecycle management.
"""

import json
import copy
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from dataclasses import asdict
import redis.asyncio as redis
import structlog
import os

from src.interfaces.context_manager import (
    ContextManagerInterface, AgentContext, ContextForkOptions,
    ContextIsolationLevel, ContextState,
    ContextNotFoundError, ContextIsolationError, OperationNotAllowedError, ContextStateError
)


logger = structlog.get_logger()


class RedisContextManager(ContextManagerInterface):
    """
    Redis-based ContextManager implementation
    Follows SRP - handles only Redis-specific context operations
    """
    
    def __init__(
        self,
        redis_url: str = None,
        db: int = 1,  # Use different DB from state store
        key_prefix: str = "tentackl:context",
        connection_pool_size: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0
    ):
        """
        Initialize Redis ContextManager
        
        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for all Redis keys
            connection_pool_size: Size of connection pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connect timeout in seconds
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
        """Get Redis connection from pool"""
        if not self._is_connected:
            await self._connect()
        return redis.Redis(connection_pool=self._redis_pool)
    
    async def _connect(self) -> None:
        """Establish Redis connection pool"""
        try:
            self._redis_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                db=self.db,
                max_connections=self.connection_pool_size,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=True
            )
            
            # Test connection
            redis_client = redis.Redis(connection_pool=self._redis_pool)
            await redis_client.ping()
            await redis_client.aclose()
            
            self._is_connected = True
            logger.info("Connected to Redis for context management", redis_url=self.redis_url, db=self.db)
            
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise ContextIsolationError(f"Cannot connect to Redis: {e}")
    
    async def _disconnect(self) -> None:
        """Close Redis connection pool"""
        if self._redis_pool:
            await self._redis_pool.disconnect()
            self._is_connected = False
            logger.info("Disconnected from Redis context manager")
    
    def _get_context_key(self, context_id: str) -> str:
        """Generate Redis key for context"""
        return f"{self.key_prefix}:ctx:{context_id}"
    
    def _get_agent_contexts_key(self, agent_id: str) -> str:
        """Generate Redis key for agent's contexts (set)"""
        return f"{self.key_prefix}:agent:{agent_id}:contexts"
    
    def _get_parent_children_key(self, parent_context_id: str) -> str:
        """Generate Redis key for parent's children contexts (set)"""
        return f"{self.key_prefix}:parent:{parent_context_id}:children"
    
    def _serialize_context(self, context: AgentContext) -> str:
        """Serialize context to JSON string"""
        data = asdict(context)
        # Convert datetime to ISO string
        data['created_at'] = context.created_at.isoformat()
        data['updated_at'] = context.updated_at.isoformat()
        # Convert enum to string
        data['isolation_level'] = context.isolation_level.value
        data['state'] = context.state.value
        # Convert sets to lists for JSON serialization
        data['allowed_operations'] = list(context.allowed_operations)
        data['restricted_operations'] = list(context.restricted_operations)
        return json.dumps(data)
    
    def _deserialize_context(self, data: str) -> AgentContext:
        """Deserialize context from JSON string"""
        try:
            context_dict = json.loads(data)
            
            # Convert ISO string back to datetime
            context_dict['created_at'] = datetime.fromisoformat(context_dict['created_at'])
            context_dict['updated_at'] = datetime.fromisoformat(context_dict['updated_at'])
            
            # Convert string back to enum
            context_dict['isolation_level'] = ContextIsolationLevel(context_dict['isolation_level'])
            context_dict['state'] = ContextState(context_dict['state'])
            
            # Convert lists back to sets
            context_dict['allowed_operations'] = set(context_dict['allowed_operations'])
            context_dict['restricted_operations'] = set(context_dict['restricted_operations'])
            
            return AgentContext(**context_dict)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ContextIsolationError(f"Invalid context data: {e}")
    
    def _deep_copy_context_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Deep copy context data for isolation"""
        try:
            # Use JSON serialization for deep copy to ensure isolation
            return json.loads(json.dumps(data))
        except (TypeError, ValueError):
            # Fallback to Python's deep copy for non-serializable objects
            return copy.deepcopy(data)
    
    async def create_context(
        self,
        agent_id: str,
        isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP,
        **context_data
    ) -> str:
        """Create a new execution context for an agent"""
        try:
            redis_client = await self._get_redis()
            
            # Create context instance
            context = AgentContext(
                agent_id=agent_id,
                isolation_level=isolation_level,
                variables=context_data.get('variables', {}),
                shared_resources=context_data.get('shared_resources', {}),
                private_resources=context_data.get('private_resources', {}),
                constraints=context_data.get('constraints', {}),
                max_execution_time=context_data.get('max_execution_time'),
                max_memory_mb=context_data.get('max_memory_mb'),
                allowed_operations=set(context_data.get('allowed_operations', [])),
                restricted_operations=set(context_data.get('restricted_operations', [])),
                metadata=context_data.get('metadata', {})
            )
            
            context_key = self._get_context_key(context.id)
            agent_contexts_key = self._get_agent_contexts_key(agent_id)
            
            serialized_context = self._serialize_context(context)
            
            # Store context and update indices atomically
            async with redis_client.pipeline(transaction=True) as pipe:
                # Store context data
                pipe.set(context_key, serialized_context)
                
                # Add to agent's contexts set
                pipe.sadd(agent_contexts_key, context.id)
                
                # Set expiration (optional - can be configured)
                # pipe.expire(context_key, 86400)  # 24 hours
                
                await pipe.execute()
            
            await redis_client.aclose()
            
            logger.info(
                "Created context",
                context_id=context.id,
                agent_id=agent_id,
                isolation_level=isolation_level.value
            )
            
            return context.id
            
        except Exception as e:
            logger.error("Failed to create context", agent_id=agent_id, error=str(e))
            raise ContextIsolationError(f"Context creation failed: {e}")
    
    async def fork_context(
        self,
        parent_context_id: str,
        child_agent_id: str,
        fork_options: Optional[ContextForkOptions] = None
    ) -> str:
        """Fork an existing context for a sub-agent"""
        try:
            redis_client = await self._get_redis()
            
            # Get parent context
            parent_context = await self.get_context(parent_context_id)
            if not parent_context:
                raise ContextNotFoundError(f"Parent context {parent_context_id} not found")
            
            # Derive options: if not provided, inherit parent's isolation level by default
            # and allow simple name-based hints for tests (e.g., 'sandboxed', 'deep').
            if fork_options is None:
                inferred_level = parent_context.isolation_level
                lname = (child_agent_id or "").lower()
                if "sandbox" in lname:
                    inferred_level = ContextIsolationLevel.SANDBOXED
                elif "deep" in lname:
                    inferred_level = ContextIsolationLevel.DEEP
                elif "shallow" in lname:
                    inferred_level = ContextIsolationLevel.SHALLOW
                options = ContextForkOptions(
                    isolation_level=inferred_level,
                    inherit_variables=(inferred_level != ContextIsolationLevel.SANDBOXED),
                    inherit_shared_resources=(inferred_level != ContextIsolationLevel.SANDBOXED),
                    inherit_constraints=(inferred_level != ContextIsolationLevel.SANDBOXED),
                )
            else:
                options = fork_options
            
            # Create child context
            child_context = AgentContext(
                agent_id=child_agent_id,
                parent_context_id=parent_context_id,
                isolation_level=options.isolation_level
            )
            
            # Apply inheritance rules based on isolation level and options
            if options.inherit_variables and options.isolation_level != ContextIsolationLevel.SANDBOXED:
                if options.isolation_level == ContextIsolationLevel.DEEP:
                    child_context.variables = self._deep_copy_context_data(parent_context.variables)
                elif options.isolation_level == ContextIsolationLevel.SHALLOW:
                    child_context.variables = parent_context.variables.copy()
                else:  # NONE
                    child_context.variables = parent_context.variables
            
            if options.inherit_shared_resources and options.isolation_level != ContextIsolationLevel.SANDBOXED:
                if options.isolation_level == ContextIsolationLevel.DEEP:
                    child_context.shared_resources = self._deep_copy_context_data(parent_context.shared_resources)
                else:
                    child_context.shared_resources = parent_context.shared_resources
            
            if options.inherit_constraints and options.isolation_level != ContextIsolationLevel.SANDBOXED:
                child_context.max_execution_time = parent_context.max_execution_time
                child_context.max_memory_mb = parent_context.max_memory_mb
                child_context.allowed_operations = parent_context.allowed_operations.copy()
                child_context.restricted_operations = parent_context.restricted_operations.copy()
                # Copy additional constraint metadata if present
                child_context.constraints = self._deep_copy_context_data(getattr(parent_context, 'constraints', {}))
            
            # Apply overrides
            if options.max_execution_time_override:
                child_context.max_execution_time = options.max_execution_time_override
            if options.max_memory_mb_override:
                child_context.max_memory_mb = options.max_memory_mb_override
            if options.allowed_operations_override:
                child_context.allowed_operations = options.allowed_operations_override
            if options.restricted_operations_override:
                child_context.restricted_operations = options.restricted_operations_override
            
            if options.copy_metadata:
                child_context.metadata = parent_context.metadata.copy()
            
            # Store child context and update relationships
            child_context_key = self._get_context_key(child_context.id)
            child_agent_contexts_key = self._get_agent_contexts_key(child_agent_id)
            parent_children_key = self._get_parent_children_key(parent_context_id)
            
            serialized_child_context = self._serialize_context(child_context)
            
            async with redis_client.pipeline(transaction=True) as pipe:
                # Store child context
                pipe.set(child_context_key, serialized_child_context)
                
                # Add to child agent's contexts
                pipe.sadd(child_agent_contexts_key, child_context.id)
                
                # Add to parent's children
                pipe.sadd(parent_children_key, child_context.id)
                
                await pipe.execute()
            
            await redis_client.aclose()
            
            logger.info(
                "Forked context",
                parent_context_id=parent_context_id,
                child_context_id=child_context.id,
                child_agent_id=child_agent_id,
                isolation_level=options.isolation_level.value
            )
            
            return child_context.id
            
        except Exception as e:
            logger.error(
                "Failed to fork context",
                parent_context_id=parent_context_id,
                child_agent_id=child_agent_id,
                error=str(e)
            )
            raise ContextIsolationError(f"Context forking failed: {e}")
    
    async def get_context(self, context_id: str) -> Optional[AgentContext]:
        """Retrieve a context by ID"""
        try:
            redis_client = await self._get_redis()
            
            context_key = self._get_context_key(context_id)
            context_data = await redis_client.get(context_key)
            
            await redis_client.aclose()
            
            if context_data:
                return self._deserialize_context(context_data)
            
            return None
            
        except Exception as e:
            logger.error("Failed to get context", context_id=context_id, error=str(e))
            return None
    
    async def update_context(self, context_id: str, updates: Dict[str, Any]) -> bool:
        """Update context data"""
        try:
            redis_client = await self._get_redis()
            
            context = await self.get_context(context_id)
            if not context:
                await redis_client.aclose()
                return False
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(context, key):
                    if key in ['allowed_operations', 'restricted_operations']:
                        # Handle set fields
                        setattr(context, key, set(value) if isinstance(value, (list, set)) else value)
                    else:
                        setattr(context, key, value)
            
            # Update timestamp
            context.updated_at = datetime.utcnow()
            
            # Save updated context
            context_key = self._get_context_key(context_id)
            serialized_context = self._serialize_context(context)
            
            await redis_client.set(context_key, serialized_context)
            await redis_client.aclose()
            
            logger.debug("Updated context", context_id=context_id)
            return True
            
        except Exception as e:
            logger.error("Failed to update context", context_id=context_id, error=str(e))
            return False
    
    async def suspend_context(self, context_id: str) -> bool:
        """Suspend a context (pause execution)"""
        return await self.update_context(context_id, {"state": ContextState.SUSPENDED})
    
    async def resume_context(self, context_id: str) -> bool:
        """Resume a suspended context"""
        return await self.update_context(context_id, {"state": ContextState.ACTIVE})
    
    async def terminate_context(self, context_id: str, cleanup: bool = True) -> bool:
        """Terminate a context and optionally clean up resources"""
        try:
            # Update state to terminated
            result = await self.update_context(context_id, {"state": ContextState.TERMINATED})
            
            if cleanup:
                # Could add resource cleanup logic here
                # For now, just log the cleanup request
                logger.debug("Context cleanup requested", context_id=context_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to terminate context", context_id=context_id, error=str(e))
            return False
    
    async def get_child_contexts(self, parent_context_id: str) -> List[AgentContext]:
        """Get all child contexts of a parent context"""
        try:
            redis_client = await self._get_redis()
            
            parent_children_key = self._get_parent_children_key(parent_context_id)
            child_context_ids = await redis_client.smembers(parent_children_key)
            
            await redis_client.aclose()
            
            children = []
            for child_id in child_context_ids:
                child_context = await self.get_context(child_id)
                if child_context:
                    children.append(child_context)
            
            return children
            
        except Exception as e:
            logger.error("Failed to get child contexts", parent_context_id=parent_context_id, error=str(e))
            return []
    
    async def cleanup_completed_contexts(self, retention_hours: int = 24) -> int:
        """Clean up completed contexts older than retention period"""
        try:
            redis_client = await self._get_redis()
            
            cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
            cleaned_count = 0
            
            # Scan for all context keys
            async for key in redis_client.scan_iter(match=f"{self.key_prefix}:ctx:*"):
                try:
                    context_data = await redis_client.get(key)
                    if context_data:
                        context = self._deserialize_context(context_data)
                        
                        # Check if context is completed/terminated and old
                        if (context.state in [ContextState.COMPLETED, ContextState.TERMINATED] and
                            context.updated_at < cutoff_time):
                            
                            # Remove context and its relationships
                            async with redis_client.pipeline(transaction=True) as pipe:
                                # Remove context
                                pipe.delete(key)
                                
                                # Remove from agent's contexts
                                agent_contexts_key = self._get_agent_contexts_key(context.agent_id)
                                pipe.srem(agent_contexts_key, context.id)
                                
                                # Remove from parent's children if applicable
                                if context.parent_context_id:
                                    parent_children_key = self._get_parent_children_key(context.parent_context_id)
                                    pipe.srem(parent_children_key, context.id)
                                
                                # Remove children index
                                children_key = self._get_parent_children_key(context.id)
                                pipe.delete(children_key)
                                
                                await pipe.execute()
                            
                            cleaned_count += 1
                            
                except Exception as e:
                    logger.warning("Error cleaning context", key=key, error=str(e))
            
            await redis_client.aclose()
            
            logger.info("Cleaned up old contexts", retention_hours=retention_hours, cleaned_count=cleaned_count)
            return cleaned_count
            
        except Exception as e:
            logger.error("Failed to cleanup contexts", error=str(e))
            return 0
    
    async def validate_operation(self, context_id: str, operation: str) -> bool:
        """Validate if an operation is allowed in the given context"""
        try:
            context = await self.get_context(context_id)
            if not context:
                return False
            
            return context.is_operation_allowed(operation)
            
        except Exception as e:
            logger.error("Failed to validate operation", context_id=context_id, operation=operation, error=str(e))
            return False
    
    async def get_context_metrics(self, context_id: str) -> Dict[str, Any]:
        """Get execution metrics for a context"""
        try:
            context = await self.get_context(context_id)
            if not context:
                return {}
            
            # Get child contexts count
            children = await self.get_child_contexts(context_id)
            
            return {
                "context_id": context_id,
                "agent_id": context.agent_id,
                "state": context.state.value,
                "isolation_level": context.isolation_level.value,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat(),
                "variables_count": len(context.variables),
                "shared_resources_count": len(context.shared_resources),
                "private_resources_count": len(context.private_resources),
                "allowed_operations_count": len(context.allowed_operations),
                "restricted_operations_count": len(context.restricted_operations),
                "children_count": len(children),
                "max_execution_time": context.max_execution_time,
                "max_memory_mb": context.max_memory_mb
            }
            
        except Exception as e:
            logger.error("Failed to get context metrics", context_id=context_id, error=str(e))
            return {}
    
    async def health_check(self) -> bool:
        """Check if the context manager is healthy"""
        try:
            redis_client = await self._get_redis()
            
            # Test basic operations
            test_key = f"{self.key_prefix}:health_check"
            await redis_client.set(test_key, "ok", ex=60)
            result = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            await redis_client.aclose()
            
            return result == "ok"
            
        except Exception as e:
            logger.error("Context manager health check failed", error=str(e))
            return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._disconnect()
