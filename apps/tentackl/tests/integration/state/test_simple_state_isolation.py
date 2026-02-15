"""
Simplified integration tests for state isolation

These tests focus on the most critical aspects of state isolation
that work with the current implementation.
"""

import pytest
import asyncio
from datetime import datetime

from src.core.sub_agent_generator import SubAgentGenerator
from src.interfaces.sub_agent_generator import (
    AgentSpecification, GenerationRequest, AgentType, GenerationStrategy,
    ContextIsolationLevel
)
from src.core.execution_tree import ExecutionStatus, ExecutionPriority, NodeType
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree


@pytest.mark.integration
class TestSimpleStateIsolation:
    """Test basic state isolation between different components"""
    
    @pytest.fixture(scope="function")
    async def redis_state_store(self):
        """Redis state store for testing"""
        store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=14,  # Use separate DB for testing
            key_prefix="test_simple_isolation"
        )
        await store.health_check()
        yield store
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/14")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_context_manager(self):
        """Redis context manager for testing"""
        manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=15,  # Use separate DB for testing
            key_prefix="test_simple_ctx"
        )
        await manager.health_check()
        yield manager
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/15")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_execution_tree(self):
        """Redis execution tree for testing"""
        tree = RedisExecutionTree(
            redis_url="redis://redis:6379",
            db=6,  # Use separate DB for testing (within 0-15 range)
            key_prefix="test_simple_tree"
        )
        await tree.health_check()
        yield tree
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/6")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture
    async def isolation_setup(self, redis_state_store, redis_context_manager, redis_execution_tree):
        """Basic isolation testing setup"""
        # Create separate parent contexts
        context_1 = await redis_context_manager.create_context(
            agent_id="parent_1",
            isolation_level=ContextIsolationLevel.DEEP,
            variables={"parent_id": "1", "shared_var": "parent_1_value"}
        )
        
        context_2 = await redis_context_manager.create_context(
            agent_id="parent_2",
            isolation_level=ContextIsolationLevel.DEEP,
            variables={"parent_id": "2", "shared_var": "parent_2_value"}
        )
        
        # Create separate execution trees
        tree_1 = await redis_execution_tree.create_tree("isolation_tree_1")
        tree_2 = await redis_execution_tree.create_tree("isolation_tree_2")
        
        # Create generator
        sub_agent_generator = SubAgentGenerator(
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_generations=3
        )
        
        return {
            "generator": sub_agent_generator,
            "contexts": {"context_1": context_1, "context_2": context_2},
            "trees": {"tree_1": tree_1, "tree_2": tree_2}
        }
    
    @pytest.mark.asyncio
    async def test_context_creation_isolation(self, isolation_setup):
        """Test that contexts are isolated during creation"""
        setup = isolation_setup
        
        # Retrieve the created contexts
        context_1 = await setup["generator"].context_manager.get_context(setup["contexts"]["context_1"])
        context_2 = await setup["generator"].context_manager.get_context(setup["contexts"]["context_2"])
        
        assert context_1 is not None
        assert context_2 is not None
        
        # Verify they have different agent IDs
        assert context_1.agent_id == "parent_1"
        assert context_2.agent_id == "parent_2"
        
        # Verify they have different context IDs
        assert context_1.id != context_2.id
        assert context_1.id == setup["contexts"]["context_1"]
        assert context_2.id == setup["contexts"]["context_2"]
        
        # Verify isolation level
        assert context_1.isolation_level == ContextIsolationLevel.DEEP
        assert context_2.isolation_level == ContextIsolationLevel.DEEP
    
    @pytest.mark.asyncio
    async def test_execution_tree_isolation(self, isolation_setup):
        """Test that execution trees are isolated"""
        setup = isolation_setup
        
        # Create specifications for different trees
        spec_1 = AgentSpecification(
            name="agent_tree_1",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Agent in tree 1",
            parameters={"input_source": "data1.csv", "output_format": "json"},
            isolation_level=ContextIsolationLevel.DEEP
        )
        
        spec_2 = AgentSpecification(
            name="agent_tree_2",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Agent in tree 2",
            parameters={"input_source": "data2.csv", "output_format": "json"},
            isolation_level=ContextIsolationLevel.DEEP
        )
        
        # Generate agents in different trees
        request_1 = GenerationRequest(
            parent_agent_id="parent_1",
            parent_context_id=setup["contexts"]["context_1"],
            tree_id=setup["trees"]["tree_1"],
            specifications=[spec_1],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        request_2 = GenerationRequest(
            parent_agent_id="parent_2",
            parent_context_id=setup["contexts"]["context_2"],
            tree_id=setup["trees"]["tree_2"],
            specifications=[spec_2],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        # Generate in parallel
        result_1, result_2 = await asyncio.gather(
            setup["generator"].generate_sub_agents(request_1),
            setup["generator"].generate_sub_agents(request_2)
        )
        
        # Both should succeed
        assert result_1.success is True
        assert result_2.success is True
        assert len(result_1.execution_nodes) == 1
        assert len(result_2.execution_nodes) == 1
        
        # Get nodes
        node_1 = result_1.execution_nodes[0]
        node_2 = result_2.execution_nodes[0]
        
        # Verify nodes have different IDs
        assert node_1.id != node_2.id
        
        # Verify nodes are in different trees
        tree_1_snapshot = await setup["generator"].execution_tree.get_tree_snapshot(setup["trees"]["tree_1"])
        tree_2_snapshot = await setup["generator"].execution_tree.get_tree_snapshot(setup["trees"]["tree_2"])
        
        assert tree_1_snapshot is not None
        assert tree_2_snapshot is not None
        
        # Check tree contents
        tree_1_node_ids = set(tree_1_snapshot.nodes.keys())
        tree_2_node_ids = set(tree_2_snapshot.nodes.keys())
        
        assert node_1.id in tree_1_node_ids
        assert node_2.id in tree_2_node_ids
        assert node_1.id not in tree_2_node_ids
        assert node_2.id not in tree_1_node_ids
    
    @pytest.mark.asyncio
    async def test_context_forking_isolation(self, isolation_setup):
        """Test that context forking creates isolated child contexts"""
        setup = isolation_setup
        
        # Create child contexts from different parents
        child_1 = await setup["generator"].context_manager.fork_context(
            parent_context_id=setup["contexts"]["context_1"],
            child_agent_id="child_1"
        )
        
        child_2 = await setup["generator"].context_manager.fork_context(
            parent_context_id=setup["contexts"]["context_2"],
            child_agent_id="child_2"
        )
        
        # Verify child contexts are different
        assert child_1 != child_2
        
        # Retrieve child contexts
        child_context_1 = await setup["generator"].context_manager.get_context(child_1)
        child_context_2 = await setup["generator"].context_manager.get_context(child_2)
        
        assert child_context_1 is not None
        assert child_context_2 is not None
        
        # Verify parent relationships
        assert child_context_1.parent_context_id == setup["contexts"]["context_1"]
        assert child_context_2.parent_context_id == setup["contexts"]["context_2"]
        
        # Verify different agent IDs
        assert child_context_1.agent_id == "child_1"
        assert child_context_2.agent_id == "child_2"
    
    @pytest.mark.asyncio
    async def test_concurrent_agent_generation_isolation(self, isolation_setup):
        """Test isolation during concurrent agent generation"""
        setup = isolation_setup
        
        # Create multiple specifications with same names but different contexts
        num_agents = 5
        tasks = []
        
        for i in range(num_agents):
            spec = AgentSpecification(
                name=f"concurrent_agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Concurrent agent {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"},
                isolation_level=ContextIsolationLevel.DEEP,
                environment={"agent_index": str(i)}
            )
            
            # Alternate between two contexts and trees
            context_key = "context_1" if i % 2 == 0 else "context_2"
            tree_key = "tree_1" if i % 2 == 0 else "tree_2"
            
            request = GenerationRequest(
                parent_agent_id=f"parent_{i}",
                parent_context_id=setup["contexts"][context_key],
                tree_id=setup["trees"][tree_key],
                specifications=[spec],
                generation_strategy=GenerationStrategy.LAZY
            )
            
            tasks.append(setup["generator"].generate_sub_agents(request))
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all succeeded
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"
            assert result.success is True, f"Task {i} was not successful"
            assert len(result.execution_nodes) == 1
        
        # Verify tree isolation
        tree_1_snapshot = await setup["generator"].execution_tree.get_tree_snapshot(setup["trees"]["tree_1"])
        tree_2_snapshot = await setup["generator"].execution_tree.get_tree_snapshot(setup["trees"]["tree_2"])
        
        assert tree_1_snapshot is not None
        assert tree_2_snapshot is not None
        
        # Count agents in each tree
        tree_1_agent_count = len([
            node for node in tree_1_snapshot.nodes.values()
            if node.name.startswith("concurrent_agent_")
        ])
        tree_2_agent_count = len([
            node for node in tree_2_snapshot.nodes.values()
            if node.name.startswith("concurrent_agent_")
        ])
        
        # Should be roughly evenly distributed (3 in one, 2 in the other)
        assert tree_1_agent_count + tree_2_agent_count == num_agents
        assert tree_1_agent_count > 0
        assert tree_2_agent_count > 0
    
    @pytest.mark.asyncio
    async def test_agent_specification_isolation(self, isolation_setup):
        """Test that agent specifications are isolated between different generations"""
        setup = isolation_setup
        
        # Create agents with the same name but different configurations
        spec_config_1 = AgentSpecification(
            name="shared_name_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Agent with config 1",
            parameters={"input_source": "config1_data.csv", "output_format": "json"},
            isolation_level=ContextIsolationLevel.DEEP,
            environment={"config": "1", "shared_env": "value_1"},
            max_memory_mb=256
        )
        
        spec_config_2 = AgentSpecification(
            name="shared_name_agent",  # Same name
            agent_type=AgentType.API_CALLER,  # Different type
            task_description="Agent with config 2",
            parameters={"endpoint": "http://api.com", "method": "GET"},
            isolation_level=ContextIsolationLevel.SANDBOXED,
            environment={"config": "2", "shared_env": "value_2"},
            max_memory_mb=512
        )
        
        # Generate in different trees
        request_1 = GenerationRequest(
            parent_agent_id="parent_config_1",
            parent_context_id=setup["contexts"]["context_1"],
            tree_id=setup["trees"]["tree_1"],
            specifications=[spec_config_1],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        request_2 = GenerationRequest(
            parent_agent_id="parent_config_2",
            parent_context_id=setup["contexts"]["context_2"],
            tree_id=setup["trees"]["tree_2"],
            specifications=[spec_config_2],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        # Generate both
        result_1 = await setup["generator"].generate_sub_agents(request_1)
        result_2 = await setup["generator"].generate_sub_agents(request_2)
        
        assert result_1.success is True
        assert result_2.success is True
        
        # Get nodes
        node_1 = result_1.execution_nodes[0]
        node_2 = result_2.execution_nodes[0]
        
        # Verify they have the same name but different configurations
        assert node_1.name == "shared_name_agent"
        assert node_2.name == "shared_name_agent"
        
        # Verify different specifications
        spec_1_data = node_1.task_data["specification"]
        spec_2_data = node_2.task_data["specification"]
        
        assert spec_1_data["agent_type"] == "data_processor"
        assert spec_2_data["agent_type"] == "api_caller"
        
        assert spec_1_data["isolation_level"] == "deep"
        assert spec_2_data["isolation_level"] == "sandboxed"
        
        assert spec_1_data["max_memory_mb"] == 256
        assert spec_2_data["max_memory_mb"] == 512
        
        assert spec_1_data["environment"]["config"] == "1"
        assert spec_2_data["environment"]["config"] == "2"
        
        assert spec_1_data["environment"]["shared_env"] == "value_1"
        assert spec_2_data["environment"]["shared_env"] == "value_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])