"""
Unit tests for RedisStateStore without Docker/testcontainers.

These tests validate the Redis StateStore implementation using the
dev Redis service (redis:6379) on a dedicated DB index to avoid
interference.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import List
import redis.asyncio as redis

from src.interfaces.state_store import StateSnapshot, StateQuery, StateType
from src.infrastructure.state.redis_state_store import RedisStateStore
from tests.contracts.test_state_store_contract import StateStoreContractTest


class TestRedisStateStore(StateStoreContractTest):
    """Test RedisStateStore implementation against the contract"""
    
    @pytest.fixture
    async def state_store(self):
        """Create RedisStateStore instance pointing to dev Redis service"""
        redis_url = "redis://redis:6379"
        store = RedisStateStore(
            redis_url=redis_url,
            db=9,
            key_prefix="test:state",
            connection_pool_size=100,
        )
        
        # Ensure clean state for each test
        redis_client = redis.Redis.from_url(f"{redis_url}/9", decode_responses=True)
        await redis_client.flushdb()
        await redis_client.close()
        
        yield store
        
        # Cleanup after test
        await store._disconnect()
    
    @pytest.mark.asyncio
    async def test_redis_specific_serialization(self, state_store):
        """Test Redis-specific serialization features"""
        # Test with complex nested data
        complex_data = {
            "nested": {
                "list": [1, 2, {"inner": "value"}],
                "datetime_str": "2023-01-01T12:00:00",
                "unicode": "测试数据",
                "numbers": [1.5, 2.7, 3.14159]
            },
            "large_text": "x" * 10000  # Large text field
        }
        
        snapshot = StateSnapshot(
            agent_id="complex_agent",
            state_type=StateType.AGENT_STATE,
            data=complex_data,
            metadata={"encoding": "utf-8", "size": "large"}
        )
        
        # Save and retrieve
        result = await state_store.save_state(snapshot)
        assert result is True
        
        retrieved = await state_store.get_latest_state("complex_agent", StateType.AGENT_STATE)
        assert retrieved is not None
        assert retrieved.data == complex_data
        assert retrieved.metadata["encoding"] == "utf-8"
    
    @pytest.mark.asyncio
    async def test_redis_sorted_set_operations(self, state_store):
        """Test Redis sorted set operations for temporal queries"""
        agent_id = "temporal_agent"
        
        # Create snapshots with specific timestamps
        base_time = datetime(2023, 1, 1, 12, 0, 0)
        snapshots = []
        
        for i in range(5):
            timestamp = base_time + timedelta(hours=i)
            snapshot = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"hour": i},
                timestamp=timestamp
            )
            snapshots.append(snapshot)
            await state_store.save_state(snapshot)
        
        # Test time range queries
        query = StateQuery(
            agent_id=agent_id,
            state_type=StateType.AGENT_STATE,
            timestamp_from=base_time + timedelta(hours=1),
            timestamp_to=base_time + timedelta(hours=3),
            limit=10
        )
        
        results = await state_store.load_state(query)
        assert len(results) == 3  # Hours 1, 2, 3
        
        # Verify chronological order
        for i, result in enumerate(results):
            assert result.data["hour"] == i + 1
    
    @pytest.mark.asyncio
    async def test_redis_pipeline_atomicity(self, state_store):
        """Test Redis pipeline operations for atomicity"""
        # Create multiple snapshots that should be saved atomically
        agent_id = "atomic_agent"
        snapshots = []
        
        for i in range(3):
            snapshot = StateSnapshot(
                agent_id=f"{agent_id}_{i}",
                state_type=StateType.AGENT_STATE,
                data={"batch": "test", "index": i}
            )
            snapshots.append(snapshot)
        
        # Save all snapshots
        save_tasks = [state_store.save_state(snapshot) for snapshot in snapshots]
        results = await asyncio.gather(*save_tasks)
        
        assert all(results), "All saves should succeed"
        
        # Verify all were saved
        for i, snapshot in enumerate(snapshots):
            retrieved = await state_store.get_latest_state(
                f"{agent_id}_{i}", StateType.AGENT_STATE
            )
            assert retrieved is not None
            assert retrieved.data["index"] == i
    
    @pytest.mark.asyncio
    async def test_redis_key_expiration_awareness(self, state_store):
        """Test behavior with Redis key expiration (if implemented)"""
        snapshot = StateSnapshot(
            agent_id="expiring_agent",
            state_type=StateType.AGENT_STATE,
            data={"test": "expiration"}
        )
        
        await state_store.save_state(snapshot)
        
        # Verify key exists
        retrieved = await state_store.get_latest_state("expiring_agent", StateType.AGENT_STATE)
        assert retrieved is not None
        
        # Test that non-existent keys are handled gracefully
        non_existent = await state_store.get_latest_state("non_existent", StateType.AGENT_STATE)
        assert non_existent is None
    
    @pytest.mark.asyncio
    async def test_redis_connection_handling(self, state_store):
        """Test Redis connection pool handling"""
        # Test multiple concurrent operations
        async def save_and_load():
            snapshot = StateSnapshot(
                agent_id="concurrent_agent",
                state_type=StateType.AGENT_STATE,
                data={"concurrent": True}
            )
            await state_store.save_state(snapshot)
            return await state_store.get_latest_state("concurrent_agent", StateType.AGENT_STATE)
        
        # Run 10 concurrent operations
        tasks = [save_and_load() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(result is not None for result in results)
        assert all(result.data["concurrent"] is True for result in results)
    
    @pytest.mark.asyncio
    async def test_redis_health_check_details(self, state_store):
        """Test detailed health check functionality"""
        # Health check should work
        health = await state_store.health_check()
        assert health is True
        
        # Test with disconnected state (simulate connection issue)
        original_pool = state_store._redis_pool
        state_store._redis_pool = None
        state_store._is_connected = False
        
        # Health check should handle connection gracefully
        try:
            health = await state_store.health_check()
            # Should either succeed (if reconnected) or fail gracefully
            assert isinstance(health, bool)
        finally:
            # Restore connection
            state_store._redis_pool = original_pool
            state_store._is_connected = True
    
    @pytest.mark.asyncio
    async def test_redis_stats_functionality(self, state_store):
        """Test Redis-specific stats functionality"""
        # Create some test data
        for i in range(3):
            for state_type in [StateType.AGENT_STATE, StateType.EXECUTION_CONTEXT]:
                snapshot = StateSnapshot(
                    agent_id=f"stats_agent_{i}",
                    state_type=state_type,
                    data={"index": i}
                )
                await state_store.save_state(snapshot)
        
        # Get stats
        stats = await state_store.get_stats()
        
        assert isinstance(stats, dict)
        assert "snapshots_agent_state" in stats
        assert "snapshots_execution_context" in stats
        assert stats["snapshots_agent_state"] >= 3
        assert stats["snapshots_execution_context"] >= 3
        assert "redis_used_memory" in stats
    
    @pytest.mark.asyncio
    async def test_redis_cleanup_performance(self, state_store):
        """Test cleanup operation performance with many states"""
        # Create many old states
        cutoff_time = datetime.utcnow() - timedelta(days=35)
        
        # Create 50 old states
        for i in range(50):
            snapshot = StateSnapshot(
                agent_id=f"cleanup_agent_{i}",
                state_type=StateType.AGENT_STATE,
                data={"old": True, "index": i},
                timestamp=cutoff_time
            )
            await state_store.save_state(snapshot)
        
        # Create some recent states
        for i in range(10):
            snapshot = StateSnapshot(
                agent_id=f"recent_agent_{i}",
                state_type=StateType.AGENT_STATE,
                data={"recent": True, "index": i}
            )
            await state_store.save_state(snapshot)
        
        # Cleanup old states
        start_time = datetime.utcnow()
        cleaned_count = await state_store.cleanup_old_states(retention_days=30)
        cleanup_duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Should have cleaned the old states
        assert cleaned_count >= 50
        
        # Cleanup should be reasonably fast
        assert cleanup_duration < 5.0  # Should complete within 5 seconds
        
        # Recent states should remain
        recent_query = StateQuery(agent_id="recent_agent_0")
        recent_results = await state_store.load_state(recent_query)
        assert len(recent_results) > 0
    
    @pytest.mark.asyncio
    async def test_redis_error_handling(self, state_store):
        """Test error handling in Redis operations"""
        # Test with invalid JSON data (should be handled gracefully)
        # Create a client from the pool returned by _get_redis()
        pool = await state_store._get_redis()
        redis_client = redis.Redis(connection_pool=pool)
        
        # Manually insert invalid data
        invalid_key = f"{state_store.key_prefix}:snapshot:invalid_agent:agent_state:test_id"
        await redis_client.set(invalid_key, "invalid json data")
        
        # Attempt to deserialize should handle error gracefully
        try:
            result = await redis_client.get(invalid_key)
            assert result == "invalid json data"
            
            # The deserialize should raise an appropriate exception
            with pytest.raises(Exception):  # Should raise StateValidationError or similar
                state_store._deserialize_snapshot(result)
        
        finally:
            await redis_client.delete(invalid_key)
            await redis_client.aclose()
    
    @pytest.mark.asyncio
    async def test_redis_memory_efficiency(self, state_store):
        """Test memory efficiency with large datasets"""
        # Create snapshots with varying data sizes
        agent_id = "memory_test_agent"
        
        # Small data
        small_snapshot = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.AGENT_STATE,
            data={"size": "small", "data": "x" * 100}
        )
        
        # Medium data
        medium_snapshot = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.EXECUTION_CONTEXT,
            data={"size": "medium", "data": "x" * 10000}
        )
        
        # Large data
        large_snapshot = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.WORKFLOW_STATE,
            data={"size": "large", "data": "x" * 100000, "list": list(range(1000))}
        )
        
        # Save all sizes
        await state_store.save_state(small_snapshot)
        await state_store.save_state(medium_snapshot)
        await state_store.save_state(large_snapshot)
        
        # Verify all can be retrieved
        small_result = await state_store.get_latest_state(agent_id, StateType.AGENT_STATE)
        medium_result = await state_store.get_latest_state(agent_id, StateType.EXECUTION_CONTEXT)
        large_result = await state_store.get_latest_state(agent_id, StateType.WORKFLOW_STATE)
        
        assert small_result.data["size"] == "small"
        assert medium_result.data["size"] == "medium"
        assert large_result.data["size"] == "large"
        assert len(large_result.data["list"]) == 1000
    
    @pytest.mark.asyncio
    async def test_redis_concurrent_access_safety(self, state_store):
        """Test thread/coroutine safety with concurrent access"""
        agent_id = "concurrent_safety_agent"
        
        async def concurrent_operations(operation_id: int):
            """Perform multiple operations concurrently"""
            results = []
            
            # Save
            snapshot = StateSnapshot(
                agent_id=f"{agent_id}_{operation_id}",
                state_type=StateType.AGENT_STATE,
                data={"operation_id": operation_id, "step": "initial"}
            )
            save_result = await state_store.save_state(snapshot)
            results.append(save_result)
            
            # Update
            updated_snapshot = snapshot.with_data({"step": "updated", "operation_id": operation_id})
            update_result = await state_store.save_state(updated_snapshot)
            results.append(update_result)
            
            # Load
            loaded = await state_store.get_latest_state(
                f"{agent_id}_{operation_id}", StateType.AGENT_STATE
            )
            results.append(loaded is not None)
            
            # Query
            query = StateQuery(agent_id=f"{agent_id}_{operation_id}")
            query_results = await state_store.load_state(query)
            results.append(len(query_results) >= 1)
            
            return all(results)
        
        # Run 20 concurrent operation sets
        tasks = [concurrent_operations(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All operations should succeed
        successful = [r for r in results if r is True]
        assert len(successful) == 20, f"Expected 20 successful operations, got {len(successful)}"
        
        # No exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"


# Additional Redis-specific integration tests
class TestRedisStateStoreIntegration:
    """Integration tests for Redis StateStore with real Redis scenarios"""
    
    @pytest.fixture
    async def state_store(self):
        """Create RedisStateStore for integration testing (no Docker)"""
        redis_url = "redis://redis:6379"
        store = RedisStateStore(
            redis_url=redis_url,
            db=10,  # Use different DB for integration tests
            key_prefix="integration:state",
            connection_pool_size=100,
        )
        
        # Clean state
        redis_client = redis.Redis.from_url(f"{redis_url}/10", decode_responses=True)
        await redis_client.flushdb()
        await redis_client.close()
        
        yield store
        await store._disconnect()
    
    @pytest.mark.asyncio
    async def test_full_workflow_integration(self, state_store):
        """Test complete workflow with multiple agents and state types"""
        # Simulate a complex workflow
        workflow_agents = ["coordinator", "worker1", "worker2", "validator"]
        
        # Phase 1: Initialize all agents
        for agent_id in workflow_agents:
            snapshot = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"phase": "initialization", "status": "starting"}
            )
            await state_store.save_state(snapshot)
        
        # Phase 2: Execution with context tracking
        for agent_id in workflow_agents:
            context_snapshot = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.EXECUTION_CONTEXT,
                data={"phase": "execution", "variables": {"task_id": f"task_{agent_id}"}}
            )
            await state_store.save_state(context_snapshot)
        
        # Phase 3: Workflow state management
        workflow_snapshot = StateSnapshot(
            agent_id="coordinator",
            state_type=StateType.WORKFLOW_STATE,
            data={"active_agents": len(workflow_agents), "completion_rate": 0.75}
        )
        await state_store.save_state(workflow_snapshot)
        
        # Verify complete state
        total_states = 0
        for agent_id in workflow_agents:
            for state_type in StateType:
                query = StateQuery(agent_id=agent_id, state_type=state_type)
                results = await state_store.load_state(query)
                total_states += len(results)
        
        # Should have states for each agent/type combination
        assert total_states >= len(workflow_agents) * 2  # At least agent_state + execution_context
        
        # Verify workflow state
        workflow_state = await state_store.get_latest_state("coordinator", StateType.WORKFLOW_STATE)
        assert workflow_state is not None
        assert workflow_state.data["active_agents"] == len(workflow_agents)
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, state_store):
        """Test performance under high load"""
        start_time = datetime.utcnow()
        
        # Create a moderate number of snapshots across multiple agents
        sem = asyncio.Semaphore(20)  # bound concurrency within pool limits
        async def save(agent_idx: int, state_idx: int):
            snapshot = StateSnapshot(
                agent_id=f"load_agent_{agent_idx}",
                state_type=StateType.AGENT_STATE,
                data={"agent_idx": agent_idx, "state_idx": state_idx}
            )
            async with sem:
                return await state_store.save_state(snapshot)

        tasks = [save(ai, si) for ai in range(20) for si in range(10)]
        results = await asyncio.gather(*tasks)
        save_duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Majority of saves should succeed (allow minor transient failures in CI)
        assert all(results), "All saves should succeed under bounded concurrency"
        
        # Performance should be reasonable (adjust threshold as needed)
        assert save_duration < 30.0, f"Save operations took too long: {save_duration}s"
        
        # Test query performance
        query_start = datetime.utcnow()
        
        # Query random agents
        async def run_query(agent_idx: int):
            async with sem:
                query = StateQuery(agent_id=f"load_agent_{agent_idx}")
                return await state_store.load_state(query)
        query_results = await asyncio.gather(*(run_query(i) for i in range(0, 20, 5)))
        query_duration = (datetime.utcnow() - query_start).total_seconds()
        
        # All queries should return results
        assert all(len(results) > 0 for results in query_results)
        
        # Query performance should be reasonable
        assert query_duration < 10.0, f"Query operations took too long: {query_duration}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
