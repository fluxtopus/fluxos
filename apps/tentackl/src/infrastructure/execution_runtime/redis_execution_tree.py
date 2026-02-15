"""
Redis-based implementation of ExecutionTree interface

This module provides a production-ready ExecutionTree implementation using Redis
for tree storage, node tracking, and real-time updates.
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import asdict
from collections import defaultdict
import redis.asyncio as redis
import structlog
import os

from src.core.execution_tree import (
    ExecutionTreeInterface, ExecutionNode, ExecutionTreeSnapshot, 
    NodeType, ExecutionStatus, ExecutionPriority, ExecutionMetrics,
    TreeNotFoundError, NodeNotFoundError, CircularDependencyError, InvalidTreeStructureError
)


logger = structlog.get_logger()


class RedisExecutionTree(ExecutionTreeInterface):
    """
    Redis-based ExecutionTree implementation
    Follows SRP - handles only Redis-specific execution tree operations
    """
    
    def __init__(
        self,
        redis_url: str = None,
        db: int = 2,  # Use different DB from state store and context manager
        key_prefix: str = "tentackl:tree",
        connection_pool_size: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        enable_real_time_updates: bool = True
    ):
        """
        Initialize Redis ExecutionTree
        
        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for all Redis keys
            connection_pool_size: Size of connection pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connect timeout in seconds
            enable_real_time_updates: Enable real-time update notifications
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.db = db
        self.key_prefix = key_prefix
        self.connection_pool_size = connection_pool_size
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.enable_real_time_updates = enable_real_time_updates
        
        self._redis_pool = None
        self._is_connected = False
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: Dict[str, Dict[str, Callable]] = {}  # tree_id -> {subscription_id -> callback}
        self._pubsub_task: Optional[asyncio.Task] = None
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection from pool"""
        if not self._is_connected:
            await self._connect()
        return redis.Redis(connection_pool=self._redis_pool)
    
    async def _connect(self) -> None:
        """Establish Redis connection pool"""
        async with self._connect_lock:
            if self._is_connected:
                return
            try:
                # Use a blocking pool so callers wait instead of failing under burst load
                try:
                    BlockingPool = redis.BlockingConnectionPool
                except AttributeError:
                    # Fallback for environments without BlockingConnectionPool
                    BlockingPool = redis.ConnectionPool
                self._redis_pool = BlockingPool.from_url(
                    self.redis_url,
                    db=self.db,
                    max_connections=self.connection_pool_size,
                    timeout=self.socket_connect_timeout,
                    socket_timeout=self.socket_timeout,
                    decode_responses=True
                )
                
                # Test connection
                redis_client = redis.Redis(connection_pool=self._redis_pool)
                await redis_client.ping()
                await redis_client.aclose()
                
                self._is_connected = True
                
                # Start pub/sub for real-time updates (single listener)
                if self.enable_real_time_updates and not self._pubsub_task:
                    self._pubsub_task = asyncio.create_task(self._pubsub_listener())
                
                logger.info("Connected to Redis for execution tree", redis_url=self.redis_url, db=self.db)
                
            except Exception as e:
                logger.error("Failed to connect to Redis", error=str(e))
                raise InvalidTreeStructureError(f"Cannot connect to Redis: {e}")
    
    async def _disconnect(self) -> None:
        """Close Redis connection pool"""
        # Stop pub/sub listener
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        
        if self._redis_pool:
            await self._redis_pool.disconnect()
            self._is_connected = False
            logger.info("Disconnected from Redis execution tree")
    
    def _get_tree_key(self, tree_id: str) -> str:
        """Generate Redis key for tree metadata"""
        return f"{self.key_prefix}:tree:{tree_id}"
    
    def _get_node_key(self, tree_id: str, node_id: str) -> str:
        """Generate Redis key for node data"""
        return f"{self.key_prefix}:tree:{tree_id}:node:{node_id}"
    
    def _get_tree_nodes_key(self, tree_id: str) -> str:
        """Generate Redis key for tree's nodes set"""
        return f"{self.key_prefix}:tree:{tree_id}:nodes"
    
    def _get_node_children_key(self, tree_id: str, node_id: str) -> str:
        """Generate Redis key for node's children set"""
        return f"{self.key_prefix}:tree:{tree_id}:node:{node_id}:children"
    
    def _get_node_dependencies_key(self, tree_id: str, node_id: str) -> str:
        """Generate Redis key for node's dependencies set"""
        return f"{self.key_prefix}:tree:{tree_id}:node:{node_id}:deps"
    
    def _get_status_index_key(self, tree_id: str, status: ExecutionStatus) -> str:
        """Generate Redis key for status-based node index"""
        return f"{self.key_prefix}:tree:{tree_id}:status:{status.value}"
    
    def _get_update_channel(self, tree_id: str) -> str:
        """Generate Redis pub/sub channel for tree updates"""
        return f"{self.key_prefix}:updates:{tree_id}"
    
    def _serialize_node(self, node: ExecutionNode) -> str:
        """Serialize execution node to JSON string"""
        data = asdict(node)
        
        # Convert datetime fields to ISO strings
        data['created_at'] = node.created_at.isoformat()
        if node.scheduled_at:
            data['scheduled_at'] = node.scheduled_at.isoformat()
        
        # Convert metrics
        if node.metrics.start_time:
            data['metrics']['start_time'] = node.metrics.start_time.isoformat()
        if node.metrics.end_time:
            data['metrics']['end_time'] = node.metrics.end_time.isoformat()
        if node.metrics.duration:
            data['metrics']['duration'] = node.metrics.duration.total_seconds()
        
        # Convert enums to strings
        data['node_type'] = node.node_type.value
        data['status'] = node.status.value
        data['priority'] = node.priority.value
        
        # Convert sets to lists
        data['children_ids'] = list(node.children_ids)
        data['dependencies'] = list(node.dependencies)
        
        return json.dumps(data)
    
    def _deserialize_node(self, data: str) -> ExecutionNode:
        """Deserialize execution node from JSON string"""
        try:
            node_dict = json.loads(data)
            
            # Convert ISO strings back to datetime
            node_dict['created_at'] = datetime.fromisoformat(node_dict['created_at'])
            if node_dict.get('scheduled_at'):
                node_dict['scheduled_at'] = datetime.fromisoformat(node_dict['scheduled_at'])
            
            # Convert metrics
            if node_dict['metrics'].get('start_time'):
                node_dict['metrics']['start_time'] = datetime.fromisoformat(node_dict['metrics']['start_time'])
            if node_dict['metrics'].get('end_time'):
                node_dict['metrics']['end_time'] = datetime.fromisoformat(node_dict['metrics']['end_time'])
            if node_dict['metrics'].get('duration'):
                node_dict['metrics']['duration'] = timedelta(seconds=node_dict['metrics']['duration'])
            
            # Convert strings back to enums
            node_dict['node_type'] = NodeType(node_dict['node_type'])
            node_dict['status'] = ExecutionStatus(node_dict['status'])
            node_dict['priority'] = ExecutionPriority(node_dict['priority'])
            
            # Convert lists back to sets
            node_dict['children_ids'] = set(node_dict['children_ids'])
            node_dict['dependencies'] = set(node_dict['dependencies'])
            
            # Create ExecutionMetrics object
            metrics_data = node_dict['metrics']
            node_dict['metrics'] = ExecutionMetrics(**metrics_data)
            
            return ExecutionNode(**node_dict)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise InvalidTreeStructureError(f"Invalid node data: {e}")
    
    async def _publish_update(self, tree_id: str, node: ExecutionNode) -> None:
        """Publish real-time update for a node"""
        if not self.enable_real_time_updates:
            return

        try:
            redis_client = await self._get_redis()

            update_data = {
                "tree_id": tree_id,
                "node_id": node.id,
                "status": node.status.value,
                "timestamp": datetime.utcnow().isoformat(),
                "node_data": self._serialize_node(node)
            }

            channel = self._get_update_channel(tree_id)
            await redis_client.publish(channel, json.dumps(update_data))
            await redis_client.aclose()

        except Exception as e:
            logger.warning("Failed to publish update", tree_id=tree_id, node_id=node.id, error=str(e))

    async def _publish_websocket_update(
        self,
        tree_id: str,
        node: ExecutionNode,
        old_status: Optional[ExecutionStatus] = None
    ) -> None:
        """Publish node update to WebSocket channel for real-time UI updates."""
        if not self.enable_real_time_updates:
            return

        try:
            redis_client = await self._get_redis()

            # Prepare the message in the format expected by WorkflowEventPublisher
            message = {
                "type": "node_update",
                "data": {
                    "node_id": node.id,
                    "status": node.status.value,
                    "data": {
                        "name": node.name,
                        "result_data": node.result_data,
                        "error_data": node.error_data,
                        "started_at": node.metrics.start_time.isoformat() if node.metrics.start_time else None,
                        "completed_at": node.metrics.end_time.isoformat() if node.metrics.end_time else None,
                        "duration_seconds": node.metrics.duration.total_seconds() if node.metrics.duration else None,
                    }
                }
            }

            # Publish to the workflow WebSocket channel
            channel = f"workflow:{tree_id}"
            result = await redis_client.publish(channel, json.dumps(message))
            await redis_client.aclose()

            logger.info(
                "📡 Published WebSocket update",
                tree_id=tree_id,
                node_id=node.id,
                status=node.status.value,
                old_status=old_status.value if old_status else None,
                channel=channel,
                subscribers=result
            )

        except Exception as e:
            logger.error("❌ Failed to publish WebSocket update", tree_id=tree_id, node_id=node.id, error=str(e), exc_info=True)

    async def _pubsub_listener(self) -> None:
        """Listen for pub/sub updates and notify subscribers"""
        try:
            redis_client = await self._get_redis()
            pubsub = redis_client.pubsub()
            
            # Subscribe to all tree update channels
            await pubsub.psubscribe(f"{self.key_prefix}:updates:*")
            
            async for message in pubsub.listen():
                if message['type'] == 'pmessage':
                    try:
                        update_data = json.loads(message['data'])
                        tree_id = update_data['tree_id']
                        node_data = update_data['node_data']
                        
                        # Deserialize node and notify subscribers
                        node = self._deserialize_node(node_data)
                        
                        if tree_id in self._subscribers:
                            for callback in self._subscribers[tree_id].values():
                                try:
                                    callback(node)
                                except Exception as e:
                                    logger.warning("Subscriber callback failed", error=str(e))
                    
                    except Exception as e:
                        logger.warning("Failed to process pub/sub message", error=str(e))
            
            await pubsub.unsubscribe()
            await redis_client.aclose()
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Pub/sub listener error", error=str(e))
    
    async def create_tree(self, root_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new execution tree and return its ID.

        For this implementation, the provided root_name is used as the tree_id
        for simplicity and test compatibility.
        """
        try:
            redis_client = await self._get_redis()
            
            # Create root node
            root_node = ExecutionNode(
                id="root",
                name=metadata.get('name', root_name) if metadata else root_name,
                node_type=NodeType.ROOT,
                status=ExecutionStatus.PENDING
            )
            
            # Store tree metadata and root node
            tree_id = root_name
            tree_key = self._get_tree_key(tree_id)
            tree_nodes_key = self._get_tree_nodes_key(tree_id)
            root_node_key = self._get_node_key(tree_id, root_node.id)
            pending_status_key = self._get_status_index_key(tree_id, ExecutionStatus.PENDING)
            
            tree_metadata = {
                "tree_id": tree_id,
                "root_node_id": root_node.id,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            
            # Add commonly used fields to top level for easier access
            if metadata:
                tree_metadata["name"] = metadata.get("name", f"Workflow {tree_id}")
                tree_metadata["status"] = metadata.get("status", "pending")
                tree_metadata["type"] = metadata.get("type")
                tree_metadata["example_id"] = metadata.get("example_id")
            
            async with redis_client.pipeline(transaction=True) as pipe:
                # Store tree metadata
                pipe.set(tree_key, json.dumps(tree_metadata))
                
                # Store root node
                pipe.set(root_node_key, self._serialize_node(root_node))
                
                # Add to tree's nodes set
                pipe.sadd(tree_nodes_key, root_node.id)
                
                # Add to status index
                pipe.sadd(pending_status_key, root_node.id)
                
                await pipe.execute()
            
            await redis_client.aclose()
            
            logger.info("Created execution tree", tree_id=tree_id, root_agent_id=root_node.id)
            
            return tree_id
        except Exception as e:
            logger.error("Failed to create execution tree", error=str(e))
            raise InvalidTreeStructureError(f"Tree creation failed: {e}")
    
    async def add_node(
        self, 
        tree_id: str, 
        node: ExecutionNode, 
        parent_id: Optional[str] = None
    ) -> bool:
        """Add a node to the execution tree"""
        try:
            redis_client = await self._get_redis()
            
            # Check if tree exists
            tree_key = self._get_tree_key(tree_id)
            if not await redis_client.exists(tree_key):
                await redis_client.aclose()
                return False
            
            # Check for circular dependency if parent is specified
            if parent_id:
                if await self._would_create_cycle(tree_id, parent_id, node.id):
                    await redis_client.aclose()
                    raise CircularDependencyError(f"Adding node {node.id} would create circular dependency")
                
                # Update parent-child relationship
                node.parent_id = parent_id
            
            # Store node and update indices
            node_key = self._get_node_key(tree_id, node.id)
            tree_nodes_key = self._get_tree_nodes_key(tree_id)
            status_key = self._get_status_index_key(tree_id, node.status)
            
            async with redis_client.pipeline(transaction=True) as pipe:
                # Store node
                pipe.set(node_key, self._serialize_node(node))
                
                # Add to tree's nodes set
                pipe.sadd(tree_nodes_key, node.id)
                
                # Add to status index
                pipe.sadd(status_key, node.id)
                
                # Update parent's children if applicable
                if parent_id:
                    parent_children_key = self._get_node_children_key(tree_id, parent_id)
                    pipe.sadd(parent_children_key, node.id)
                
                # Store node dependencies
                if node.dependencies:
                    deps_key = self._get_node_dependencies_key(tree_id, node.id)
                    pipe.sadd(deps_key, *node.dependencies)
                
                await pipe.execute()
            
            await redis_client.aclose()
            
            logger.debug("Added node to tree", tree_id=tree_id, node_id=node.id, parent_id=parent_id)
            return True
            
        except Exception as e:
            logger.error("Failed to add node", tree_id=tree_id, node_id=node.id, error=str(e))
            return False
    
    async def _would_create_cycle(self, tree_id: str, parent_id: str, child_id: str) -> bool:
        """Check if adding child to parent would create a cycle"""
        # Simple cycle detection: check if parent_id is a descendant of child_id
        visited = set()
        to_visit = [child_id]
        
        while to_visit:
            current_id = to_visit.pop()
            if current_id in visited:
                continue
            
            if current_id == parent_id:
                return True
            
            visited.add(current_id)
            
            # Get children of current node
            children = await self.get_children(tree_id, current_id)
            to_visit.extend(child.id for child in children)
        
        return False
    
    async def update_node_status(
        self, 
        tree_id: str, 
        node_id: str, 
        status: ExecutionStatus,
        result_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update the status of a node"""
        try:
            redis_client = await self._get_redis()
            
            # Get current node using same client to reduce contention
            node_key = self._get_node_key(tree_id, node_id)
            raw = await redis_client.get(node_key)
            if not raw:
                logger.warning("Node not found during status update", tree_id=tree_id, node_id=node_id)
                await redis_client.aclose()
                return False
            node = self._deserialize_node(raw)
            
            old_status = node.status
            
            # Log status change
            if old_status != status:
                logger.info(f"🔄 Node '{node.name}' ({node_id}) status: {old_status.value} → {status.value} [tree: {tree_id}]")
            else:
                logger.debug(f"📝 Node '{node.name}' ({node_id}) updated data [tree: {tree_id}]")
            
            # Update node status and data
            if status == ExecutionStatus.RUNNING:
                node.start_execution()
                logger.debug(f"▶️ Node '{node.name}' started execution [tree: {tree_id}]")
            elif status == ExecutionStatus.COMPLETED:
                node.complete_execution(result_data)
                logger.debug(f"✅ Node '{node.name}' completed execution [tree: {tree_id}]")
            elif status == ExecutionStatus.FAILED:
                node.fail_execution(error_data or {})
                logger.error(f"❌ Node '{node.name}' failed execution [tree: {tree_id}]: {error_data}")
            else:
                node.status = status
                if result_data:
                    node.result_data.update(result_data)
                if error_data:
                    node.error_data = error_data
            
            # Update in Redis
            old_status_key = self._get_status_index_key(tree_id, old_status)
            new_status_key = self._get_status_index_key(tree_id, status)
            
            async with redis_client.pipeline(transaction=True) as pipe:
                # Update node data
                pipe.set(node_key, self._serialize_node(node))
                
                # Update status indices
                if old_status != status:
                    pipe.srem(old_status_key, node_id)
                    pipe.sadd(new_status_key, node_id)
                
                await pipe.execute()
            
            await redis_client.aclose()

            # Publish real-time update to internal channel
            await self._publish_update(tree_id, node)

            # Publish to WebSocket event channel for real-time UI updates
            await self._publish_websocket_update(tree_id, node, old_status)

            logger.debug(
                "Updated node status",
                tree_id=tree_id,
                node_id=node_id,
                old_status=old_status.value,
                new_status=status.value
            )

            return True
            
        except Exception as e:
            logger.error("Failed to update node status", tree_id=tree_id, node_id=node_id, error=str(e))
            return False

    async def update_node_dependencies(
        self,
        tree_id: str,
        node_id: str,
        new_dependencies: set
    ) -> bool:
        """Update the dependencies for a node.

        This is used when for_each nodes are expanded and downstream nodes
        need to depend on all expanded children instead of the original node.

        Args:
            tree_id: The tree ID
            node_id: The node to update
            new_dependencies: The new set of dependency node IDs

        Returns:
            True if successful, False otherwise
        """
        try:
            redis_client = await self._get_redis()

            # Get the current node
            node_key = self._get_node_key(tree_id, node_id)
            node_data = await redis_client.get(node_key)

            if not node_data:
                await redis_client.aclose()
                return False

            node = self._deserialize_node(node_data)
            old_deps = node.dependencies.copy() if node.dependencies else set()

            # Update the node's dependencies
            node.dependencies = new_dependencies

            # Get the dependencies Redis key
            deps_key = self._get_node_dependencies_key(tree_id, node_id)

            async with redis_client.pipeline(transaction=True) as pipe:
                # Update the serialized node data
                pipe.set(node_key, self._serialize_node(node))

                # Clear old dependencies and add new ones
                pipe.delete(deps_key)
                if new_dependencies:
                    pipe.sadd(deps_key, *new_dependencies)

                await pipe.execute()

            await redis_client.aclose()

            logger.debug(
                "Updated node dependencies",
                tree_id=tree_id,
                node_id=node_id,
                old_deps=list(old_deps),
                new_deps=list(new_dependencies)
            )

            return True

        except Exception as e:
            logger.error("Failed to update node dependencies", tree_id=tree_id, node_id=node_id, error=str(e))
            return False

    async def get_node(self, tree_id: str, node_id: str) -> Optional[ExecutionNode]:
        """Get a specific node from the tree"""
        try:
            redis_client = await self._get_redis()
            
            node_key = self._get_node_key(tree_id, node_id)
            node_data = await redis_client.get(node_key)
            
            await redis_client.aclose()
            
            if node_data:
                return self._deserialize_node(node_data)
            
            return None
            
        except Exception as e:
            logger.error("Failed to get node", tree_id=tree_id, node_id=node_id, error=str(e))
            return None
    
    async def get_tree_snapshot(self, tree_id: str) -> Optional[ExecutionTreeSnapshot]:
        """Get a snapshot of the entire execution tree"""
        try:
            redis_client = await self._get_redis()
            
            # Get tree metadata
            tree_key = self._get_tree_key(tree_id)
            tree_data = await redis_client.get(tree_key)
            
            if not tree_data:
                await redis_client.aclose()
                return None
            
            tree_metadata = json.loads(tree_data)
            
            # Get all nodes
            tree_nodes_key = self._get_tree_nodes_key(tree_id)
            node_ids = await redis_client.smembers(tree_nodes_key)
            
            nodes = {}
            for node_id in node_ids:
                node = await self.get_node(tree_id, node_id)
                if node:
                    nodes[node_id] = node
            
            await redis_client.aclose()
            
            snapshot = ExecutionTreeSnapshot(
                tree_id=tree_id,
                nodes=nodes,
                root_node_id=tree_metadata['root_node_id'],
                metadata=tree_metadata.get('metadata', {})
            )
            
            return snapshot
            
        except Exception as e:
            logger.error("Failed to get tree snapshot", tree_id=tree_id, error=str(e))
            return None
    
    async def get_children(self, tree_id: str, parent_id: str) -> List[ExecutionNode]:
        """Get all child nodes of a parent"""
        try:
            redis_client = await self._get_redis()
            
            parent_children_key = self._get_node_children_key(tree_id, parent_id)
            child_ids = await redis_client.smembers(parent_children_key)
            
            await redis_client.aclose()
            
            children = []
            for child_id in child_ids:
                child = await self.get_node(tree_id, child_id)
                if child:
                    children.append(child)
            
            return children
            
        except Exception as e:
            logger.error("Failed to get children", tree_id=tree_id, parent_id=parent_id, error=str(e))
            return []
    
    async def get_ready_nodes(self, tree_id: str) -> List[ExecutionNode]:
        """Get all nodes that are ready for execution"""
        try:
            redis_client = await self._get_redis()
            
            # Get all pending nodes
            pending_status_key = self._get_status_index_key(tree_id, ExecutionStatus.PENDING)
            pending_node_ids = await redis_client.smembers(pending_status_key)

            # Get all completed nodes for dependency checking
            # Include EXPANDED nodes as "completed" since their children will handle actual execution
            completed_status_key = self._get_status_index_key(tree_id, ExecutionStatus.COMPLETED)
            expanded_status_key = self._get_status_index_key(tree_id, ExecutionStatus.EXPANDED)

            completed_node_ids = await redis_client.smembers(completed_status_key)
            expanded_node_ids = await redis_client.smembers(expanded_status_key)

            # Merge completed and expanded nodes for dependency checking
            completed_node_ids = completed_node_ids.union(expanded_node_ids)

            await redis_client.aclose()
            
            ready_nodes = []
            for node_id in pending_node_ids:
                node = await self.get_node(tree_id, node_id)
                if node and node.is_ready_to_execute(completed_node_ids):
                    ready_nodes.append(node)
            
            return ready_nodes
            
        except Exception as e:
            logger.error("Failed to get ready nodes", tree_id=tree_id, error=str(e))
            return []

    async def get_running_nodes(self, tree_id: str) -> List[ExecutionNode]:
        """Get nodes currently in RUNNING state."""
        try:
            redis_client = await self._get_redis()
            running_status_key = self._get_status_index_key(tree_id, ExecutionStatus.RUNNING)
            node_ids = await redis_client.smembers(running_status_key)
            await redis_client.aclose()

            nodes: List[ExecutionNode] = []
            for node_id in node_ids:
                node = await self.get_node(tree_id, node_id)
                if node:
                    nodes.append(node)
            return nodes
        except Exception as e:
            logger.error("Failed to get running nodes", tree_id=tree_id, error=str(e))
            return []

    async def pause_running_nodes(self, tree_id: str) -> List[str]:
        """Pause all currently running nodes and return associated celery task IDs."""
        celery_ids: List[str] = []
        running_nodes = await self.get_running_nodes(tree_id)
        for node in running_nodes:
            celery_task_id = (node.metadata or {}).get("celery_task_id")
            if celery_task_id:
                celery_ids.append(str(celery_task_id))
            await self.update_node_status(tree_id, node.id, ExecutionStatus.PAUSED)
        return celery_ids

    async def resume_paused_nodes(self, tree_id: str) -> int:
        """Move PAUSED nodes back to PENDING and return number resumed."""
        resumed = 0
        try:
            redis_client = await self._get_redis()
            paused_status_key = self._get_status_index_key(tree_id, ExecutionStatus.PAUSED)
            node_ids = await redis_client.smembers(paused_status_key)
            await redis_client.aclose()

            for node_id in node_ids:
                ok = await self.update_node_status(tree_id, node_id, ExecutionStatus.PENDING)
                if ok:
                    resumed += 1
        except Exception as e:
            logger.error("Failed to resume paused nodes", tree_id=tree_id, error=str(e))
            return resumed
        return resumed
    
    async def subscribe_to_updates(
        self, 
        tree_id: str, 
        callback: Callable[[ExecutionNode], None]
    ) -> str:
        """Subscribe to real-time updates for a tree"""
        try:
            import uuid
            subscription_id = str(uuid.uuid4())
            
            if tree_id not in self._subscribers:
                self._subscribers[tree_id] = {}
            
            self._subscribers[tree_id][subscription_id] = callback
            
            logger.debug("Subscribed to tree updates", tree_id=tree_id, subscription_id=subscription_id)
            return subscription_id
            
        except Exception as e:
            logger.error("Failed to subscribe to updates", tree_id=tree_id, error=str(e))
            raise InvalidTreeStructureError(f"Subscription failed: {e}")
    
    async def unsubscribe_from_updates(self, subscription_id: str) -> bool:
        """Unsubscribe from tree updates"""
        try:
            for tree_id, tree_subs in self._subscribers.items():
                if subscription_id in tree_subs:
                    del tree_subs[subscription_id]
                    logger.debug("Unsubscribed from tree updates", subscription_id=subscription_id)
                    return True
            
            return False
            
        except Exception as e:
            logger.error("Failed to unsubscribe", subscription_id=subscription_id, error=str(e))
            return False
    
    async def delete_tree(self, tree_id: str) -> bool:
        """Delete an execution tree and all its nodes"""
        try:
            redis_client = await self._get_redis()
            
            # Get all node IDs
            tree_nodes_key = self._get_tree_nodes_key(tree_id)
            node_ids = await redis_client.smembers(tree_nodes_key)
            
            # Delete all tree-related keys
            keys_to_delete = [
                self._get_tree_key(tree_id),
                tree_nodes_key
            ]
            
            # Add node keys
            for node_id in node_ids:
                keys_to_delete.extend([
                    self._get_node_key(tree_id, node_id),
                    self._get_node_children_key(tree_id, node_id),
                    self._get_node_dependencies_key(tree_id, node_id)
                ])
            
            # Add status index keys
            for status in ExecutionStatus:
                keys_to_delete.append(self._get_status_index_key(tree_id, status))
            
            # Delete all keys
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
            
            await redis_client.aclose()
            
            # Remove subscribers
            if tree_id in self._subscribers:
                del self._subscribers[tree_id]
            
            logger.info("Deleted execution tree", tree_id=tree_id, nodes_count=len(node_ids))
            return True
            
        except Exception as e:
            logger.error("Failed to delete tree", tree_id=tree_id, error=str(e))
            return False
    
    async def get_execution_path(self, tree_id: str, node_id: str) -> List[ExecutionNode]:
        """Get the execution path from root to a specific node"""
        try:
            path = []
            current_node = await self.get_node(tree_id, node_id)
            
            while current_node:
                path.insert(0, current_node)
                if current_node.parent_id:
                    current_node = await self.get_node(tree_id, current_node.parent_id)
                else:
                    break
            
            return path
            
        except Exception as e:
            logger.error("Failed to get execution path", tree_id=tree_id, node_id=node_id, error=str(e))
            return []
    
    async def get_tree_metrics(self, tree_id: str) -> Dict[str, Any]:
        """Get aggregated metrics for the entire tree"""
        try:
            redis_client = await self._get_redis()
            
            # Get counts by status
            status_counts = {}
            total_nodes = 0
            
            for status in ExecutionStatus:
                status_key = self._get_status_index_key(tree_id, status)
                count = await redis_client.scard(status_key)
                status_counts[status.value] = count
                total_nodes += count
            
            await redis_client.aclose()
            
            # Calculate rates
            completion_rate = status_counts.get('completed', 0) / total_nodes if total_nodes > 0 else 0
            failure_rate = status_counts.get('failed', 0) / total_nodes if total_nodes > 0 else 0
            
            return {
                "tree_id": tree_id,
                "total_nodes": total_nodes,
                "status_counts": status_counts,
                "completion_rate": completion_rate,
                "failure_rate": failure_rate,
                "active_nodes": status_counts.get('running', 0)
            }
            
        except Exception as e:
            logger.error("Failed to get tree metrics", tree_id=tree_id, error=str(e))
            return {}
    
    async def health_check(self) -> bool:
        """Check if the execution tree is healthy"""
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
            logger.error("Execution tree health check failed", error=str(e))
            return False
    
    async def list_trees(self) -> List[str]:
        """List all execution tree IDs"""
        try:
            redis_client = await self._get_redis()
            
            # Find all tree keys using pattern matching
            # Looking specifically for tree metadata keys, not node/status keys
            pattern = f"{self.key_prefix}:tree:*"
            cursor = 0
            tree_ids = set()
            
            # Scan for all tree keys
            while True:
                cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
                for key in keys:
                    # Only process main tree metadata keys
                    # Skip keys that have :node:, :nodes, :status: etc.
                    if (':node:' not in key and 
                        not key.endswith(':nodes') and 
                        ':status:' not in key and
                        ':children' not in key and
                        ':deps' not in key):
                        # Extract tree ID from key: "prefix:tree:tree_id"
                        # Remove the prefix to get the tree_id
                        tree_id = key.replace(f"{self.key_prefix}:tree:", "")
                        tree_ids.add(tree_id)
                
                if cursor == 0:
                    break
            
            await redis_client.aclose()
            return list(tree_ids)
            
        except Exception as e:
            logger.error("Failed to list trees", error=str(e))
            return []
    
    async def get_tree(self, tree_id: str) -> Optional[Dict[str, Any]]:
        """Get the complete execution tree data"""
        try:
            redis_client = await self._get_redis()
            
            # Get tree metadata
            tree_key = self._get_tree_key(tree_id)
            tree_data = await redis_client.get(tree_key)
            
            if not tree_data:
                await redis_client.aclose()
                return None
            
            result = json.loads(tree_data)
            
            # Add nodes count
            tree_nodes_key = self._get_tree_nodes_key(tree_id)
            nodes_count = await redis_client.scard(tree_nodes_key)
            result['nodes_count'] = nodes_count
            
            await redis_client.aclose()
            return result
            
        except Exception as e:
            logger.error("Failed to get tree", tree_id=tree_id, error=str(e))
            return None
    
    async def get_tree_metadata(self, tree_id: str) -> Optional[Dict[str, Any]]:
        """Get tree-level metadata"""
        return await self.get_tree(tree_id)
    
    async def update_tree_metadata(self, tree_id: str, metadata: Dict[str, Any]) -> None:
        """Update tree-level metadata"""
        try:
            redis_client = await self._get_redis()
            
            # Get existing tree data
            tree_key = self._get_tree_key(tree_id)
            tree_data = await redis_client.get(tree_key)
            
            if tree_data:
                existing = json.loads(tree_data)
                
                # Update the metadata object
                if "metadata" not in existing:
                    existing["metadata"] = {}
                existing["metadata"].update(metadata)
                
                # Update commonly used fields at top level
                if "name" in metadata:
                    existing["name"] = metadata["name"]
                if "status" in metadata:
                    existing["status"] = metadata["status"]
                if "updated_at" in metadata:
                    existing["updated_at"] = metadata["updated_at"]
                if "completed_at" in metadata:
                    existing["completed_at"] = metadata["completed_at"]
                
                await redis_client.set(tree_key, json.dumps(existing))
            
            await redis_client.aclose()
            
        except Exception as e:
            logger.error("Failed to update tree metadata", tree_id=tree_id, error=str(e))
    
    async def update_tree(self, tree_id: str, metadata: Dict[str, Any]) -> None:
        """Alias for update_tree_metadata for backward compatibility"""
        await self.update_tree_metadata(tree_id, metadata)
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._disconnect()
