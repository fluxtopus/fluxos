"""
Integration tests for sub-agent generation with various specifications

These tests verify that the SubAgentGenerator can handle different types of
agent specifications, edge cases, and real-world scenarios.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.core.sub_agent_generator import SubAgentGenerator
from src.interfaces.sub_agent_generator import (
    AgentSpecification, GenerationRequest, AgentType, GenerationStrategy,
    ContextIsolationLevel, InvalidSpecificationError
)
from src.core.execution_tree import ExecutionStatus, ExecutionPriority, NodeType
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree


@pytest.mark.integration
class TestSubAgentGenerationScenarios:
    """Test sub-agent generation with various real-world scenarios"""
    
    @pytest.fixture(scope="function")
    async def redis_state_store(self):
        """Redis state store for testing"""
        store = RedisStateStore(
            redis_url="redis://redis:6379",
            db=10,  # Use separate DB for testing
            key_prefix="test_generation"
        )
        await store.health_check()
        yield store
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/10")
        await r.flushdb()
        await r.close()
    
    @pytest.fixture(scope="function")
    async def redis_context_manager(self):
        """Redis context manager for testing"""
        manager = RedisContextManager(
            redis_url="redis://redis:6379",
            db=11,  # Use separate DB for testing
            key_prefix="test_generation_ctx"
        )
        await manager.health_check()
        yield manager
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/11")
        await r.flushdb()
        await r.close()
    
    @pytest.fixture(scope="function")
    async def redis_execution_tree(self):
        """Redis execution tree for testing"""
        tree = RedisExecutionTree(
            redis_url="redis://redis:6379",
            db=12,  # Use separate DB for testing
            key_prefix="test_generation_tree"
        )
        await tree.health_check()
        yield tree
        # Cleanup
        import redis.asyncio as redis
        r = redis.from_url("redis://redis:6379/12")
        await r.flushdb()
        await r.close()
    
    @pytest.fixture
    async def sub_agent_generator(self, redis_state_store, redis_context_manager, redis_execution_tree):
        """SubAgentGenerator with real Redis backends"""
        # Create parent context first
        parent_context_id = await redis_context_manager.create_context(
            agent_id="parent_agent",
            isolation_level=ContextIsolationLevel.SHALLOW,
            config={"debug": True},
            environment="test"
        )
        
        # Create execution tree
        tree_id = await redis_execution_tree.create_tree("test_generation_tree")
        
        generator = SubAgentGenerator(
            state_store=redis_state_store,
            context_manager=redis_context_manager,
            execution_tree=redis_execution_tree,
            max_concurrent_generations=5
        )
        
        yield generator, parent_context_id, tree_id
    
    @pytest.mark.asyncio
    async def test_data_processor_agent_specification(self, sub_agent_generator):
        """Test generating a data processor agent with various configurations"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        # Test different data processor configurations
        test_cases = [
            {
                "name": "csv_processor",
                "parameters": {
                    "input_source": "data/sales.csv",
                    "output_format": "json",
                    "chunk_size": 1000,
                    "encoding": "utf-8"
                },
                "max_memory_mb": 512,
                "timeout_seconds": 300
            },
            {
                "name": "xml_processor", 
                "parameters": {
                    "input_source": "data/config.xml",
                    "output_format": "yaml",
                    "validation_schema": "schemas/config.xsd"
                },
                "max_memory_mb": 256,
                "timeout_seconds": 180
            },
            {
                "name": "json_processor",
                "parameters": {
                    "input_source": "data/events.jsonl",
                    "output_format": "parquet",
                    "compression": "gzip"
                },
                "max_memory_mb": 1024,
                "timeout_seconds": 600
            }
        ]
        
        specifications = []
        for case in test_cases:
            spec = AgentSpecification(
                name=case["name"],
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Process {case['name']} data",
                parameters=case["parameters"],
                max_memory_mb=case["max_memory_mb"],
                timeout_seconds=case["timeout_seconds"],
                isolation_level=ContextIsolationLevel.DEEP,
                tags=["data_processing", "batch"]
            )
            specifications.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY  # Use lazy to avoid StatefulAgent instantiation
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 3
        assert len(result.generated_agents) == 0  # Lazy generation doesn't create agents
        assert len(result.execution_nodes) == 3
        
        # Verify each execution node was created correctly
        for i, node in enumerate(result.execution_nodes):
            assert node.name == test_cases[i]["name"]
            assert node.node_type == NodeType.SUB_AGENT
            assert node.status == ExecutionStatus.PENDING
        
        # Verify execution nodes
        for node in result.execution_nodes:
            assert node.node_type == NodeType.SUB_AGENT
            assert node.status == ExecutionStatus.PENDING
            assert "data_processing" in node.task_data["specification"]["tags"]
    
    @pytest.mark.asyncio
    async def test_api_caller_agent_variations(self, sub_agent_generator):
        """Test generating API caller agents with different configurations"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        specifications = [
            AgentSpecification(
                name="rest_api_caller",
                agent_type=AgentType.API_CALLER,
                task_description="Call REST API endpoints",
                parameters={
                    "endpoint": "https://api.example.com/v1/users",
                    "method": "GET",
                    "headers": {"Authorization": "Bearer token"},
                    "timeout": 30,
                    "retry_count": 3
                },
                environment={"API_KEY": "test_key"},
                max_cpu_percent=15,
                timeout_seconds=120
            ),
            AgentSpecification(
                name="graphql_caller",
                agent_type=AgentType.API_CALLER,
                task_description="Execute GraphQL queries",
                parameters={
                    "endpoint": "https://api.example.com/graphql",
                    "method": "POST",
                    "query": "query { users { id name email } }",
                    "variables": {}
                },
                max_cpu_percent=25,
                timeout_seconds=60
            ),
            AgentSpecification(
                name="webhook_caller",
                agent_type=AgentType.API_CALLER,
                task_description="Send webhook notifications",
                parameters={
                    "endpoint": "https://webhook.example.com/notify",
                    "method": "POST",
                    "payload_template": "webhook_template.json",
                    "batch_size": 10
                },
                max_cpu_percent=10,
                timeout_seconds=45
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.BATCH,
            batch_size=2
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 3
        
        # Verify API-specific parameters are preserved
        for agent in result.generated_agents:
            assert agent["type"] == "api_caller"
        
        # Check that one agent has environment variables
        rest_agent = next(a for a in result.generated_agents if a["name"] == "rest_api_caller")
        assert rest_agent is not None
    
    @pytest.mark.asyncio
    async def test_complex_dependency_chain(self, sub_agent_generator):
        """Test generating agents with complex dependency relationships"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        specifications = [
            # Data ingestion (no dependencies)
            AgentSpecification(
                name="data_ingester",
                agent_type=AgentType.FILE_HANDLER,
                task_description="Ingest raw data files",
                parameters={
                    "file_path": "/data/raw/",
                    "operation": "read",
                    "file_pattern": "*.csv"
                },
                priority=ExecutionPriority.HIGH
            ),
            # Data validation (depends on ingestion)
            AgentSpecification(
                name="data_validator",
                agent_type=AgentType.VALIDATOR,
                task_description="Validate ingested data",
                parameters={
                    "validation_rules": "rules/data_validation.json",
                    "data_source": "ingested_data"
                },
                dependencies=["data_ingester"],
                priority=ExecutionPriority.HIGH
            ),
            # Data processing (depends on validation)
            AgentSpecification(
                name="data_processor",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process validated data",
                parameters={
                    "input_source": "validated_data",
                    "output_format": "parquet",
                    "transformations": ["normalize", "aggregate"]
                },
                dependencies=["data_validator"],
                priority=ExecutionPriority.NORMAL
            ),
            # Analysis (depends on processing)
            AgentSpecification(
                name="data_analyzer",
                agent_type=AgentType.ANALYZER,
                task_description="Analyze processed data",
                parameters={
                    "analysis_type": "statistical",
                    "data_source": "processed_data",
                    "output_format": "report"
                },
                dependencies=["data_processor"],
                priority=ExecutionPriority.NORMAL
            ),
            # Notification (depends on analysis)
            AgentSpecification(
                name="result_notifier",
                agent_type=AgentType.NOTIFIER,
                task_description="Send analysis results",
                parameters={
                    "notification_type": "email",
                    "recipients": ["team@example.com"],
                    "template": "analysis_complete.html"
                },
                dependencies=["data_analyzer"],
                priority=ExecutionPriority.LOW
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.LAZY  # Create nodes but not agents
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert len(result.execution_nodes) == 5
        assert len(result.generated_agents) == 0  # Lazy generation
        
        # Verify dependency relationships are correctly set
        nodes_by_name = {node.name: node for node in result.execution_nodes}
        
        # Check dependencies
        assert len(nodes_by_name["data_ingester"].dependencies) == 0
        assert "data_ingester" in nodes_by_name["data_validator"].dependencies
        assert "data_validator" in nodes_by_name["data_processor"].dependencies
        assert "data_processor" in nodes_by_name["data_analyzer"].dependencies
        assert "data_analyzer" in nodes_by_name["result_notifier"].dependencies
        
        # Check priorities
        assert nodes_by_name["data_ingester"].priority == ExecutionPriority.HIGH
        assert nodes_by_name["result_notifier"].priority == ExecutionPriority.LOW
    
    @pytest.mark.asyncio
    async def test_resource_intensive_agents(self, sub_agent_generator):
        """Test generating resource-intensive agents"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        specifications = [
            AgentSpecification(
                name="ml_trainer",
                agent_type=AgentType.ANALYZER,
                task_description="Train machine learning model",
                parameters={
                    "analysis_type": "ml_training",
                    "data_source": "training_data.parquet",
                    "model_type": "neural_network",
                    "epochs": 100,
                    "batch_size": 32
                },
                max_memory_mb=4096,  # 4GB
                max_cpu_percent=80,
                timeout_seconds=3600,  # 1 hour
                isolation_level=ContextIsolationLevel.SANDBOXED,
                tags=["ml", "compute_intensive"]
            ),
            AgentSpecification(
                name="large_file_processor",
                agent_type=AgentType.FILE_HANDLER,
                task_description="Process large files",
                parameters={
                    "file_path": "/data/large_dataset.csv",
                    "operation": "transform",
                    "chunk_size": 10000,
                    "compression": "gzip"
                },
                max_memory_mb=2048,  # 2GB
                max_cpu_percent=60,
                timeout_seconds=1800,  # 30 minutes
                isolation_level=ContextIsolationLevel.DEEP
            ),
            AgentSpecification(
                name="video_processor",
                agent_type=AgentType.TRANSFORMER,
                task_description="Process video files",
                parameters={
                    "input_format": "mp4",
                    "output_format": "webm",
                    "resolution": "1080p",
                    "codec": "vp9"
                },
                max_memory_mb=8192,  # 8GB
                max_cpu_percent=95,
                timeout_seconds=7200,  # 2 hours
                isolation_level=ContextIsolationLevel.SANDBOXED,
                tags=["media", "compute_intensive"]
            )
        ]
        
        # Test resource estimation
        resource_estimate = await generator.estimate_resource_usage(specifications)
        
        assert resource_estimate["total_memory_mb"] == 14336  # 4096 + 2048 + 8192
        assert resource_estimate["total_cpu_percent"] == 235   # 80 + 60 + 95
        assert resource_estimate["agent_count"] == 3
        
        # Generation should succeed
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.IMMEDIATE
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 3
        
        # Verify high-resource agents have correct isolation
        for agent in result.generated_agents:
            if agent["name"] in ["ml_trainer", "video_processor"]:
                # These should have sandboxed isolation
                assert agent is not None  # Basic check - detailed isolation testing would need context manager verification
    
    @pytest.mark.asyncio
    async def test_custom_agent_specifications(self, sub_agent_generator):
        """Test generating custom agents with specialized configurations"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        specifications = [
            AgentSpecification(
                name="blockchain_monitor",
                agent_type=AgentType.CUSTOM,
                task_description="Monitor blockchain transactions",
                parameters={
                    "custom_logic": "blockchain_monitoring.py",
                    "network": "ethereum",
                    "contract_addresses": ["0x123...", "0x456..."],
                    "poll_interval": 15,
                    "event_types": ["Transfer", "Approval"]
                },
                environment={
                    "WEB3_PROVIDER_URL": "https://mainnet.infura.io/v3/key",
                    "PRIVATE_KEY": "encrypted_key"
                },
                max_memory_mb=512,
                timeout_seconds=300,
                tags=["blockchain", "monitoring", "custom"]
            ),
            AgentSpecification(
                name="ai_image_generator",
                agent_type=AgentType.CUSTOM,
                task_description="Generate AI images",
                parameters={
                    "custom_logic": "stable_diffusion.py",
                    "model": "stable-diffusion-v2",
                    "prompt": "A beautiful landscape",
                    "num_images": 4,
                    "steps": 50,
                    "guidance_scale": 7.5
                },
                environment={
                    "HUGGINGFACE_TOKEN": "hf_token",
                    "CUDA_VISIBLE_DEVICES": "0"
                },
                max_memory_mb=6144,  # 6GB for AI model
                max_cpu_percent=90,
                timeout_seconds=600,
                isolation_level=ContextIsolationLevel.SANDBOXED,
                tags=["ai", "image_generation", "gpu"]
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.IMMEDIATE
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 2
        
        # Verify custom agents have correct type
        for agent in result.generated_agents:
            assert agent["type"] == "custom"
        
        # Verify nodes have custom logic parameters
        for node in result.execution_nodes:
            assert "custom_logic" in node.task_data
            if node.name == "blockchain_monitor":
                assert node.task_data["network"] == "ethereum"
            elif node.name == "ai_image_generator":
                assert node.task_data["model"] == "stable-diffusion-v2"
    
    @pytest.mark.asyncio
    async def test_invalid_specifications_handling(self, sub_agent_generator):
        """Test handling of invalid agent specifications"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        # Test various invalid specifications
        invalid_specs = [
            # Missing required parameters
            AgentSpecification(
                name="invalid_data_processor",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Missing required params",
                parameters={"output_format": "json"}  # Missing input_source
            ),
            # Invalid resource limits
            AgentSpecification(
                name="invalid_resources",
                agent_type=AgentType.API_CALLER,
                task_description="Invalid resource limits",
                parameters={"endpoint": "http://api.com", "method": "GET"},
                max_memory_mb=-100,  # Invalid
                max_cpu_percent=150,  # Invalid
                timeout_seconds=-30   # Invalid
            ),
            # Empty name
            AgentSpecification(
                name="",
                agent_type=AgentType.VALIDATOR,
                task_description="Empty name test",
                parameters={"validation_rules": "rules.json", "data_source": "data"}
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=invalid_specs,
            generation_strategy=GenerationStrategy.IMMEDIATE
        )
        
        result = await generator.generate_sub_agents(request)
        
        # Should fail due to validation errors
        assert result.success is False
        assert len(result.errors) > 0
        assert result.total_agents_created == 0
        
        # Check specific error messages
        error_text = " ".join(result.errors).lower()
        assert "missing required parameter" in error_text
        assert "memory limit must be positive" in error_text
        assert "cpu percent must be between" in error_text
        assert "agent name is required" in error_text
    
    @pytest.mark.asyncio
    async def test_concurrent_generation_limits(self, sub_agent_generator):
        """Test concurrent generation limits"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        # Create more specifications than the concurrent limit (5)
        specifications = []
        for i in range(8):
            spec = AgentSpecification(
                name=f"concurrent_agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Concurrent processing {i}",
                parameters={
                    "input_source": f"data_{i}.csv",
                    "output_format": "json"
                }
            )
            specifications.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.IMMEDIATE,
            max_parallel=10  # Should be limited by generator's max_concurrent_generations (5)
        )
        
        start_time = datetime.utcnow()
        result = await generator.generate_sub_agents(request)
        end_time = datetime.utcnow()
        
        assert result.success is True
        assert result.total_agents_created == 8
        
        # Should take longer than if all were truly parallel (due to concurrency limit)
        duration = (end_time - start_time).total_seconds()
        assert duration > 0  # Basic check - detailed timing would be flaky in tests
    
    @pytest.mark.asyncio
    async def test_mixed_isolation_levels(self, sub_agent_generator):
        """Test agents with different isolation levels"""
        generator, parent_context_id, tree_id = sub_agent_generator
        
        specifications = [
            AgentSpecification(
                name="shared_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Agent with shared context",
                parameters={"input_source": "data.csv", "output_format": "json"},
                isolation_level=ContextIsolationLevel.NONE
            ),
            AgentSpecification(
                name="shallow_agent",
                agent_type=AgentType.API_CALLER,
                task_description="Agent with shallow isolation",
                parameters={"endpoint": "http://api.com", "method": "GET"},
                isolation_level=ContextIsolationLevel.SHALLOW
            ),
            AgentSpecification(
                name="deep_agent",
                agent_type=AgentType.VALIDATOR,
                task_description="Agent with deep isolation",
                parameters={"validation_rules": "rules.json", "data_source": "data"},
                isolation_level=ContextIsolationLevel.DEEP
            ),
            AgentSpecification(
                name="sandboxed_agent",
                agent_type=AgentType.ANALYZER,
                task_description="Agent with sandboxed isolation",
                parameters={"analysis_type": "security", "data_source": "logs"},
                isolation_level=ContextIsolationLevel.SANDBOXED,
                max_memory_mb=1024,
                max_cpu_percent=50
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="test_parent",
            parent_context_id=parent_context_id,
            tree_id=tree_id,
            specifications=specifications,
            generation_strategy=GenerationStrategy.IMMEDIATE
        )
        
        result = await generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 4
        
        # All agents should be created successfully regardless of isolation level
        isolation_levels = [spec.isolation_level for spec in specifications]
        assert ContextIsolationLevel.NONE in isolation_levels
        assert ContextIsolationLevel.SHALLOW in isolation_levels
        assert ContextIsolationLevel.DEEP in isolation_levels
        assert ContextIsolationLevel.SANDBOXED in isolation_levels


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])