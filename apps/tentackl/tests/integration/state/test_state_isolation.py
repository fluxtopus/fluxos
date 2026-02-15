"""
Integration tests for state isolation across components

These tests verify that state isolation works correctly when multiple
components interact together, ensuring that contexts and state are
properly isolated between different agents and execution contexts.
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any, List

from src.core.sub_agent_generator import SubAgentGenerator
from src.core.parallel_executor import ParallelExecutor, ExecutionMode
from src.interfaces.sub_agent_generator import (
    AgentSpecification, GenerationRequest, AgentType, GenerationStrategy,
    ContextIsolationLevel
)
from src.core.execution_tree import ExecutionStatus, ExecutionPriority, NodeType
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree


@pytest.mark.integration
class TestStateIsolation:
    """Test state isolation across different components"""
    
    @pytest.fixture(scope="function")
    async def redis_state_store(self):
        """Redis state store for testing"""
        store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=11,  # Use separate DB for testing
            key_prefix="test_state_isolation"
        )
        await store.health_check()
        yield store
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/11")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_context_manager(self):
        """Redis context manager for testing"""
        manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=12,  # Use separate DB for testing
            key_prefix="test_isolation_ctx"
        )
        await manager.health_check()
        yield manager
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/12")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_execution_tree(self):
        """Redis execution tree for testing"""
        tree = RedisExecutionTree(
            redis_url="redis://redis:6379",
            db=13,  # Use separate DB for testing
            key_prefix="test_isolation_tree"
        )
        await tree.health_check()
        yield tree
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/13")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture
    async def isolation_test_setup(self, redis_state_store, redis_context_manager, redis_execution_tree):
        """Complete isolation testing setup"""
        # Create multiple parent contexts with different isolation levels
        parent_context_shallow = await redis_context_manager.create_context(
            agent_id="parent_shallow",
            isolation_level=ContextIsolationLevel.SHALLOW,
            config={"shared_setting": "shallow_value"},
            environment="test_shallow"
        )
        
        parent_context_deep = await redis_context_manager.create_context(
            agent_id="parent_deep",
            isolation_level=ContextIsolationLevel.DEEP,
            config={"shared_setting": "deep_value"},
            environment="test_deep"
        )
        
        parent_context_sandboxed = await redis_context_manager.create_context(
            agent_id="parent_sandboxed",
            isolation_level=ContextIsolationLevel.SANDBOXED,
            config={"shared_setting": "sandboxed_value"},
            environment="test_sandboxed"
        )
        
        # Create separate execution trees
        tree_shallow = await redis_execution_tree.create_tree("shallow_tree")
        tree_deep = await redis_execution_tree.create_tree("deep_tree")
        tree_sandboxed = await redis_execution_tree.create_tree("sandboxed_tree")
        
        # Create components
        sub_agent_generator = SubAgentGenerator(
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_generations=5
        )
        
        parallel_executor = ParallelExecutor(
            sub_agent_generator=sub_agent_generator,
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_executions=5
        )
        
        return {
            "sub_agent_generator": sub_agent_generator,
            "parallel_executor": parallel_executor,
            "contexts": {
                "shallow": parent_context_shallow,
                "deep": parent_context_deep,
                "sandboxed": parent_context_sandboxed
            },
            "trees": {
                "shallow": tree_shallow,
                "deep": tree_deep,
                "sandboxed": tree_sandboxed
            }
        }
    
    @pytest.mark.asyncio
    async def test_context_isolation_between_trees(self, isolation_test_setup):
        """Test that contexts are isolated between different execution trees"""
        setup = isolation_test_setup
        
        # Create specifications for different trees with same agent names but different contexts
        shallow_spec = AgentSpecification(
            name="test_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Agent in shallow context",
            parameters={"input_source": "shallow_data.csv", "output_format": "json"},
            isolation_level=ContextIsolationLevel.SHALLOW,
            environment={"TREE_TYPE": "shallow", "SHARED_VAR": "shallow_value"}
        )
        
        deep_spec = AgentSpecification(
            name="test_agent",  # Same name as shallow
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Agent in deep context",
            parameters={"input_source": "deep_data.csv", "output_format": "json"},
            isolation_level=ContextIsolationLevel.DEEP,
            environment={"TREE_TYPE": "deep", "SHARED_VAR": "deep_value"}
        )
        
        # Generate agents in different trees
        shallow_request = GenerationRequest(
            parent_agent_id="parent_shallow",
            parent_context_id=setup["contexts"]["shallow"],
            tree_id=setup["trees"]["shallow"],
            specifications=[shallow_spec],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        deep_request = GenerationRequest(
            parent_agent_id="parent_deep",
            parent_context_id=setup["contexts"]["deep"],
            tree_id=setup["trees"]["deep"],
            specifications=[deep_spec],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        # Generate in parallel to test isolation
        shallow_result, deep_result = await asyncio.gather(
            setup["sub_agent_generator"].generate_sub_agents(shallow_request),
            setup["sub_agent_generator"].generate_sub_agents(deep_request)
        )
        
        # Both should succeed independently
        assert shallow_result.success is True
        assert deep_result.success is True
        assert len(shallow_result.execution_nodes) == 1
        assert len(deep_result.execution_nodes) == 1
        
        # Verify nodes are in different trees
        shallow_node = shallow_result.execution_nodes[0]
        deep_node = deep_result.execution_nodes[0]
        
        assert shallow_node.name == "test_agent"
        assert deep_node.name == "test_agent"
        
        # Verify they have different environment settings
        shallow_env = shallow_node.task_data["specification"]["environment"]
        deep_env = deep_node.task_data["specification"]["environment"]
        
        assert shallow_env["TREE_TYPE"] == "shallow"
        assert deep_env["TREE_TYPE"] == "deep"
        assert shallow_env["SHARED_VAR"] == "shallow_value"
        assert deep_env["SHARED_VAR"] == "deep_value"
        
        # Verify nodes are in different execution trees
        shallow_tree_snapshot = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(
            setup["trees"]["shallow"]
        )
        deep_tree_snapshot = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(
            setup["trees"]["deep"]
        )
        
        assert shallow_tree_snapshot is not None
        assert deep_tree_snapshot is not None
        
        # Each tree should contain only its own nodes
        shallow_node_ids = set(shallow_tree_snapshot.nodes.keys())
        deep_node_ids = set(deep_tree_snapshot.nodes.keys())
        
        assert shallow_node.id in shallow_node_ids
        assert deep_node.id in deep_node_ids
        assert shallow_node.id not in deep_node_ids
        assert deep_node.id not in shallow_node_ids
    
    @pytest.mark.asyncio
    async def test_state_isolation_with_parallel_execution(self, isolation_test_setup):
        """Test state isolation during parallel execution of agents"""
        setup = isolation_test_setup
        
        # Create specifications with different isolation levels
        specifications = [
            AgentSpecification(
                name="shallow_agent_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Shallow agent 1",
                parameters={"input_source": "data1.csv", "output_format": "json"},
                isolation_level=ContextIsolationLevel.SHALLOW,
                environment={"ISOLATION": "shallow", "AGENT_ID": "1"}
            ),
            AgentSpecification(
                name="shallow_agent_2",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Shallow agent 2",
                parameters={"input_source": "data2.csv", "output_format": "json"},
                isolation_level=ContextIsolationLevel.SHALLOW,
                environment={"ISOLATION": "shallow", "AGENT_ID": "2"}
            ),
            AgentSpecification(
                name="deep_agent_1",
                agent_type=AgentType.API_CALLER,
                task_description="Deep agent 1",
                parameters={"endpoint": "http://api1.com", "method": "GET"},
                isolation_level=ContextIsolationLevel.DEEP,
                environment={"ISOLATION": "deep", "AGENT_ID": "1"}
            ),
            AgentSpecification(
                name="sandboxed_agent_1",
                agent_type=AgentType.VALIDATOR,
                task_description="Sandboxed agent 1",
                parameters={"validation_rules": "rules1.json", "data_source": "data"},
                isolation_level=ContextIsolationLevel.SANDBOXED,
                environment={"ISOLATION": "sandboxed", "AGENT_ID": "1"},
                max_memory_mb=512,
                max_cpu_percent=25
            )
        ]
        
        # Create execution plan
        plan = await setup["parallel_executor"].create_execution_plan(
            specifications=specifications,
            execution_mode=ExecutionMode.PARALLEL
        )
        
        # Generate agents
        request = GenerationRequest(
            parent_agent_id="parent_isolation_test",
            parent_context_id=setup["contexts"]["shallow"],  # Use shallow as parent
            tree_id=setup["trees"]["shallow"],
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        result = await setup["sub_agent_generator"].generate_sub_agents(request)
        
        assert result.success is True
        assert len(result.execution_nodes) == 4
        
        # Verify each agent has correct isolation settings
        nodes_by_name = {node.name: node for node in result.execution_nodes}
        
        # Check shallow agents
        shallow_1 = nodes_by_name["shallow_agent_1"]
        shallow_2 = nodes_by_name["shallow_agent_2"]
        
        assert shallow_1.task_data["specification"]["isolation_level"] == "shallow"
        assert shallow_2.task_data["specification"]["isolation_level"] == "shallow"
        assert shallow_1.task_data["specification"]["environment"]["AGENT_ID"] == "1"
        assert shallow_2.task_data["specification"]["environment"]["AGENT_ID"] == "2"
        
        # Check deep agent
        deep_1 = nodes_by_name["deep_agent_1"]
        assert deep_1.task_data["specification"]["isolation_level"] == "deep"
        assert deep_1.task_data["specification"]["environment"]["ISOLATION"] == "deep"
        
        # Check sandboxed agent
        sandboxed_1 = nodes_by_name["sandboxed_agent_1"]
        assert sandboxed_1.task_data["specification"]["isolation_level"] == "sandboxed"
        assert sandboxed_1.task_data["specification"]["environment"]["ISOLATION"] == "sandboxed"
        assert sandboxed_1.task_data["specification"]["max_memory_mb"] == 512
    
    @pytest.mark.asyncio
    async def test_context_variable_isolation(self, isolation_test_setup):
        """Test that context variables are properly isolated"""
        setup = isolation_test_setup
        
        # Get current contexts and update their variables
        shallow_context = await setup["sub_agent_generator"].context_manager.get_context(
            setup["contexts"]["shallow"]
        )
        deep_context = await setup["sub_agent_generator"].context_manager.get_context(
            setup["contexts"]["deep"]
        )
        
        # Update variables manually and save contexts
        shallow_context.variables.update({
            "shared_var": "shallow_updated", 
            "shallow_only": "shallow_value"
        })
        deep_context.variables.update({
            "shared_var": "deep_updated", 
            "deep_only": "deep_value"
        })
        
        # Save the updated contexts back
        await setup["sub_agent_generator"].context_manager.update_context(
            setup["contexts"]["shallow"],
            {"variables": shallow_context.variables}
        )
        
        await setup["sub_agent_generator"].context_manager.update_context(
            setup["contexts"]["deep"],
            {"variables": deep_context.variables}
        )
        
        # Create child contexts
        child_shallow = await setup["sub_agent_generator"].context_manager.fork_context(
            parent_context_id=setup["contexts"]["shallow"],
            child_agent_id="child_shallow_agent"
        )
        
        child_deep = await setup["sub_agent_generator"].context_manager.fork_context(
            parent_context_id=setup["contexts"]["deep"],
            child_agent_id="child_deep_agent"
        )
        
        # Update child contexts with different values
        child_shallow_context = await setup["sub_agent_generator"].context_manager.get_context(
            child_shallow
        )
        child_deep_context = await setup["sub_agent_generator"].context_manager.get_context(
            child_deep
        )
        
        child_shallow_context.variables.update({
            "child_var": "child_shallow_value", 
            "shared_var": "child_shallow_updated"
        })
        child_deep_context.variables.update({
            "child_var": "child_deep_value", 
            "shared_var": "child_deep_updated"
        })
        
        await setup["sub_agent_generator"].context_manager.update_context(
            child_shallow,
            {"variables": child_shallow_context.variables}
        )
        
        await setup["sub_agent_generator"].context_manager.update_context(
            child_deep,
            {"variables": child_deep_context.variables}
        )
        
        # Retrieve contexts and verify isolation
        shallow_context = await setup["sub_agent_generator"].context_manager.get_context(
            setup["contexts"]["shallow"]
        )
        deep_context = await setup["sub_agent_generator"].context_manager.get_context(
            setup["contexts"]["deep"]
        )
        child_shallow_context = await setup["sub_agent_generator"].context_manager.get_context(
            child_shallow
        )
        child_deep_context = await setup["sub_agent_generator"].context_manager.get_context(
            child_deep
        )
        
        # Verify parent contexts are isolated
        assert shallow_context.variables["shared_var"] == "shallow_updated"
        assert deep_context.variables["shared_var"] == "deep_updated"
        assert "shallow_only" in shallow_context.variables
        assert "deep_only" in deep_context.variables
        assert "shallow_only" not in deep_context.variables
        assert "deep_only" not in shallow_context.variables
        
        # Verify child contexts are isolated from each other
        assert child_shallow_context.variables["shared_var"] == "child_shallow_updated"
        assert child_deep_context.variables["shared_var"] == "child_deep_updated"
        assert child_shallow_context.variables["child_var"] == "child_shallow_value"
        assert child_deep_context.variables["child_var"] == "child_deep_value"
        
        # Verify child contexts have correct parent relationships
        assert child_shallow_context.parent_context_id == setup["contexts"]["shallow"]
        assert child_deep_context.parent_context_id == setup["contexts"]["deep"]
    
    @pytest.mark.asyncio
    async def test_state_store_isolation_across_agents(self, isolation_test_setup):
        """Test that state store data is properly isolated between agents"""
        setup = isolation_test_setup
        
        from src.interfaces.state_store import StateSnapshot, StateType
        
        # Create different agent states using StateSnapshot
        agent_snapshots = [
            ("agent_1", StateSnapshot(
                agent_id="agent_1",
                state_type=StateType.AGENT_STATE,
                data={"type": "data_processor", "status": "processing", "data": "agent_1_data"},
                metadata={"test": "isolation_test"}
            )),
            ("agent_2", StateSnapshot(
                agent_id="agent_2",
                state_type=StateType.AGENT_STATE,
                data={"type": "api_caller", "status": "calling", "data": "agent_2_data"},
                metadata={"test": "isolation_test"}
            )),
            ("agent_3", StateSnapshot(
                agent_id="agent_3",
                state_type=StateType.AGENT_STATE,
                data={"type": "validator", "status": "validating", "data": "agent_3_data"},
                metadata={"test": "isolation_test"}
            ))
        ]
        
        # Store states for different agents
        for agent_id, snapshot in agent_snapshots:
            success = await setup["sub_agent_generator"].state_store.save_state(snapshot)
            assert success is True
        
        # Retrieve and verify isolation
        for agent_id, expected_snapshot in agent_snapshots:
            retrieved_snapshot = await setup["sub_agent_generator"].state_store.get_latest_state(
                agent_id, StateType.AGENT_STATE
            )
            assert retrieved_snapshot is not None
            assert retrieved_snapshot.agent_id == expected_snapshot.agent_id
            assert retrieved_snapshot.data == expected_snapshot.data
            
            # Verify other agents' data is not accessible through this agent's state
            for other_agent_id, other_snapshot in agent_snapshots:
                if other_agent_id != agent_id:
                    assert retrieved_snapshot.agent_id != other_snapshot.agent_id
                    assert retrieved_snapshot.data != other_snapshot.data
        
        # Test concurrent state updates
        async def update_agent_state(agent_id: str, updates: Dict[str, Any]):
            current_snapshot = await setup["sub_agent_generator"].state_store.get_latest_state(
                agent_id, StateType.AGENT_STATE
            )
            if current_snapshot:
                updated_data = current_snapshot.data.copy()
                updated_data.update(updates)
                new_snapshot = StateSnapshot(
                    agent_id=agent_id,
                    state_type=StateType.AGENT_STATE,
                    data=updated_data,
                    metadata=current_snapshot.metadata
                )
                await setup["sub_agent_generator"].state_store.save_state(new_snapshot)
        
        # Update states concurrently
        update_tasks = [
            update_agent_state("agent_1", {"status": "completed", "result": "success"}),
            update_agent_state("agent_2", {"status": "failed", "error": "timeout"}),
            update_agent_state("agent_3", {"status": "completed", "result": "valid"})
        ]
        
        await asyncio.gather(*update_tasks)
        
        # Verify updates were applied correctly and independently
        agent_1_state = await setup["sub_agent_generator"].state_store.get_latest_state("agent_1", StateType.AGENT_STATE)
        agent_2_state = await setup["sub_agent_generator"].state_store.get_latest_state("agent_2", StateType.AGENT_STATE)
        agent_3_state = await setup["sub_agent_generator"].state_store.get_latest_state("agent_3", StateType.AGENT_STATE)
        
        assert agent_1_state.data["status"] == "completed"
        assert agent_1_state.data["result"] == "success"
        assert agent_2_state.data["status"] == "failed"
        assert agent_2_state.data["error"] == "timeout"
        assert agent_3_state.data["status"] == "completed"
        assert agent_3_state.data["result"] == "valid"
    
    @pytest.mark.asyncio
    async def test_execution_tree_isolation(self, isolation_test_setup):
        """Test that execution trees are properly isolated"""
        setup = isolation_test_setup
        
        # Create nodes in different trees
        tree_data = [
            (setup["trees"]["shallow"], "shallow_node_1", "Shallow tree node 1"),
            (setup["trees"]["shallow"], "shallow_node_2", "Shallow tree node 2"),
            (setup["trees"]["deep"], "deep_node_1", "Deep tree node 1"),
            (setup["trees"]["sandboxed"], "sandboxed_node_1", "Sandboxed tree node 1")
        ]
        
        created_nodes = []
        for tree_id, node_name, description in tree_data:
            from src.core.execution_tree import ExecutionNode
            node = ExecutionNode(
                name=node_name,
                node_type=NodeType.SUB_AGENT,
                status=ExecutionStatus.PENDING,
                priority=ExecutionPriority.NORMAL,
                task_data={"description": description, "tree_id": tree_id}
            )
            
            success = await setup["sub_agent_generator"].execution_tree.add_node(tree_id, node)
            assert success is True
            created_nodes.append((tree_id, node))
        
        # Verify each tree contains only its own nodes
        for tree_id in [setup["trees"]["shallow"], setup["trees"]["deep"], setup["trees"]["sandboxed"]]:
            tree_snapshot = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(tree_id)
            assert tree_snapshot is not None
            
            # Filter nodes that were created for this tree
            expected_nodes = [node for t_id, node in created_nodes if t_id == tree_id]
            
            # Verify all expected nodes are in the tree
            for expected_node in expected_nodes:
                assert expected_node.id in tree_snapshot.nodes
            
            # Verify no unexpected nodes are in the tree
            for t_id, node in created_nodes:
                if t_id != tree_id:
                    assert node.id not in tree_snapshot.nodes
    
    @pytest.mark.asyncio
    async def test_concurrent_isolation_stress_test(self, isolation_test_setup):
        """Stress test isolation under concurrent operations"""
        setup = isolation_test_setup
        
        # Create multiple concurrent operations across different isolation levels
        num_agents_per_level = 3
        
        async def create_and_execute_agents(isolation_level: ContextIsolationLevel, tree_id: str, context_id: str, prefix: str):
            specifications = []
            for i in range(num_agents_per_level):
                spec = AgentSpecification(
                    name=f"{prefix}_agent_{i}",
                    agent_type=AgentType.DATA_PROCESSOR,
                    task_description=f"{prefix} agent {i}",
                    parameters={"input_source": f"{prefix}_data_{i}.csv", "output_format": "json"},
                    isolation_level=isolation_level,
                    environment={"PREFIX": prefix, "AGENT_NUM": str(i)}
                )
                specifications.append(spec)
            
            request = GenerationRequest(
                parent_agent_id=f"parent_{prefix}",
                parent_context_id=context_id,
                tree_id=tree_id,
                specifications=specifications,
                generation_strategy=GenerationStrategy.LAZY
            )
            
            return await setup["sub_agent_generator"].generate_sub_agents(request)
        
        # Run concurrent operations
        concurrent_tasks = [
            create_and_execute_agents(
                ContextIsolationLevel.SHALLOW,
                setup["trees"]["shallow"],
                setup["contexts"]["shallow"],
                "shallow"
            ),
            create_and_execute_agents(
                ContextIsolationLevel.DEEP,
                setup["trees"]["deep"],
                setup["contexts"]["deep"],
                "deep"
            ),
            create_and_execute_agents(
                ContextIsolationLevel.SANDBOXED,
                setup["trees"]["sandboxed"],
                setup["contexts"]["sandboxed"],
                "sandboxed"
            )
        ]
        
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        
        # Verify all operations succeeded
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"
            assert result.success is True
            assert len(result.execution_nodes) == num_agents_per_level
        
        # Verify each tree has the correct number of nodes
        tree_keys = ["shallow", "deep", "sandboxed"]
        for i, key in enumerate(tree_keys):
            tree_snapshot = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(
                setup["trees"][key]
            )
            assert tree_snapshot is not None
            
            # Count nodes that match our created agents
            matching_nodes = [
                node for node in tree_snapshot.nodes.values()
                if node.name.startswith(f"{key}_agent_")
            ]
            assert len(matching_nodes) == num_agents_per_level
            
            # Verify isolation - no cross-contamination
            for node in tree_snapshot.nodes.values():
                if node.name.startswith(f"{key}_agent_"):
                    env = node.task_data.get("specification", {}).get("environment", {})
                    assert env.get("PREFIX") == key
    
    @pytest.mark.asyncio
    async def test_cleanup_isolation(self, isolation_test_setup):
        """Test that cleanup operations maintain isolation"""
        setup = isolation_test_setup
        
        # Create test data in different contexts and trees
        test_data = [
            ("shallow", setup["contexts"]["shallow"], setup["trees"]["shallow"]),
            ("deep", setup["contexts"]["deep"], setup["trees"]["deep"]),
            ("sandboxed", setup["contexts"]["sandboxed"], setup["trees"]["sandboxed"])
        ]
        
        # Create agents and contexts
        for prefix, context_id, tree_id in test_data:
            # Create child context
            child_context = await setup["sub_agent_generator"].context_manager.fork_context(
                parent_context_id=context_id,
                child_agent_id=f"{prefix}_cleanup_agent"
            )
            
            # Add context variables
            await setup["sub_agent_generator"].context_manager.update_context(
                child_context,
                {"cleanup_test": f"{prefix}_value", "agent_type": prefix}
            )
            
            # Create execution node
            from src.core.execution_tree import ExecutionNode
            node = ExecutionNode(
                name=f"{prefix}_cleanup_node",
                node_type=NodeType.SUB_AGENT,
                status=ExecutionStatus.COMPLETED,
                priority=ExecutionPriority.NORMAL,
                context_id=child_context,
                task_data={"cleanup_test": True, "prefix": prefix}
            )
            
            await setup["sub_agent_generator"].execution_tree.add_node(tree_id, node)
        
        # Perform selective cleanup - only clean up "shallow" context
        shallow_child_contexts = await setup["sub_agent_generator"].context_manager.get_child_contexts(
            setup["contexts"]["shallow"]
        )
        
        # Clean up shallow contexts only
        for context in shallow_child_contexts:
            await setup["sub_agent_generator"].context_manager.terminate_context(context.id, cleanup=True)
        
        # Verify shallow contexts are cleaned but others remain
        remaining_deep_contexts = await setup["sub_agent_generator"].context_manager.get_child_contexts(
            setup["contexts"]["deep"]
        )
        remaining_sandboxed_contexts = await setup["sub_agent_generator"].context_manager.get_child_contexts(
            setup["contexts"]["sandboxed"]
        )
        
        assert len(remaining_deep_contexts) > 0
        assert len(remaining_sandboxed_contexts) > 0
        
        # Verify execution trees still contain their respective nodes
        deep_tree = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(
            setup["trees"]["deep"]
        )
        sandboxed_tree = await setup["sub_agent_generator"].execution_tree.get_tree_snapshot(
            setup["trees"]["sandboxed"]
        )
        
        assert deep_tree is not None
        assert sandboxed_tree is not None
        
        # Check that nodes are still there
        deep_node_names = {node.name for node in deep_tree.nodes.values()}
        sandboxed_node_names = {node.name for node in sandboxed_tree.nodes.values()}
        
        assert "deep_cleanup_node" in deep_node_names
        assert "sandboxed_cleanup_node" in sandboxed_node_names


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])