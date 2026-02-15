"""
Property-based tests for StateStore interface using Hypothesis

These tests validate the StateStore interface with property-based testing
to discover edge cases and ensure robust implementations.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, assume, settings, HealthCheck
import string
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, Bundle

from src.interfaces.state_store import (
    StateStoreInterface, StateSnapshot, StateQuery, StateType
)
from tests.contracts.test_state_store_contract import MockStateStore


# Hypothesis strategies for generating test data
@st.composite
def state_snapshot_strategy(draw):
    """Generate valid StateSnapshot instances"""
    allowed_agent_chars = string.ascii_letters + string.digits + "_-"
    agent_id = draw(st.text(min_size=1, max_size=50, alphabet=st.sampled_from(list(allowed_agent_chars))))
    state_type = draw(st.sampled_from(StateType))
    
    # Generate data dictionary
    allowed_key_chars = string.ascii_letters + string.digits + "_"
    data_keys = draw(st.lists(st.text(min_size=1, max_size=20, alphabet=st.sampled_from(list(allowed_key_chars))), min_size=0, max_size=10))
    data_values = draw(st.lists(st.one_of(
        st.text(max_size=100),
        st.integers(min_value=-1000, max_value=1000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.none()
    ), min_size=len(data_keys), max_size=len(data_keys)))
    
    data = dict(zip(data_keys, data_values))
    
    # Generate metadata
    metadata_keys = draw(st.lists(st.text(min_size=1, max_size=20, alphabet=st.sampled_from(list(allowed_key_chars))), min_size=0, max_size=5))
    metadata_values = draw(st.lists(st.text(max_size=50), min_size=len(metadata_keys), max_size=len(metadata_keys)))
    metadata = dict(zip(metadata_keys, metadata_values))
    
    return StateSnapshot(
        agent_id=agent_id,
        state_type=state_type,
        data=data,
        metadata=metadata
    )


@st.composite
def state_query_strategy(draw):
    """Generate valid StateQuery instances"""
    agent_id = draw(st.one_of(st.none(), st.text(min_size=1, max_size=50)))
    state_type = draw(st.one_of(st.none(), st.sampled_from(StateType)))
    
    # Generate optional datetime range
    timestamp_from = draw(st.one_of(st.none(), st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1)
    )))
    
    timestamp_to = draw(st.one_of(st.none(), st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1)
    )))
    
    # Ensure from <= to if both are set
    if timestamp_from and timestamp_to and timestamp_from > timestamp_to:
        timestamp_from, timestamp_to = timestamp_to, timestamp_from
    
    limit = draw(st.integers(min_value=1, max_value=1000))
    offset = draw(st.integers(min_value=0, max_value=1000))
    
    return StateQuery(
        agent_id=agent_id,
        state_type=state_type,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        limit=limit,
        offset=offset
    )


class StateStoreStateMachine(RuleBasedStateMachine):
    """
    Stateful property-based testing for StateStore
    This validates that operations maintain consistency across sequences of actions
    """
    
    def __init__(self):
        super().__init__()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.state_store = MockStateStore()
        self.saved_snapshots = []

    def teardown(self):
        """Ensure event loop cleanup after each state machine run."""
        try:
            super().teardown()
        finally:
            if self._loop.is_running():
                self._loop.stop()
            self._loop.close()
            asyncio.set_event_loop(None)

    def _run(self, coro):
        """Run async coroutine using the dedicated loop."""
        return self._loop.run_until_complete(coro)
    
    snapshots = Bundle('snapshots')
    
    @initialize()
    def setup(self):
        """Initialize the state machine"""
        pass
    
    @rule(target=snapshots, snapshot=state_snapshot_strategy())
    def save_snapshot(self, snapshot):
        """Save a state snapshot"""
        result = self._run(self.state_store.save_state(snapshot))
        assert result is True, "save_state should always succeed for valid snapshots"
        self.saved_snapshots.append(snapshot)
        return snapshot
    
    @rule(snapshot=snapshots)
    def load_snapshot_by_agent(self, snapshot):
        """Load snapshot by agent ID"""
        query = StateQuery(agent_id=snapshot.agent_id, state_type=snapshot.state_type)
        results = self._run(self.state_store.load_state(query))
        
        # Should find at least the saved snapshot
        found_snapshot = None
        for result in results:
            if result.id == snapshot.id:
                found_snapshot = result
                break
        
        assert found_snapshot is not None, "Should find previously saved snapshot"
        assert found_snapshot.agent_id == snapshot.agent_id
        assert found_snapshot.state_type == snapshot.state_type
        assert found_snapshot.data == snapshot.data
    
    @rule(snapshot=snapshots)
    def get_latest_state(self, snapshot):
        """Get latest state for agent"""
        latest = self._run(self.state_store.get_latest_state(snapshot.agent_id, snapshot.state_type))
        
        if latest:
            assert latest.agent_id == snapshot.agent_id
            assert latest.state_type == snapshot.state_type
    
    @rule(query=state_query_strategy())
    def query_states(self, query):
        """Query states with various filters"""
        results = self._run(self.state_store.load_state(query))
        
        # Results should respect query constraints
        assert len(results) <= query.limit, "Results should not exceed limit"
        
        for result in results:
            if query.agent_id:
                assert result.agent_id == query.agent_id
            if query.state_type:
                assert result.state_type == query.state_type
            if query.timestamp_from:
                assert result.timestamp >= query.timestamp_from
            if query.timestamp_to:
                assert result.timestamp <= query.timestamp_to
    
    @rule()
    def health_check_always_works(self):
        """Health check should always work"""
        health = self._run(self.state_store.health_check())
        assert isinstance(health, bool)


# Run the state machine
TestStateStoreStateMachine = StateStoreStateMachine.TestCase


class TestStateStoreProperties:
    """Property-based tests for StateStore interface"""
    
    @pytest.fixture
    def state_store(self):
        return MockStateStore()
    
    @given(snapshot=state_snapshot_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_snapshot_immutability_property(self, snapshot):
        """Test that StateSnapshot maintains immutability properties"""
        original_data = snapshot.data.copy()
        original_metadata = snapshot.metadata.copy()
        
        # Create modified versions
        new_snapshot_data = snapshot.with_data({"new_field": "value"})
        new_snapshot_metadata = snapshot.with_metadata({"new_meta": "meta_value"})
        
        # Original should be unchanged
        assert snapshot.data == original_data
        assert snapshot.metadata == original_metadata
        
        # New snapshots should have incremented versions
        assert new_snapshot_data.version == snapshot.version + 1
        assert new_snapshot_metadata.version == snapshot.version + 1
        
        # Parent references should be set
        assert new_snapshot_data.parent_snapshot_id == snapshot.id
        assert new_snapshot_metadata.parent_snapshot_id == snapshot.id
    
    @given(snapshots=st.lists(state_snapshot_strategy(), min_size=1, max_size=10))
    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_save_load_consistency(self, snapshots):
        """Test that saved snapshots can always be loaded consistently"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        # Save all snapshots
        for snapshot in snapshots:
            result = await state_store.save_state(snapshot)
            assert result is True
        
        # Load each snapshot and verify data integrity
        for snapshot in snapshots:
            query = StateQuery(agent_id=snapshot.agent_id, state_type=snapshot.state_type)
            results = await state_store.load_state(query)
            
            # Find our specific snapshot
            found = any(r.id == snapshot.id for r in results)
            assert found, f"Snapshot {snapshot.id} should be found after saving"
    
    @given(agent_ids=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=5, unique=True))
    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_delete_isolation_property(self, agent_ids):
        """Test that deleting states for one agent doesn't affect others"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        assume(len(agent_ids) >= 2)
        
        # Create snapshots for different agents
        snapshots_by_agent = {}
        for agent_id in agent_ids:
            snapshot = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"test": f"data_for_{agent_id}"}
            )
            await state_store.save_state(snapshot)
            snapshots_by_agent[agent_id] = snapshot
        
        # Delete states for first agent
        target_agent = agent_ids[0]
        result = await state_store.delete_state(target_agent)
        assert result is True
        
        # Verify target agent's states are gone
        query = StateQuery(agent_id=target_agent)
        target_results = await state_store.load_state(query)
        assert len(target_results) == 0
        
        # Verify other agents' states still exist
        for other_agent in agent_ids[1:]:
            query = StateQuery(agent_id=other_agent)
            other_results = await state_store.load_state(query)
            assert len(other_results) > 0, f"Agent {other_agent} states should still exist"
    
    @given(
        agent_id=st.text(min_size=1, max_size=30),
        state_count=st.integers(min_value=1, max_value=20)
    )
    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_state_history_ordering(self, agent_id, state_count):
        """Test that state history maintains chronological ordering"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        snapshots = []
        
        # Create multiple states with small delays
        for i in range(state_count):
            snapshot = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"iteration": i, "timestamp": datetime.utcnow().isoformat()}
            )
            await state_store.save_state(snapshot)
            snapshots.append(snapshot)
            await asyncio.sleep(0.001)  # Tiny delay to ensure different timestamps
        
        # Get history
        history = await state_store.get_state_history(agent_id, limit=state_count + 10)
        
        # Verify chronological ordering
        assert len(history) == state_count
        for i in range(len(history) - 1):
            assert history[i].timestamp <= history[i + 1].timestamp, "History should be chronologically ordered"
    
    @given(
        queries=st.lists(state_query_strategy(), min_size=1, max_size=5),
        snapshots=st.lists(state_snapshot_strategy(), min_size=1, max_size=10)
    )
    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=15000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_query_consistency_property(self, queries, snapshots):
        """Test that queries return consistent results"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        # Save all snapshots
        for snapshot in snapshots:
            await state_store.save_state(snapshot)
        
        # Run each query multiple times and verify consistency
        for query in queries:
            results1 = await state_store.load_state(query)
            results2 = await state_store.load_state(query)
            
            # Results should be identical (same count and content)
            assert len(results1) == len(results2), "Query results should be consistent"
            
            result_ids1 = {r.id for r in results1}
            result_ids2 = {r.id for r in results2}
            assert result_ids1 == result_ids2, "Query should return same snapshots consistently"
    
    @given(retention_days=st.integers(min_value=0, max_value=100))
    @pytest.mark.asyncio
    @settings(max_examples=10, deadline=10000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_cleanup_respects_retention(self, retention_days):
        """Test that cleanup respects retention period"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        # Create old and new snapshots
        old_snapshot = StateSnapshot(
            agent_id="old_agent",
            state_type=StateType.AGENT_STATE,
            data={"status": "old"},
            timestamp=datetime.utcnow() - timedelta(days=retention_days + 5)
        )
        
        new_snapshot = StateSnapshot(
            agent_id="new_agent", 
            state_type=StateType.AGENT_STATE,
            data={"status": "new"}
        )
        
        await state_store.save_state(old_snapshot)
        await state_store.save_state(new_snapshot)
        
        # Run cleanup
        cleaned_count = await state_store.cleanup_old_states(retention_days=retention_days)
        
        # Verify retention behavior
        if retention_days == 0:
            # Should clean everything old
            assert cleaned_count >= 0
        else:
            # New snapshot should remain
            new_query = StateQuery(agent_id="new_agent")
            new_results = await state_store.load_state(new_query)
            assert len(new_results) > 0, "Recent snapshots should be retained"
    
    @given(data=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(
            st.text(max_size=1000),
            st.integers(min_value=-10000, max_value=10000),
            st.lists(st.integers(), max_size=100),
            st.dictionaries(st.text(max_size=10), st.text(max_size=100), max_size=10)
        ),
        min_size=0,
        max_size=20
    ))
    @pytest.mark.asyncio
    @settings(max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_large_data_handling(self, data):
        """Test that StateStore handles various data structures correctly"""
        from tests.contracts.test_state_store_contract import MockStateStore
        state_store = MockStateStore()
        snapshot = StateSnapshot(
            agent_id="large_data_agent",
            state_type=StateType.AGENT_STATE,
            data=data
        )
        
        # Should save successfully
        result = await state_store.save_state(snapshot)
        assert result is True
        
        # Should retrieve data correctly
        latest = await state_store.get_latest_state(snapshot.agent_id, snapshot.state_type)
        assert latest is not None
        assert latest.data == data, "Retrieved data should match original"


if __name__ == "__main__":
    # Run property-based tests manually
    import pytest
    pytest.main([__file__, "-v"])
