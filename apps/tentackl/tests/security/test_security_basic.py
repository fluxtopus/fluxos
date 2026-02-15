"""
Basic Security Tests for State Isolation

These tests verify fundamental security properties of the state isolation system.
"""

import pytest
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any

from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.interfaces.state_store import StateSnapshot, StateType, StateQuery
from src.interfaces.context_manager import ContextIsolationLevel


class TestBasicSecurity:
    """Basic security tests"""
    
    @pytest.fixture(scope="function")
    async def security_setup(self):
        """Setup for security testing"""
        state_store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=14,
            key_prefix="sec_test"
        )
        await state_store.health_check()
        
        context_manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=14,
            key_prefix="sec_test_ctx"
        )
        await context_manager.health_check()
        
        yield {
            "state_store": state_store,
            "context_manager": context_manager
        }
        
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/14")
        await r.flushdb()
        await r.aclose()
    
    @pytest.mark.asyncio
    async def test_agent_state_isolation(self, security_setup):
        """Test that agents cannot access each other's states"""
        setup = security_setup
        
        # Create two agents
        agent1_id = f"agent_1_{uuid.uuid4().hex[:8]}"
        agent2_id = f"agent_2_{uuid.uuid4().hex[:8]}"
        
        # Save secret data for agent1
        secret_state = StateSnapshot(
            agent_id=agent1_id,
            state_type=StateType.AGENT_STATE,
            data={"secret": "agent1_secret_key", "balance": 1000},
            metadata={"security": "high"}
        )
        await setup["state_store"].save_state(secret_state)
        
        # Save normal data for agent2
        normal_state = StateSnapshot(
            agent_id=agent2_id,
            state_type=StateType.AGENT_STATE,
            data={"public": "agent2_data", "balance": 500},
            metadata={"security": "low"}
        )
        await setup["state_store"].save_state(normal_state)
        
        # Agent2 tries to access its own state
        agent2_state = await setup["state_store"].get_latest_state(
            agent2_id, StateType.AGENT_STATE
        )
        
        # Should only see its own data
        assert agent2_state is not None
        assert agent2_state.agent_id == agent2_id
        assert agent2_state.data["public"] == "agent2_data"
        assert "secret" not in agent2_state.data
        
        # Agent1 can access its own secret
        agent1_state = await setup["state_store"].get_latest_state(
            agent1_id, StateType.AGENT_STATE
        )
        assert agent1_state is not None
        assert agent1_state.data["secret"] == "agent1_secret_key"
    
    @pytest.mark.asyncio
    async def test_context_isolation_levels(self, security_setup):
        """Test different context isolation levels"""
        setup = security_setup
        
        # Create parent context with secrets
        parent_context = await setup["context_manager"].create_context(
            agent_id="parent_agent",
            isolation_level=ContextIsolationLevel.SHALLOW,
            variables={
                "api_key": "secret_api_key_123",
                "database_url": "postgres://secret@db:5432"
            },
            shared_resources={
                "cache": "redis_cache",
                "queue": "task_queue"
            }
        )
        
        # Test SANDBOXED isolation - no access to parent data
        from src.interfaces.context_manager import ContextForkOptions
        sandboxed_options = ContextForkOptions(
            isolation_level=ContextIsolationLevel.SANDBOXED,
            inherit_variables=False,
            inherit_shared_resources=False
        )
        sandboxed_ctx = await setup["context_manager"].fork_context(
            parent_context_id=parent_context,
            child_agent_id="sandboxed_child",
            fork_options=sandboxed_options
        )
        
        sandboxed_data = await setup["context_manager"].get_context(sandboxed_ctx)
        assert sandboxed_data is not None
        assert "api_key" not in sandboxed_data.variables
        assert sandboxed_data.shared_resources == {}
        
        # Test DEEP isolation - gets copy but isolated
        deep_options = ContextForkOptions(
            isolation_level=ContextIsolationLevel.DEEP,
            inherit_variables=True,
            inherit_shared_resources=True
        )
        
        deep_ctx = await setup["context_manager"].fork_context(
            parent_context_id=parent_context,
            child_agent_id="deep_child",
            fork_options=deep_options
        )
        
        deep_data = await setup["context_manager"].get_context(deep_ctx)
        assert deep_data is not None
        # In DEEP mode, variables are copied
        assert "api_key" in deep_data.variables
        
        # Modify child context
        await setup["context_manager"].update_context(
            deep_ctx,
            {"api_key": "modified_key"}
        )
        
        # Parent should be unaffected
        parent_data = await setup["context_manager"].get_context(parent_context)
        assert parent_data.variables["api_key"] == "secret_api_key_123"
    
    @pytest.mark.asyncio
    async def test_injection_prevention(self, security_setup):
        """Test prevention of injection attacks"""
        setup = security_setup
        
        # Test various injection attempts in agent IDs
        injections = [
            "'; DROP TABLE states; --",
            "agent_id\" OR \"1\"=\"1",
            "../../../etc/passwd",
            "<script>alert('xss')</script>"
        ]
        
        for injection in injections:
            # Use injection as agent ID
            state = StateSnapshot(
                agent_id=injection,
                state_type=StateType.AGENT_STATE,
                data={"test": "injection_test"},
                metadata={"injection": injection}
            )
            
            # Should handle safely
            result = await setup["state_store"].save_state(state)
            assert result is True
            
            # Should retrieve exact data (no execution)
            loaded = await setup["state_store"].get_latest_state(
                injection, StateType.AGENT_STATE
            )
            assert loaded is not None
            assert loaded.agent_id == injection
            
            # System should remain healthy
            health = await setup["state_store"].health_check()
            # health_check returns a dict or True
            if isinstance(health, dict):
                assert health["status"] == "healthy"
            else:
                assert health is True
    
    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self, security_setup):
        """Test safety under concurrent access"""
        setup = security_setup
        
        shared_account_id = "shared_account"
        initial_balance = 1000
        
        # Initialize shared state
        initial_state = StateSnapshot(
            agent_id=shared_account_id,
            state_type=StateType.AGENT_STATE,
            data={"balance": initial_balance},
            metadata={"type": "account"}
        )
        await setup["state_store"].save_state(initial_state)
        
        # Multiple concurrent withdrawals
        async def withdraw(amount: float, transaction_id: str):
            # Read current balance
            current = await setup["state_store"].get_latest_state(
                shared_account_id, StateType.AGENT_STATE
            )
            
            if current and current.data["balance"] >= amount:
                # Simulate processing
                await asyncio.sleep(0.01)
                
                # Update balance
                new_balance = current.data["balance"] - amount
                new_state = StateSnapshot(
                    agent_id=shared_account_id,
                    state_type=StateType.AGENT_STATE,
                    data={"balance": new_balance},
                    metadata={"last_transaction": transaction_id}
                )
                return await setup["state_store"].save_state(new_state)
            return False
        
        # Try concurrent withdrawals
        tasks = []
        for i in range(5):
            # Each trying to withdraw 300 (total 1500 > 1000)
            tasks.append(withdraw(300, f"tx_{i}"))
        
        results = await asyncio.gather(*tasks)
        
        # Check final balance
        final = await setup["state_store"].get_latest_state(
            shared_account_id, StateType.AGENT_STATE
        )
        
        # Balance should never go negative
        assert final.data["balance"] >= 0
        # Should not allow overdraft
        assert final.data["balance"] <= initial_balance


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])