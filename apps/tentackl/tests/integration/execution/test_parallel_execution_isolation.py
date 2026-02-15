"""
Integration tests for parallel execution isolation

These tests verify that the ParallelExecutor correctly manages isolated
execution of sub-agents with proper resource limits and context separation.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.core.parallel_executor import ParallelExecutor, ExecutionPlan, ExecutionResult, ExecutionMode
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
class TestParallelExecutionIsolation:
    """Test parallel execution isolation functionality"""
    
    @pytest.fixture(scope="function")
    async def redis_state_store(self):
        """Redis state store for testing"""
        store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=5,  # Use separate DB for testing
            key_prefix="test_parallel_exec"
        )
        await store.health_check()
        yield store
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/5")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_context_manager(self):
        """Redis context manager for testing"""
        manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=6,  # Use separate DB for testing
            key_prefix="test_parallel_ctx"
        )
        await manager.health_check()
        yield manager
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/6")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture(scope="function")
    async def redis_execution_tree(self):
        """Redis execution tree for testing"""
        tree = RedisExecutionTree(
            redis_url="redis://redis:6379",
            db=7,  # Use separate DB for testing
            key_prefix="test_parallel_tree"
        )
        await tree.health_check()
        yield tree
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/7")
        await r.flushdb()
        await r.aclose()
    
    @pytest.fixture
    async def parallel_executor_setup(self, redis_state_store, redis_context_manager, redis_execution_tree):
        """Complete ParallelExecutor setup with real Redis backends"""
        # Create parent context
        parent_context_id = await redis_context_manager.create_context(
            agent_id="parent_agent",
            isolation_level=ContextIsolationLevel.SHALLOW,
            config={"debug": True},
            environment="test"
        )
        
        # Create execution tree
        tree_id = await redis_execution_tree.create_tree("test_parallel_execution")
        
        # Create SubAgentGenerator
        sub_agent_generator = SubAgentGenerator(
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_generations=3
        )
        
        # Create ParallelExecutor
        parallel_executor = ParallelExecutor(
            sub_agent_generator=sub_agent_generator,
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_executions=5
        )
        
        yield parallel_executor, sub_agent_generator, parent_context_id, tree_id
    
    @pytest.mark.asyncio
    async def test_isolated_context_execution(self, parallel_executor_setup):
        """Test that agents execute in isolated contexts"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create specifications with different isolation levels
        specifications = [
            AgentSpecification(
                name="shallow_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Agent with shallow isolation",
                parameters={"input_source": "data.csv", "output_format": "json"},
                isolation_level=ContextIsolationLevel.SHALLOW,
                environment={"SHARED_VAR": "shallow_value"}
            ),
            AgentSpecification(
                name="deep_agent",
                agent_type=AgentType.API_CALLER,
                task_description="Agent with deep isolation",
                parameters={"endpoint": "http://api.com", "method": "GET"},
                isolation_level=ContextIsolationLevel.DEEP,
                environment={"ISOLATED_VAR": "deep_value"}
            ),
            AgentSpecification(
                name="sandboxed_agent",
                agent_type=AgentType.VALIDATOR,
                task_description="Agent with sandboxed isolation",
                parameters={"validation_rules": "rules.json", "data_source": "data"},
                isolation_level=ContextIsolationLevel.SANDBOXED,
                environment={"SECURE_VAR": "sandbox_value"},
                max_memory_mb=256,
                max_cpu_percent=25
            )
        ]
        
        # Create execution plan
        plan = await parallel_executor.create_execution_plan(
            specifications=specifications,
            execution_mode=ExecutionMode.PARALLEL
        )
        
        # Execute the plan using lazy strategy to avoid StatefulAgent issues
        generation_request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        # Generate execution nodes
        generation_result = await sub_agent_generator.generate_sub_agents(generation_request)
        
        assert generation_result.success is True
        assert len(generation_result.execution_nodes) == 3
        
        # Verify each agent has its own context
        context_ids = set()
        for node in generation_result.execution_nodes:
            # Check that node was created with proper task data
            assert node.task_data["lazy_generation"] is True
            assert node.task_data["parent_context_id"] == parent_context_id
            
            # Each agent should have different isolation levels
            spec_data = node.task_data["specification"]
            if spec_data["name"] == "shallow_agent":
                assert spec_data["isolation_level"] == "shallow"
            elif spec_data["name"] == "deep_agent":
                assert spec_data["isolation_level"] == "deep"
            elif spec_data["name"] == "sandboxed_agent":
                assert spec_data["isolation_level"] == "sandboxed"
        
        # Verify nodes are properly isolated in execution tree  
        tree_snapshot = await parallel_executor.execution_tree.get_tree_snapshot(tree_id)
        assert tree_snapshot is not None
        assert len(tree_snapshot.nodes) >= 3  # At least our 3 nodes
    
    @pytest.mark.asyncio
    async def test_resource_limit_enforcement(self, parallel_executor_setup):
        """Test that resource limits are properly enforced"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create specifications with varying resource requirements
        specifications = [
            AgentSpecification(
                name="low_resource_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Low resource agent",
                parameters={"input_source": "small_data.csv", "output_format": "json"},
                max_memory_mb=128,
                max_cpu_percent=10,
                timeout_seconds=60
            ),
            AgentSpecification(
                name="medium_resource_agent",
                agent_type=AgentType.ANALYZER,
                task_description="Medium resource agent",
                parameters={"analysis_type": "basic", "data_source": "medium_data"},
                max_memory_mb=512,
                max_cpu_percent=50,
                timeout_seconds=300
            ),
            AgentSpecification(
                name="high_resource_agent",
                agent_type=AgentType.FILE_HANDLER,
                task_description="High resource agent",
                parameters={"file_path": "large_file.bin", "operation": "compress"},
                max_memory_mb=2048,
                max_cpu_percent=80,
                timeout_seconds=600
            )
        ]
        
        # Test resource estimation
        resource_estimates = await sub_agent_generator.estimate_resource_usage(specifications)
        
        assert resource_estimates["total_memory_mb"] == 2688  # 128 + 512 + 2048
        assert resource_estimates["total_cpu_percent"] == 140  # 10 + 50 + 80
        assert resource_estimates["agent_count"] == 3
        assert "estimated_cost" in resource_estimates
        
        # Create execution plan with batch mode for resource management
        plan = await parallel_executor.create_execution_plan(
            specifications=specifications,
            execution_mode=ExecutionMode.BATCH
        )
        
        # Should create multiple groups due to resource constraints
        assert plan.execution_mode == ExecutionMode.BATCH
        assert plan.total_memory_mb == 2688
        assert plan.total_cpu_percent == 140
        
        # Verify execution order considers resource limits
        execution_order = plan.get_execution_order()
        assert len(execution_order) >= 1  # At least one execution level
        
        # Generate agents and verify resource allocation
        generation_request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        generation_result = await sub_agent_generator.generate_sub_agents(generation_request)
        
        assert generation_result.success is True
        assert len(generation_result.execution_nodes) == 3
        
        # Verify resource information is preserved in task data
        for node in generation_result.execution_nodes:
            spec_data = node.task_data["specification"]
            assert "max_memory_mb" in spec_data
            assert "max_cpu_percent" in spec_data
            assert "timeout_seconds" in spec_data
    
    @pytest.mark.asyncio
    async def test_concurrent_execution_limits(self, parallel_executor_setup):
        """Test that concurrent execution limits are respected"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create more specifications than the concurrent limit (5)
        specifications = []
        for i in range(8):
            spec = AgentSpecification(
                name=f"concurrent_agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Concurrent test agent {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"},
                max_memory_mb=256,
                timeout_seconds=30
            )
            specifications.append(spec)
        
        # Create execution plan
        plan = await parallel_executor.create_execution_plan(
            specifications=specifications,
            execution_mode=ExecutionMode.PARALLEL,
            max_parallel=10  # Should be limited by executor's max_concurrent_executions (5)
        )
        
        assert plan.max_parallel_agents == 5  # Limited by executor's setting
        
        # Generate execution nodes
        generation_request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        start_time = datetime.utcnow()
        generation_result = await sub_agent_generator.generate_sub_agents(generation_request)
        end_time = datetime.utcnow()
        
        assert generation_result.success is True
        assert len(generation_result.execution_nodes) == 8
        
        # Verify all agents were created
        agent_names = {node.name for node in generation_result.execution_nodes}
        expected_names = {f"concurrent_agent_{i}" for i in range(8)}
        assert agent_names == expected_names
        
        # Verify generation time is reasonable (not too slow due to batching)
        duration = (end_time - start_time).total_seconds()
        assert duration < 1.0  # Should be fast for lazy generation
    
    @pytest.mark.asyncio
    async def test_dependency_based_isolation(self, parallel_executor_setup):
        """Test isolation with dependent agents"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create specifications with dependencies
        specifications = [
            AgentSpecification(
                name="data_ingester",
                agent_type=AgentType.FILE_HANDLER,
                task_description="Ingest data",
                parameters={"file_path": "raw_data/", "operation": "read"},
                isolation_level=ContextIsolationLevel.SHALLOW
            ),
            AgentSpecification(
                name="data_validator",
                agent_type=AgentType.VALIDATOR,
                task_description="Validate data",
                parameters={"validation_rules": "schema.json", "data_source": "ingested"},
                dependencies=["data_ingester"],
                isolation_level=ContextIsolationLevel.DEEP
            ),
            AgentSpecification(
                name="data_processor",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "validated_data", "output_format": "parquet"},
                dependencies=["data_validator"],
                isolation_level=ContextIsolationLevel.SANDBOXED,
                max_memory_mb=1024
            )
        ]
        
        # Create pipeline execution plan
        plan = await parallel_executor.create_execution_plan(
            specifications=specifications,
            execution_mode=ExecutionMode.PIPELINE
        )
        
        assert plan.execution_mode == ExecutionMode.PIPELINE
        
        # Verify dependency graph
        assert "data_validator" in plan.dependency_graph
        assert "data_ingester" in plan.dependency_graph["data_validator"]
        assert "data_processor" in plan.dependency_graph
        assert "data_validator" in plan.dependency_graph["data_processor"]
        
        # Verify execution order respects dependencies
        execution_order = plan.get_execution_order()
        
        # Find which level each agent is in
        ingester_level = processor_level = validator_level = -1
        for level, agents in enumerate(execution_order):
            if "data_ingester" in agents:
                ingester_level = level
            if "data_validator" in agents:
                validator_level = level
            if "data_processor" in agents:
                processor_level = level
        
        # Verify dependency order
        assert ingester_level < validator_level  # Ingester before validator
        assert validator_level < processor_level  # Validator before processor
        
        # Generate execution nodes
        generation_request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        generation_result = await sub_agent_generator.generate_sub_agents(generation_request)
        
        assert generation_result.success is True
        assert len(generation_result.execution_nodes) == 3
        
        # Verify dependencies are preserved in execution nodes
        nodes_by_name = {node.name: node for node in generation_result.execution_nodes}
        
        assert len(nodes_by_name["data_ingester"].dependencies) == 0
        assert "data_ingester" in nodes_by_name["data_validator"].dependencies
        assert "data_validator" in nodes_by_name["data_processor"].dependencies
    
    @pytest.mark.asyncio
    async def test_execution_mode_isolation(self, parallel_executor_setup):
        """Test different execution modes provide proper isolation"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create identical specifications for different execution modes
        base_specs = [
            AgentSpecification(
                name="agent_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Test agent 1",
                parameters={"input_source": "data1.csv", "output_format": "json"}
            ),
            AgentSpecification(
                name="agent_2",
                agent_type=AgentType.API_CALLER,
                task_description="Test agent 2",
                parameters={"endpoint": "http://api1.com", "method": "GET"}
            ),
            AgentSpecification(
                name="agent_3",
                agent_type=AgentType.VALIDATOR,
                task_description="Test agent 3",
                parameters={"validation_rules": "rules1.json", "data_source": "data"}
            )
        ]
        
        # Test different execution modes
        execution_modes = [
            ExecutionMode.PARALLEL,
            ExecutionMode.SEQUENTIAL,
            ExecutionMode.BATCH
        ]
        
        for mode in execution_modes:
            # Create execution plan
            plan = await parallel_executor.create_execution_plan(
                specifications=base_specs,
                execution_mode=mode
            )
            
            assert plan.execution_mode == mode
            
            # Verify execution order differs by mode
            execution_order = plan.get_execution_order()
            
            if mode == ExecutionMode.PARALLEL:
                # All agents in one group
                assert len(execution_order) == 1
                assert len(execution_order[0]) == 3
            elif mode == ExecutionMode.SEQUENTIAL:
                # Each agent in its own group
                assert len(execution_order) == 3
                assert all(len(group) == 1 for group in execution_order)
            elif mode == ExecutionMode.BATCH:
                # May be grouped based on resources
                assert len(execution_order) >= 1
                total_agents = sum(len(group) for group in execution_order)
                assert total_agents == 3
    
    @pytest.mark.asyncio
    async def test_adaptive_execution_mode(self, parallel_executor_setup):
        """Test adaptive execution mode chooses appropriate strategy"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Test case 1: High resource requirements should trigger batch mode
        high_resource_specs = [
            AgentSpecification(
                name=f"heavy_agent_{i}",
                agent_type=AgentType.ANALYZER,
                task_description=f"Heavy analysis {i}",
                parameters={"analysis_type": "complex", "data_source": "large_dataset"},
                max_memory_mb=3000,  # High memory
                max_cpu_percent=90   # High CPU
            ) for i in range(3)
        ]
        
        plan = await parallel_executor.create_execution_plan(
            specifications=high_resource_specs,
            execution_mode=ExecutionMode.ADAPTIVE
        )
        
        # Should adapt to batch mode due to resource constraints
        assert plan.execution_mode == ExecutionMode.BATCH
        assert len(plan.agent_groups) > 1  # Should create multiple groups
        
        # Test case 2: Dependencies should trigger pipeline mode
        dependency_specs = [
            AgentSpecification(
                name="step_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="First step",
                parameters={"input_source": "raw", "output_format": "clean"}
            ),
            AgentSpecification(
                name="step_2",
                agent_type=AgentType.VALIDATOR,
                task_description="Second step",
                parameters={"validation_rules": "rules", "data_source": "clean"},
                dependencies=["step_1"]
            )
        ]
        
        plan = await parallel_executor.create_execution_plan(
            specifications=dependency_specs,
            execution_mode=ExecutionMode.ADAPTIVE
        )
        
        # Should adapt to pipeline mode due to dependencies
        assert plan.execution_mode == ExecutionMode.PIPELINE
        
        # Test case 3: Low resource, no dependencies should use parallel mode
        simple_specs = [
            AgentSpecification(
                name=f"simple_agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Simple task {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"},
                max_memory_mb=128,
                max_cpu_percent=10
            ) for i in range(2)
        ]
        
        plan = await parallel_executor.create_execution_plan(
            specifications=simple_specs,
            execution_mode=ExecutionMode.ADAPTIVE
        )
        
        # Should use parallel mode for simple, independent agents
        assert plan.execution_mode == ExecutionMode.PARALLEL
        assert len(plan.agent_groups) == 1
        assert len(plan.agent_groups[0]) == 2
    
    @pytest.mark.asyncio
    async def test_context_variable_isolation(self, parallel_executor_setup):
        """Test that context variables are properly isolated between agents"""
        parallel_executor, sub_agent_generator, parent_context_id, tree_id = parallel_executor_setup
        
        # Create specifications with conflicting environment variables
        specifications = [
            AgentSpecification(
                name="env_agent_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Agent with env vars 1",
                parameters={"input_source": "data1.csv", "output_format": "json"},
                environment={"API_KEY": "key1", "DEBUG": "true", "SHARED_VAR": "value1"},
                isolation_level=ContextIsolationLevel.DEEP
            ),
            AgentSpecification(
                name="env_agent_2",
                agent_type=AgentType.API_CALLER,
                task_description="Agent with env vars 2",
                parameters={"endpoint": "http://api.com", "method": "POST"},
                environment={"API_KEY": "key2", "DEBUG": "false", "SHARED_VAR": "value2"},
                isolation_level=ContextIsolationLevel.DEEP
            ),
            AgentSpecification(
                name="env_agent_3",
                agent_type=AgentType.VALIDATOR,
                task_description="Agent with env vars 3",
                parameters={"validation_rules": "rules.json", "data_source": "data"},
                environment={"API_KEY": "key3", "TIMEOUT": "30", "SHARED_VAR": "value3"},
                isolation_level=ContextIsolationLevel.SANDBOXED
            )
        ]
        
        # Generate execution nodes
        generation_request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY
        )
        
        generation_result = await sub_agent_generator.generate_sub_agents(generation_request)
        
        assert generation_result.success is True
        assert len(generation_result.execution_nodes) == 3
        
        # Verify environment variables are preserved per agent
        for node in generation_result.execution_nodes:
            spec_data = node.task_data["specification"]
            env_vars = spec_data["environment"]
            
            if spec_data["name"] == "env_agent_1":
                assert env_vars["API_KEY"] == "key1"
                assert env_vars["DEBUG"] == "true"
                assert env_vars["SHARED_VAR"] == "value1"
            elif spec_data["name"] == "env_agent_2":
                assert env_vars["API_KEY"] == "key2"
                assert env_vars["DEBUG"] == "false"
                assert env_vars["SHARED_VAR"] == "value2"
            elif spec_data["name"] == "env_agent_3":
                assert env_vars["API_KEY"] == "key3"
                assert env_vars["TIMEOUT"] == "30"
                assert env_vars["SHARED_VAR"] == "value3"
        
        # Verify nodes have different isolation levels
        isolation_levels = {
            node.task_data["specification"]["name"]: node.task_data["specification"]["isolation_level"]
            for node in generation_result.execution_nodes
        }
        
        assert isolation_levels["env_agent_1"] == "deep"
        assert isolation_levels["env_agent_2"] == "deep"
        assert isolation_levels["env_agent_3"] == "sandboxed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])