"""
Unit tests for SubAgentGenerator

These tests validate the sub-agent generation functionality including
specification validation, resource estimation, and agent lifecycle management.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from src.core.sub_agent_generator import SubAgentGenerator
from src.interfaces.sub_agent_generator import (
    AgentSpecification, GenerationRequest, AgentType, GenerationStrategy,
    ContextIsolationLevel, InvalidSpecificationError
)
from src.core.execution_tree import ExecutionStatus, ExecutionPriority, NodeType


class TestSubAgentGenerator:
    """Test SubAgentGenerator functionality"""
    
    @pytest.fixture
    def mock_state_store(self):
        """Mock state store"""
        mock = AsyncMock()
        mock.health_check.return_value = True
        return mock
    
    @pytest.fixture  
    def mock_context_manager(self):
        """Mock context manager"""
        mock = AsyncMock()
        
        # Mock context creation
        mock.fork_context.return_value = MagicMock(
            context_id="test_context_123",
            parent_id="parent_context",
            isolation_level=ContextIsolationLevel.SHALLOW,
            variables={},
            resource_limits={}
        )
        
        mock.get_context.return_value = MagicMock(
            context_id="parent_context",
            variables={"config": {"debug": True}}
        )
        
        mock.update_context.return_value = True
        mock.delete_context.return_value = True
        
        return mock
    
    @pytest.fixture
    def mock_execution_tree(self):
        """Mock execution tree"""
        mock = AsyncMock()
        
        # Mock tree operations
        mock.get_tree_snapshot.return_value = MagicMock(
            tree_id="test_tree_123",
            nodes={}
        )
        
        mock.add_node.return_value = True
        mock.update_node_status.return_value = True
        
        return mock
    
    @pytest.fixture
    def sub_agent_generator(self, mock_state_store, mock_context_manager, mock_execution_tree):
        """Create SubAgentGenerator instance with mocked dependencies"""
        return SubAgentGenerator(
            state_store=mock_state_store,
            context_manager=mock_context_manager,
            execution_tree=mock_execution_tree,
            max_concurrent_generations=10
        )
    
    @pytest.fixture
    def sample_specification(self):
        """Sample agent specification"""
        return AgentSpecification(
            name="test_data_processor",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process CSV data",
            parameters={
                "input_source": "data.csv",
                "output_format": "json"
            },
            environment={
                "debug": True,
                "log_level": "INFO"
            },
            max_memory_mb=512,
            max_cpu_percent=50,
            timeout_seconds=300,
            priority=ExecutionPriority.NORMAL,
            isolation_level=ContextIsolationLevel.DEEP,
            tags=["data", "processing"]
        )
    
    @pytest.fixture
    def sample_generation_request(self, sample_specification):
        """Sample generation request"""
        return GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=[sample_specification],
            generation_strategy=GenerationStrategy.IMMEDIATE,
            max_parallel=5
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, sub_agent_generator):
        """Test SubAgentGenerator initialization"""
        assert sub_agent_generator.max_concurrent_generations == 10
        assert sub_agent_generator.default_timeout_seconds == 300
        assert len(sub_agent_generator._templates) == len(AgentType)
        assert AgentType.DATA_PROCESSOR in sub_agent_generator._templates
    
    @pytest.mark.asyncio
    async def test_get_generation_templates(self, sub_agent_generator):
        """Test getting generation templates"""
        templates = await sub_agent_generator.get_generation_templates()
        
        assert isinstance(templates, dict)
        assert AgentType.DATA_PROCESSOR in templates
        assert AgentType.API_CALLER in templates
        
        # Check template structure
        data_processor_template = templates[AgentType.DATA_PROCESSOR]
        assert "class_name" in data_processor_template
        assert "required_params" in data_processor_template
        assert "default_memory_mb" in data_processor_template
        assert "capabilities" in data_processor_template
    
    @pytest.mark.asyncio
    async def test_validate_specification_valid(self, sub_agent_generator, sample_specification):
        """Test validating a valid specification"""
        errors = await sub_agent_generator.validate_specification(sample_specification)
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_specification_missing_name(self, sub_agent_generator):
        """Test validating specification with missing name"""
        spec = AgentSpecification(
            name="",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data"
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert "Agent name is required" in errors
    
    @pytest.mark.asyncio
    async def test_validate_specification_missing_required_params(self, sub_agent_generator):
        """Test validating specification with missing required parameters"""
        spec = AgentSpecification(
            name="test_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={"output_format": "json"}  # Missing input_source
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert any("Missing required parameter: input_source" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_specification_invalid_resources(self, sub_agent_generator):
        """Test validating specification with invalid resource limits"""
        spec = AgentSpecification(
            name="test_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={"input_source": "data.csv", "output_format": "json"},
            max_memory_mb=-100,  # Invalid
            max_cpu_percent=150,  # Invalid
            timeout_seconds=-30   # Invalid
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert "Memory limit must be positive" in errors
        assert "CPU percent must be between 1 and 100" in errors
        assert "Timeout must be positive" in errors
    
    @pytest.mark.asyncio
    async def test_estimate_resource_usage(self, sub_agent_generator):
        """Test resource usage estimation"""
        specs = [
            AgentSpecification(
                name="agent1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"},
                max_memory_mb=256,
                max_cpu_percent=25,
                timeout_seconds=300
            ),
            AgentSpecification(
                name="agent2",
                agent_type=AgentType.API_CALLER,
                task_description="Call API",
                parameters={"endpoint": "http://api.example.com", "method": "GET"},
                max_memory_mb=128,
                max_cpu_percent=15,
                timeout_seconds=120
            )
        ]
        
        estimates = await sub_agent_generator.estimate_resource_usage(specs)
        
        assert estimates["total_memory_mb"] == 384  # 256 + 128
        assert estimates["total_cpu_percent"] == 40   # 25 + 15
        assert estimates["estimated_time_seconds"] == 300  # max(300, 120)
        assert estimates["agent_count"] == 2
        assert "estimated_cost" in estimates
    
    @pytest.mark.asyncio
    async def test_generate_sub_agents_immediate_success(self, sub_agent_generator, sample_generation_request):
        """Test successful immediate sub-agent generation"""
        result = await sub_agent_generator.generate_sub_agents(sample_generation_request)
        
        assert result.success is True
        assert result.total_agents_created == 1
        assert len(result.generated_agents) == 1
        assert len(result.execution_nodes) == 1
        assert len(result.errors) == 0
        
        # Check generated agent structure
        agent = result.generated_agents[0]
        assert agent["name"] == "test_data_processor"
        assert agent["type"] == "data_processor"
        assert "agent_id" in agent
        assert "context_id" in agent
        assert "node_id" in agent
    
    @pytest.mark.asyncio
    async def test_generate_sub_agents_batch_strategy(self, sub_agent_generator, mock_context_manager, mock_execution_tree):
        """Test batch generation strategy"""
        # Create multiple specifications
        specs = []
        for i in range(7):  # More than batch size
            spec = AgentSpecification(
                name=f"agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Process data {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"}
            )
            specs.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=specs,
            generation_strategy=GenerationStrategy.BATCH,
            batch_size=3
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 7
        assert len(result.generated_agents) == 7
    
    @pytest.mark.asyncio
    async def test_generate_sub_agents_lazy_strategy(self, sub_agent_generator, sample_specification):
        """Test lazy generation strategy"""
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=[sample_specification],
            generation_strategy=GenerationStrategy.LAZY
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        assert result.success is True
        assert len(result.execution_nodes) == 1
        assert len(result.generated_agents) == 0  # No agents created in lazy mode
        assert "Lazy generation" in " ".join(result.warnings)
        
        # Check execution node has lazy flag
        node = result.execution_nodes[0]
        assert node.task_data["lazy_generation"] is True
        assert node.agent_id is None  # No agent created yet
    
    @pytest.mark.asyncio
    async def test_generate_sub_agents_validation_failure(self, sub_agent_generator):
        """Test generation with validation failures"""
        # Invalid specification (missing required params)
        invalid_spec = AgentSpecification(
            name="invalid_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={}  # Missing required parameters
        )
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123", 
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=[invalid_spec]
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        assert result.success is False
        assert len(result.errors) > 0
        assert result.total_agents_created == 0
    
    @pytest.mark.asyncio
    async def test_generate_sub_agents_concurrent_limit(self, sub_agent_generator):
        """Test concurrent generation limit"""
        # Create many specifications
        specs = []
        for i in range(15):  # More than max_concurrent_generations (10)
            spec = AgentSpecification(
                name=f"agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Process data {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"}
            )
            specs.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context", 
            tree_id="test_tree_123",
            specifications=specs,
            max_parallel=20  # Should be limited to max_concurrent_generations
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        # Should succeed but respect concurrency limits
        assert result.success is True
        assert result.total_agents_created == 15
    
    @pytest.mark.asyncio
    async def test_get_sub_agent_status(self, sub_agent_generator, sample_generation_request):
        """Test getting sub-agent status"""
        # Generate an agent first
        result = await sub_agent_generator.generate_sub_agents(sample_generation_request)
        assert result.success is True
        
        agent_id = result.generated_agents[0]["agent_id"]
        
        # Get status
        status = await sub_agent_generator.get_sub_agent_status(agent_id)
        
        assert status is not None
        assert status.agent_id == agent_id
        assert status.name == "test_data_processor"
        assert status.agent_type == AgentType.DATA_PROCESSOR
        assert status.status == ExecutionStatus.PENDING
        assert status.parent_agent_id == "parent_agent_123"
    
    @pytest.mark.asyncio
    async def test_list_sub_agents(self, sub_agent_generator):
        """Test listing sub-agents for a parent"""
        # Generate multiple agents
        specs = []
        for i in range(3):
            spec = AgentSpecification(
                name=f"agent_{i}",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description=f"Process data {i}",
                parameters={"input_source": f"data_{i}.csv", "output_format": "json"}
            )
            specs.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123", 
            specifications=specs
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        assert result.success is True
        
        # List sub-agents
        sub_agents = await sub_agent_generator.list_sub_agents("parent_agent_123")
        
        assert len(sub_agents) == 3
        for status in sub_agents:
            assert status.parent_agent_id == "parent_agent_123"
            assert status.agent_type == AgentType.DATA_PROCESSOR
    
    @pytest.mark.asyncio
    async def test_terminate_sub_agent(self, sub_agent_generator, sample_generation_request, mock_execution_tree, mock_context_manager):
        """Test terminating a sub-agent"""
        # Generate an agent first
        result = await sub_agent_generator.generate_sub_agents(sample_generation_request)
        assert result.success is True
        
        agent_id = result.generated_agents[0]["agent_id"]
        
        # Terminate the agent
        success = await sub_agent_generator.terminate_sub_agent(agent_id, "Test termination")
        
        assert success is True
        
        # Verify calls to dependencies
        mock_execution_tree.update_node_status.assert_called()
        mock_context_manager.delete_context.assert_called()
        
        # Check agent status
        status = await sub_agent_generator.get_sub_agent_status(agent_id)
        assert status.status == ExecutionStatus.CANCELLED
        assert status.error_data["reason"] == "Test termination"
    
    @pytest.mark.asyncio
    async def test_pause_and_resume_sub_agent(self, sub_agent_generator, sample_generation_request, mock_execution_tree):
        """Test pausing and resuming a sub-agent"""
        # Generate an agent first
        result = await sub_agent_generator.generate_sub_agents(sample_generation_request)
        assert result.success is True
        
        agent_id = result.generated_agents[0]["agent_id"]
        
        # Pause the agent
        success = await sub_agent_generator.pause_sub_agent(agent_id)
        assert success is True
        
        status = await sub_agent_generator.get_sub_agent_status(agent_id)
        assert status.status == ExecutionStatus.PAUSED
        
        # Resume the agent
        success = await sub_agent_generator.resume_sub_agent(agent_id)
        assert success is True
        
        status = await sub_agent_generator.get_sub_agent_status(agent_id)
        assert status.status == ExecutionStatus.RUNNING
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_agents(self, sub_agent_generator):
        """Test cleaning up completed agents"""
        # Manually add some completed agents to the tracking
        from src.interfaces.sub_agent_generator import SubAgentStatus
        
        # Recent completed agent (should not be cleaned)
        recent_agent = SubAgentStatus(
            agent_id="recent_agent",
            name="recent",
            agent_type=AgentType.DATA_PROCESSOR,
            status=ExecutionStatus.COMPLETED,
            node_id="node_1",
            context_id="ctx_1",
            parent_agent_id="parent_1",
            completed_at=datetime.utcnow()
        )
        
        # Old completed agent (should be cleaned)
        old_agent = SubAgentStatus(
            agent_id="old_agent",
            name="old",
            agent_type=AgentType.DATA_PROCESSOR,
            status=ExecutionStatus.COMPLETED,
            node_id="node_2", 
            context_id="ctx_2",
            parent_agent_id="parent_1",
            completed_at=datetime.utcnow() - timedelta(hours=25)
        )
        
        sub_agent_generator._active_agents["recent_agent"] = recent_agent
        sub_agent_generator._active_agents["old_agent"] = old_agent
        
        # Cleanup with max_age of 24 hours
        cleaned_count = await sub_agent_generator.cleanup_completed_agents(max_age_hours=24)
        
        assert cleaned_count == 1
        assert "recent_agent" in sub_agent_generator._active_agents
        assert "old_agent" not in sub_agent_generator._active_agents
    
    @pytest.mark.asyncio
    async def test_agent_type_templates_coverage(self, sub_agent_generator):
        """Test that all agent types have templates"""
        templates = await sub_agent_generator.get_generation_templates()
        
        for agent_type in AgentType:
            assert agent_type in templates
            template = templates[agent_type]
            
            # Check required template fields
            assert "class_name" in template
            assert "required_params" in template
            assert "default_memory_mb" in template
            assert "default_timeout" in template
            assert "capabilities" in template
            
            # Check data types
            assert isinstance(template["required_params"], list)
            assert isinstance(template["default_memory_mb"], int)
            assert isinstance(template["default_timeout"], int)
            assert isinstance(template["capabilities"], list)
    
    @pytest.mark.asyncio
    async def test_generation_with_dependencies(self, sub_agent_generator):
        """Test generating agents with dependencies"""
        # Create specs with dependencies
        spec1 = AgentSpecification(
            name="agent_1",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={"input_source": "data.csv", "output_format": "json"}
        )
        
        spec2 = AgentSpecification(
            name="agent_2", 
            agent_type=AgentType.VALIDATOR,
            task_description="Validate processed data",
            parameters={"validation_rules": "schema.json", "data_source": "processed_data"},
            dependencies=["agent_1"]  # Depends on agent_1
        )
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=[spec1, spec2]
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        assert result.success is True
        assert result.total_agents_created == 2
        
        # Check that agent_2 has dependency on agent_1
        agent_2_node = None
        for node in result.execution_nodes:
            if node.name == "agent_2":
                agent_2_node = node
                break
        
        assert agent_2_node is not None
        assert "agent_1" in agent_2_node.dependencies
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_tree(self, sub_agent_generator, mock_execution_tree):
        """Test error handling when tree doesn't exist"""
        # Mock tree not found
        mock_execution_tree.get_tree_snapshot.return_value = None
        
        spec = AgentSpecification(
            name="test_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={"input_source": "data.csv", "output_format": "json"}
        )
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="non_existent_tree",
            specifications=[spec]
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        assert result.success is False
        assert any("not found" in error for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_resource_limit_enforcement(self, sub_agent_generator):
        """Test resource limit enforcement"""
        # Create specs that would exceed resource limits
        specs = []
        for i in range(50):  # Create many high-resource agents
            spec = AgentSpecification(
                name=f"heavy_agent_{i}",
                agent_type=AgentType.ANALYZER,
                task_description="Heavy analysis",
                parameters={"analysis_type": "complex", "data_source": "large_dataset"},
                max_memory_mb=1024,  # 1GB each
                max_cpu_percent=100  # 100% each
            )
            specs.append(spec)
        
        request = GenerationRequest(
            parent_agent_id="parent_agent_123",
            parent_context_id="parent_context",
            tree_id="test_tree_123",
            specifications=specs
        )
        
        result = await sub_agent_generator.generate_sub_agents(request)
        
        # Should fail due to resource limits
        assert result.success is False
        assert any("resource" in error.lower() for error in result.errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])