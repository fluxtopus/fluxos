"""
Contract tests for StateStore interface implementations

These tests ensure all StateStore implementations conform to the interface contract
and behave consistently across different backends.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Type, List
from unittest.mock import AsyncMock

from src.interfaces.state_store import (
    StateStoreInterface, StateSnapshot, StateQuery, StateType,
    StateNotFoundError, StateValidationError, StateStoreConnectionError
)


class StateStoreContractTest:
    """
    Base contract test class for StateStore implementations
    All StateStore implementations must pass these tests
    """
    
    @pytest.fixture
    def state_store(self) -> StateStoreInterface:
        """Override this fixture in implementation-specific test classes"""
        raise NotImplementedError("Subclasses must provide state_store fixture")
    
    @pytest.fixture
    def sample_snapshot(self) -> StateSnapshot:
        """Sample state snapshot for testing"""
        return StateSnapshot(
            agent_id="test_agent_123",
            state_type=StateType.AGENT_STATE,
            data={"status": "running", "progress": 50},
            metadata={"created_by": "test_suite"}
        )
    
    @pytest.fixture
    def sample_snapshots(self) -> List[StateSnapshot]:
        """Multiple sample snapshots for batch testing"""
        return [
            StateSnapshot(
                agent_id="agent_1",
                state_type=StateType.AGENT_STATE,
                data={"status": "running", "progress": 25}
            ),
            StateSnapshot(
                agent_id="agent_1",
                state_type=StateType.EXECUTION_CONTEXT,
                data={"context": "main", "variables": {"x": 10}}
            ),
            StateSnapshot(
                agent_id="agent_2",
                state_type=StateType.AGENT_STATE,
                data={"status": "completed", "progress": 100}
            )
        ]
    
    @pytest.mark.asyncio
    async def test_save_and_load_single_state(self, state_store, sample_snapshot):
        """Test basic save and load operations"""
        # Save state
        result = await state_store.save_state(sample_snapshot)
        assert result is True, "save_state should return True on success"
        
        # Load state by agent ID and type
        query = StateQuery(
            agent_id=sample_snapshot.agent_id,
            state_type=sample_snapshot.state_type
        )
        snapshots = await state_store.load_state(query)
        
        assert len(snapshots) >= 1, "Should find at least one snapshot"
        found_snapshot = snapshots[0]
        assert found_snapshot.agent_id == sample_snapshot.agent_id
        assert found_snapshot.state_type == sample_snapshot.state_type
        assert found_snapshot.data == sample_snapshot.data
        assert found_snapshot.metadata == sample_snapshot.metadata
    
    @pytest.mark.asyncio
    async def test_get_latest_state(self, state_store, sample_snapshot):
        """Test getting the most recent state"""
        # Save initial state
        await state_store.save_state(sample_snapshot)
        
        # Save updated state
        updated_snapshot = sample_snapshot.with_data({"status": "completed", "progress": 100})
        await state_store.save_state(updated_snapshot)
        
        # Get latest state
        latest = await state_store.get_latest_state(
            sample_snapshot.agent_id, 
            sample_snapshot.state_type
        )
        
        assert latest is not None, "Should find latest state"
        assert latest.data["status"] == "completed"
        assert latest.data["progress"] == 100
        assert latest.version == updated_snapshot.version
    
    @pytest.mark.asyncio
    async def test_state_history(self, state_store, sample_snapshot):
        """Test state history retrieval"""
        agent_id = sample_snapshot.agent_id
        
        # Save multiple states with small delays
        snapshots = []
        for i in range(3):
            snapshot = sample_snapshot.with_data({"iteration": i, "progress": i * 30})
            await state_store.save_state(snapshot)
            snapshots.append(snapshot)
            await asyncio.sleep(0.01)  # Small delay to ensure different timestamps
        
        # Get history
        history = await state_store.get_state_history(agent_id, limit=10)
        
        assert len(history) == 3, "Should have 3 historical states"
        
        # Verify chronological order
        for i in range(len(history) - 1):
            assert history[i].timestamp <= history[i + 1].timestamp
    
    @pytest.mark.asyncio
    async def test_delete_state(self, state_store, sample_snapshots):
        """Test state deletion"""
        # Save multiple states
        for snapshot in sample_snapshots:
            await state_store.save_state(snapshot)
        
        # Delete all states for agent_1
        result = await state_store.delete_state("agent_1")
        assert result is True, "delete_state should return True on success"
        
        # Verify deletion
        query = StateQuery(agent_id="agent_1")
        remaining = await state_store.load_state(query)
        assert len(remaining) == 0, "All states for agent_1 should be deleted"
        
        # Verify agent_2 states still exist
        query = StateQuery(agent_id="agent_2")
        agent2_states = await state_store.load_state(query)
        assert len(agent2_states) > 0, "agent_2 states should still exist"
    
    @pytest.mark.asyncio
    async def test_delete_state_by_type(self, state_store, sample_snapshots):
        """Test selective deletion by state type"""
        # Save multiple states
        for snapshot in sample_snapshots:
            await state_store.save_state(snapshot)
        
        # Delete only AGENT_STATE for agent_1
        result = await state_store.delete_state("agent_1", StateType.AGENT_STATE)
        assert result is True
        
        # Verify selective deletion
        query = StateQuery(agent_id="agent_1", state_type=StateType.AGENT_STATE)
        agent_states = await state_store.load_state(query)
        assert len(agent_states) == 0, "AGENT_STATE should be deleted"
        
        query = StateQuery(agent_id="agent_1", state_type=StateType.EXECUTION_CONTEXT)
        context_states = await state_store.load_state(query)
        assert len(context_states) > 0, "EXECUTION_CONTEXT should still exist"
    
    @pytest.mark.asyncio
    async def test_query_filters(self, state_store, sample_snapshots):
        """Test various query filters"""
        # Save test data
        for snapshot in sample_snapshots:
            await state_store.save_state(snapshot)
        
        # Test filter by state type
        query = StateQuery(state_type=StateType.AGENT_STATE)
        agent_states = await state_store.load_state(query)
        for state in agent_states:
            assert state.state_type == StateType.AGENT_STATE
        
        # Test filter by agent ID
        query = StateQuery(agent_id="agent_1")
        agent1_states = await state_store.load_state(query)
        for state in agent1_states:
            assert state.agent_id == "agent_1"
        
        # Test limit and offset
        query = StateQuery(limit=1, offset=0)
        limited_states = await state_store.load_state(query)
        assert len(limited_states) <= 1
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, state_store, sample_snapshot):
        """Test concurrent save/load operations"""
        agent_id = sample_snapshot.agent_id
        
        async def save_states():
            tasks = []
            for i in range(10):
                snapshot = sample_snapshot.with_data({"iteration": i})
                tasks.append(state_store.save_state(snapshot))
            return await asyncio.gather(*tasks)
        
        async def load_states():
            tasks = []
            for _ in range(5):
                query = StateQuery(agent_id=agent_id)
                tasks.append(state_store.load_state(query))
            return await asyncio.gather(*tasks)
        
        # Run concurrent operations
        save_results, load_results = await asyncio.gather(
            save_states(),
            load_states()
        )
        
        # All saves should succeed
        assert all(save_results), "All save operations should succeed"
        
        # All loads should succeed (though may return different counts)
        assert all(isinstance(result, list) for result in load_results)
    
    @pytest.mark.asyncio
    async def test_cleanup_old_states(self, state_store, sample_snapshot):
        """Test cleanup of old state snapshots"""
        # Save a state with old timestamp
        old_snapshot = StateSnapshot(
            agent_id="old_agent",
            state_type=StateType.AGENT_STATE,
            data={"status": "old"},
            timestamp=datetime.utcnow() - timedelta(days=35)
        )
        await state_store.save_state(old_snapshot)
        
        # Save a recent state
        await state_store.save_state(sample_snapshot)
        
        # Cleanup states older than 30 days
        cleaned_count = await state_store.cleanup_old_states(retention_days=30)
        
        # Should have cleaned at least the old state
        assert cleaned_count >= 1, "Should clean up old states"
        
        # Recent state should still exist
        query = StateQuery(agent_id=sample_snapshot.agent_id)
        remaining = await state_store.load_state(query)
        assert len(remaining) > 0, "Recent states should remain"
    
    @pytest.mark.asyncio
    async def test_health_check(self, state_store):
        """Test health check functionality"""
        health = await state_store.health_check()
        assert isinstance(health, bool), "health_check should return a boolean"
        assert health is True, "StateStore should be healthy in test environment"
    
    @pytest.mark.asyncio
    async def test_invalid_operations(self, state_store):
        """Test error handling for invalid operations"""
        # Test loading non-existent state
        query = StateQuery(agent_id="non_existent_agent")
        snapshots = await state_store.load_state(query)
        assert len(snapshots) == 0, "Should return empty list for non-existent agent"
        
        # Test getting latest state for non-existent agent
        latest = await state_store.get_latest_state("non_existent", StateType.AGENT_STATE)
        assert latest is None, "Should return None for non-existent agent"
        
        # Test deleting non-existent state
        result = await state_store.delete_state("non_existent_agent")
        assert result is True, "delete_state should succeed even for non-existent agent"
    
    @pytest.mark.asyncio
    async def test_state_snapshot_immutability(self, state_store, sample_snapshot):
        """Test that state snapshots maintain immutability"""
        # Save original snapshot
        await state_store.save_state(sample_snapshot)
        
        # Create modified version
        modified_snapshot = sample_snapshot.with_data({"new_field": "new_value"})
        
        # Verify original is unchanged
        assert "new_field" not in sample_snapshot.data
        assert modified_snapshot.parent_snapshot_id == sample_snapshot.id
        assert modified_snapshot.version == sample_snapshot.version + 1
        
        # Save modified version
        await state_store.save_state(modified_snapshot)
        
        # Both should be retrievable
        query = StateQuery(agent_id=sample_snapshot.agent_id)
        snapshots = await state_store.load_state(query)
        assert len(snapshots) >= 2, "Both versions should be stored"
    
    @pytest.mark.asyncio
    async def test_large_state_data(self, state_store):
        """Test handling of large state data"""
        large_data = {"large_list": list(range(10000))}
        large_snapshot = StateSnapshot(
            agent_id="large_agent",
            state_type=StateType.AGENT_STATE,
            data=large_data
        )
        
        # Should handle large data
        result = await state_store.save_state(large_snapshot)
        assert result is True, "Should handle large state data"
        
        # Should retrieve large data correctly
        latest = await state_store.get_latest_state("large_agent", StateType.AGENT_STATE)
        assert latest is not None
        assert len(latest.data["large_list"]) == 10000
    
    def test_state_snapshot_validation(self):
        """Test StateSnapshot validation"""
        # Valid snapshot should not raise
        valid_snapshot = StateSnapshot(agent_id="valid_agent")
        assert valid_snapshot.agent_id == "valid_agent"
        
        # Invalid snapshot should raise
        with pytest.raises(ValueError):
            StateSnapshot(agent_id="")  # Empty agent_id should fail
    
    def test_state_query_defaults(self):
        """Test StateQuery default values"""
        query = StateQuery()
        assert query.limit == 100
        assert query.offset == 0
        assert query.agent_id is None
        assert query.state_type is None
        assert len(query.metadata_filter) == 0


# Mock implementation for basic testing
class MockStateStore(StateStoreInterface):
    """Mock implementation for testing interface contract"""
    
    def __init__(self):
        self.states = {}
        self.is_healthy = True
    
    async def save_state(self, snapshot: StateSnapshot) -> bool:
        key = f"{snapshot.agent_id}:{snapshot.state_type.value}:{snapshot.id}"
        self.states[key] = snapshot
        return True
    
    async def load_state(self, query: StateQuery) -> List[StateSnapshot]:
        results = []
        for snapshot in self.states.values():
            # Filter by agent id(s)
            if query.agent_id and snapshot.agent_id != query.agent_id:
                continue
            if getattr(query, "agent_ids", None):
                if snapshot.agent_id not in query.agent_ids:
                    continue
            # Filter by state type(s)
            if query.state_type and snapshot.state_type != query.state_type:
                continue
            if getattr(query, "state_types", None):
                if snapshot.state_type not in query.state_types:
                    continue
            # Filter by timestamp range
            if query.timestamp_from and snapshot.timestamp < query.timestamp_from:
                continue
            if query.timestamp_to and snapshot.timestamp > query.timestamp_to:
                continue
            # Filter by metadata
            if query.metadata_filter:
                ok = True
                for k, v in query.metadata_filter.items():
                    if snapshot.metadata.get(k) != v:
                        ok = False
                        break
                if not ok:
                    continue
            results.append(snapshot)
        
        # Apply offset and limit
        start = query.offset
        end = start + query.limit
        return sorted(results, key=lambda x: x.timestamp)[start:end]
    
    async def get_latest_state(self, agent_id: str, state_type: StateType) -> StateSnapshot:
        snapshots = [s for s in self.states.values() 
                    if s.agent_id == agent_id and s.state_type == state_type]
        if not snapshots:
            return None
        return max(snapshots, key=lambda x: x.timestamp)
    
    async def delete_state(self, agent_id: str, state_type: StateType = None) -> bool:
        to_delete = []
        for key, snapshot in self.states.items():
            if snapshot.agent_id == agent_id:
                if state_type is None or snapshot.state_type == state_type:
                    to_delete.append(key)
        
        for key in to_delete:
            del self.states[key]
        return True
    
    async def get_state_history(self, agent_id: str, limit: int = 100) -> List[StateSnapshot]:
        snapshots = [s for s in self.states.values() if s.agent_id == agent_id]
        return sorted(snapshots, key=lambda x: x.timestamp)[:limit]
    
    async def cleanup_old_states(self, retention_days: int = 30) -> int:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        to_delete = []
        for key, snapshot in self.states.items():
            if snapshot.timestamp < cutoff:
                to_delete.append(key)
        
        for key in to_delete:
            del self.states[key]
        return len(to_delete)
    
    async def health_check(self) -> bool:
        return self.is_healthy


class TestMockStateStore(StateStoreContractTest):
    """Test the mock implementation against the contract"""
    
    @pytest.fixture
    def state_store(self):
        return MockStateStore()
