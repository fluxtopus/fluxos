"""
Unit tests for RedisExecutionTree implementation

These tests validate the Redis ExecutionTree implementation with thread safety,
concurrent operations, and pub/sub functionality using the existing Redis service.
"""

import pytest
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import redis.asyncio as redis

from src.core.execution_tree import (
    ExecutionNode, NodeType, ExecutionStatus, ExecutionPriority,
    ExecutionMetrics, TreeNotFoundError, NodeNotFoundError, 
    CircularDependencyError, InvalidTreeStructureError
)
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree


class TestRedisExecutionTree:
    """Test RedisExecutionTree implementation with thread safety focus"""
    
    @pytest.fixture
    async def execution_tree(self):
        """Create RedisExecutionTree instance using Docker service"""
        # Use the Redis service from docker-compose
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
        tree = RedisExecutionTree(
            redis_url=redis_url,
            db=4,  # Use separate DB for tests
            key_prefix="test:tree",
            connection_pool_size=25  # Increased for concurrent tests
        )
        
        # Ensure clean state for each test
        redis_client = redis.Redis.from_url(redis_url, db=4, decode_responses=True)
        await redis_client.flushdb()
        await redis_client.close()
        
        yield tree
        
        # Cleanup after test
        await tree._disconnect()
    
    @pytest.mark.asyncio
    async def test_redis_specific_serialization(self, execution_tree):
        """Test Redis-specific serialization and deserialization"""
        # Create complex node with all fields populated
        node = ExecutionNode(
            name="complex_node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.PENDING,
            priority=ExecutionPriority.HIGH,
            task_data={"model": "gpt-4", "timeout": 300},
            result_data={"complex": {"nested": [1, 2, {"inner": "value"}]}},
            dependencies={"dep1", "dep2", "dep3"}
        )
        
        # Test serialization roundtrip
        serialized = execution_tree._serialize_node(node)
        deserialized = execution_tree._deserialize_node(serialized)
        
        assert deserialized.name == node.name
        assert deserialized.node_type == node.node_type
        assert deserialized.status == node.status
        assert deserialized.priority == node.priority
        assert deserialized.task_data == node.task_data
        assert deserialized.result_data == node.result_data
        assert deserialized.dependencies == node.dependencies
    
    @pytest.mark.asyncio
    async def test_concurrent_node_status_updates(self, execution_tree):
        """Test thread safety of concurrent node status updates"""
        tree_id = await execution_tree.create_tree("concurrent_updates")
        
        # Create test nodes
        nodes = []
        for i in range(10):
            node = ExecutionNode(
                name=f"concurrent_node_{i}",
                node_type=NodeType.AGENT,
                status=ExecutionStatus.PENDING
            )
            await execution_tree.add_node(tree_id, node)
            nodes.append(node)
        
        async def update_node_status(node_id: str, iteration: int):
            """Update node status multiple times"""
            results = []
            
            # Running
            result = await execution_tree.update_node_status(
                tree_id, node_id, ExecutionStatus.RUNNING
            )
            results.append(result)
            
            # Simulate some work
            await asyncio.sleep(0.01)
            
            # Complete with result data
            result = await execution_tree.update_node_status(
                tree_id, node_id, ExecutionStatus.COMPLETED,
                result_data={"iteration": iteration, "result": f"completed_{iteration}"}
            )
            results.append(result)
            
            return all(results)
        
        # Run concurrent updates
        tasks = [
            update_node_status(node.id, i) 
            for i, node in enumerate(nodes)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All updates should succeed
        successful = [r for r in results if r is True]
        assert len(successful) == len(nodes), f"Expected {len(nodes)} successful updates, got {len(successful)}"
        
        # No exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"
        
        # Verify final states
        for i, node in enumerate(nodes):
            updated_node = await execution_tree.get_node(tree_id, node.id)
            assert updated_node.status == ExecutionStatus.COMPLETED
            assert updated_node.result_data["iteration"] == i
            assert updated_node.result_data["result"] == f"completed_{i}"
    
    @pytest.mark.asyncio
    async def test_concurrent_tree_operations(self, execution_tree):
        """Test concurrent tree creation, modification, and deletion"""
        
        async def create_and_populate_tree(tree_index: int):
            """Create a tree and add nodes to it"""
            tree_id = await execution_tree.create_tree(f"concurrent_tree_{tree_index}")
            
            # Add several nodes
            for i in range(5):
                node = ExecutionNode(
                    name=f"node_{tree_index}_{i}",
                    node_type=NodeType.AGENT,
                    status=ExecutionStatus.PENDING,
                    task_data={"tree_index": tree_index, "node_index": i}
                )
                success = await execution_tree.add_node(tree_id, node)
                if not success:
                    return False
            
            # Get snapshot to verify
            snapshot = await execution_tree.get_tree_snapshot(tree_id)
            return snapshot is not None and len(snapshot.nodes) == 6  # 5 + root
        
        # Create 15 trees concurrently
        tasks = [create_and_populate_tree(i) for i in range(15)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All operations should succeed
        successful = [r for r in results if r is True]
        assert len(successful) == 15, f"Expected 15 successful tree operations, got {len(successful)}"
        
        # No exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"
    
    @pytest.mark.asyncio
    async def test_ready_nodes_calculation_thread_safety(self, execution_tree):
        """Test thread safety of ready nodes calculation with concurrent updates"""
        tree_id = await execution_tree.create_tree("ready_nodes_test")
        
        # Create a dependency chain: A -> B -> C, D -> E
        node_a = ExecutionNode(name="A", node_type=NodeType.AGENT, status=ExecutionStatus.PENDING)
        node_b = ExecutionNode(name="B", node_type=NodeType.AGENT, status=ExecutionStatus.PENDING, dependencies={node_a.id})
        node_c = ExecutionNode(name="C", node_type=NodeType.AGENT, status=ExecutionStatus.PENDING, dependencies={node_b.id})
        node_d = ExecutionNode(name="D", node_type=NodeType.AGENT, status=ExecutionStatus.PENDING)
        node_e = ExecutionNode(name="E", node_type=NodeType.AGENT, status=ExecutionStatus.PENDING, dependencies={node_d.id})
        
        # Add all nodes
        for node in [node_a, node_b, node_c, node_d, node_e]:
            await execution_tree.add_node(tree_id, node)
        
        async def update_and_check_ready():
            """Concurrently update status and check ready nodes"""
            results = []
            
            # Check initial ready nodes
            ready = await execution_tree.get_ready_nodes(tree_id)
            results.append(("initial", len(ready)))
            
            # Complete A
            await execution_tree.update_node_status(tree_id, node_a.id, ExecutionStatus.COMPLETED)
            ready = await execution_tree.get_ready_nodes(tree_id)
            results.append(("after_a", len(ready)))
            
            # Complete D
            await execution_tree.update_node_status(tree_id, node_d.id, ExecutionStatus.COMPLETED)
            ready = await execution_tree.get_ready_nodes(tree_id)
            results.append(("after_d", len(ready)))
            
            return results
        
        # Run multiple concurrent ready node calculations
        tasks = [update_and_check_ready() for _ in range(5)]
        all_results = await asyncio.gather(*tasks)
        
        # Verify consistent results across all concurrent operations
        for results in all_results:
            # Initially, A and D should be ready (no dependencies)
            initial_ready = next(r[1] for r in results if r[0] == "initial")
            assert initial_ready >= 2, f"Expected at least 2 ready nodes initially, got {initial_ready}"
    
    @pytest.mark.asyncio
    async def test_large_tree_performance(self, execution_tree):
        """Test performance with large execution trees"""
        tree_id = await execution_tree.create_tree("large_tree_test")
        
        # Create a large tree with 100 nodes
        start_time = datetime.utcnow()
        
        # Create nodes in batches for better performance
        batch_size = 20
        all_nodes = []
        
        for batch_start in range(0, 100, batch_size):
            batch_nodes = []
            for i in range(batch_start, min(batch_start + batch_size, 100)):
                node = ExecutionNode(
                    name=f"large_node_{i}",
                    node_type=NodeType.AGENT,
                    status=ExecutionStatus.PENDING,
                    task_data={"index": i, "batch": batch_start // batch_size}
                )
                batch_nodes.append(node)
                all_nodes.append(node)
            
            # Add batch concurrently
            batch_tasks = [execution_tree.add_node(tree_id, node) for node in batch_nodes]
            batch_results = await asyncio.gather(*batch_tasks)
            assert all(batch_results), f"Batch {batch_start // batch_size} failed"
        
        creation_time = (datetime.utcnow() - start_time).total_seconds()
        assert creation_time < 30.0, f"Tree creation took too long: {creation_time}s"
        
        # Test concurrent status updates
        update_start = datetime.utcnow()
        
        # Update status of all nodes concurrently
        update_tasks = [
            execution_tree.update_node_status(tree_id, node.id, ExecutionStatus.RUNNING)
            for node in all_nodes[:50]  # Update first 50 nodes
        ]
        update_results = await asyncio.gather(*update_tasks)
        
        update_time = (datetime.utcnow() - update_start).total_seconds()
        assert update_time < 15.0, f"Concurrent updates took too long: {update_time}s"
        assert all(update_results), "All updates should succeed"
        
        # Test tree snapshot performance
        snapshot_start = datetime.utcnow()
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        snapshot_time = (datetime.utcnow() - snapshot_start).total_seconds()
        
        assert snapshot is not None
        assert len(snapshot.nodes) == 101  # 100 + root node
        assert snapshot_time < 10.0, f"Snapshot creation took too long: {snapshot_time}s"
    
    @pytest.mark.asyncio
    async def test_error_handling_thread_safety(self, execution_tree):
        """Test error handling under concurrent operations"""
        tree_id = await execution_tree.create_tree("error_handling_test")
        
        async def operation_with_errors(operation_id: int):
            """Perform operations that may encounter errors"""
            try:
                # Try to get non-existent node
                node = await execution_tree.get_node(tree_id, f"non_existent_{operation_id}")
                assert node is None
                
                # Try to update non-existent node
                success = await execution_tree.update_node_status(
                    tree_id, f"non_existent_{operation_id}", ExecutionStatus.RUNNING
                )
                assert success is False
                
                # Create valid node
                valid_node = ExecutionNode(
                    name=f"error_test_node_{operation_id}",
                    node_type=NodeType.AGENT,
                    status=ExecutionStatus.PENDING
                )
                success = await execution_tree.add_node(tree_id, valid_node)
                assert success is True
                
                return True
                
            except Exception as e:
                return e
        
        # Run many concurrent operations with potential errors
        tasks = [operation_with_errors(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All operations should handle errors gracefully
        successful = [r for r in results if r is True]
        assert len(successful) == 20, f"Expected 20 successful operations, got {len(successful)}"
        
        # No unhandled exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"
    
    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion_resilience(self, execution_tree):
        """Test resilience to connection pool exhaustion"""
        tree_id = await execution_tree.create_tree("connection_pool_test")
        
        async def heavy_redis_operation(operation_id: int):
            """Perform multiple Redis operations rapidly"""
            try:
                # Create node
                node = ExecutionNode(
                    name=f"pool_test_node_{operation_id}",
                    node_type=NodeType.AGENT,
                    status=ExecutionStatus.PENDING
                )
                
                # Multiple operations in sequence
                success1 = await execution_tree.add_node(tree_id, node)
                success2 = await execution_tree.update_node_status(tree_id, node.id, ExecutionStatus.RUNNING)
                retrieved = await execution_tree.get_node(tree_id, node.id)
                success3 = await execution_tree.update_node_status(tree_id, node.id, ExecutionStatus.COMPLETED)
                
                return all([success1, success2, retrieved is not None, success3])
                
            except Exception as e:
                return e
        
        # Run many operations concurrently to stress connection pool
        tasks = [heavy_redis_operation(i) for i in range(30)]  # More than pool size
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Most operations should succeed (allow for some failures under extreme load)
        successful = [r for r in results if r is True]
        success_rate = len(successful) / len(tasks)
        
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2%}"
        
        # Check that pool recovered
        health = await execution_tree.health_check()
        assert health is True, "ExecutionTree should be healthy after load test"
    
    @pytest.mark.asyncio
    async def test_basic_tree_operations(self, execution_tree):
        """Test basic tree operations work correctly"""
        # Create a tree
        tree_id = await execution_tree.create_tree("basic_test")
        assert tree_id is not None
        
        # Create and add nodes
        node1 = ExecutionNode(name="test_node1", node_type=NodeType.AGENT)
        node2 = ExecutionNode(name="test_node2", node_type=NodeType.AGENT)
        
        # Add nodes
        result1 = await execution_tree.add_node(tree_id, node1)
        result2 = await execution_tree.add_node(tree_id, node2)
        
        assert result1 is True
        assert result2 is True
        
        # Get tree snapshot
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        assert snapshot is not None
        assert len(snapshot.nodes) == 3  # 2 + root node
        
        # Update node status
        update_result = await execution_tree.update_node_status(
            tree_id, node1.id, ExecutionStatus.COMPLETED
        )
        assert update_result is True
        
        # Verify status update
        updated_node = await execution_tree.get_node(tree_id, node1.id)
        assert updated_node.status == ExecutionStatus.COMPLETED
        
        # Get metrics
        metrics = await execution_tree.get_tree_metrics(tree_id)
        assert isinstance(metrics, dict)
        assert metrics.get("total_nodes", 0) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])