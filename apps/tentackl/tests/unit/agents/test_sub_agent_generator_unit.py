"""
Unit tests for SubAgentGenerator

These tests focus on individual methods and components of the SubAgentGenerator
in isolation, using mocks for dependencies.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.core.sub_agent_generator import SubAgentGenerator
from src.interfaces.sub_agent_generator import (
    AgentSpecification, GenerationRequest, AgentType, GenerationStrategy,
    ContextIsolationLevel, SubAgentStatus
)
from src.core.execution_tree import ExecutionStatus, ExecutionPriority, NodeType


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for SubAgentGenerator"""
    mock_state_store = AsyncMock()
    mock_context_manager = AsyncMock()
    mock_execution_tree = AsyncMock()
    
    # Setup basic mock behaviors
    mock_state_store.health_check.return_value = True
    mock_context_manager.health_check.return_value = True
    mock_execution_tree.health_check.return_value = True
    
    mock_context_manager.create_context.return_value = "test_context_id"
    mock_context_manager.fork_context.return_value = "child_context_id"
    mock_execution_tree.create_tree.return_value = "test_tree_id"
    mock_execution_tree.add_node.return_value = True
    
    return mock_state_store, mock_context_manager, mock_execution_tree


@pytest.fixture
def sub_agent_generator(mock_dependencies):
    """Create SubAgentGenerator with mocked dependencies"""
    state_store, context_manager, execution_tree = mock_dependencies
    
    generator = SubAgentGenerator(
        state_store=state_store,
        context_manager=context_manager,
        execution_tree=execution_tree,
        max_concurrent_generations=5
    )
    
    return generator


class TestSubAgentGeneratorUnit:
    """Unit tests for SubAgentGenerator methods"""
    
    def test_initialization(self, mock_dependencies):
        """Test SubAgentGenerator initialization"""
        state_store, context_manager, execution_tree = mock_dependencies
        
        generator = SubAgentGenerator(
            state_store=state_store,
            context_manager=context_manager,
            execution_tree=execution_tree,
            max_concurrent_generations=10,
            default_timeout_seconds=600,
            resource_monitor_interval=2.0
        )
        
        assert generator.state_store == state_store
        assert generator.context_manager == context_manager
        assert generator.execution_tree == execution_tree
        assert generator.max_concurrent_generations == 10
        assert generator.default_timeout_seconds == 600
        assert generator.resource_monitor_interval == 2.0
        
        # Check templates are initialized
        assert AgentType.DATA_PROCESSOR in generator._templates
        assert AgentType.API_CALLER in generator._templates
        assert AgentType.CUSTOM in generator._templates
        
        # Verify template structure
        data_processor_template = generator._templates[AgentType.DATA_PROCESSOR]
        assert "class_name" in data_processor_template
        assert "required_params" in data_processor_template
        assert "default_memory_mb" in data_processor_template
        assert "capabilities" in data_processor_template
    
    @pytest.mark.asyncio
    async def test_validate_specification_valid(self, sub_agent_generator):
        """Test specification validation with valid specifications"""
        # Valid DATA_PROCESSOR specification
        spec = AgentSpecification(
            name="test_processor",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={
                "input_source": "data.csv",
                "output_format": "json"
            },
            max_memory_mb=512,
            max_cpu_percent=50,
            timeout_seconds=300
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_specification_missing_name(self, sub_agent_generator):
        """Test specification validation with missing name"""
        spec = AgentSpecification(
            name="",  # Empty name
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={
                "input_source": "data.csv",
                "output_format": "json"
            }
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert len(errors) > 0
        assert any("name is required" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_specification_missing_description(self, sub_agent_generator):
        """Test specification validation with missing task description"""
        spec = AgentSpecification(
            name="test_processor",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="",  # Empty description
            parameters={
                "input_source": "data.csv",
                "output_format": "json"
            }
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert len(errors) > 0
        assert any("task description is required" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_specification_missing_required_params(self, sub_agent_generator):
        """Test specification validation with missing required parameters"""
        spec = AgentSpecification(
            name="test_processor",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={
                "output_format": "json"  # Missing input_source
            }
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert len(errors) > 0
        assert any("missing required parameter" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_specification_invalid_resource_limits(self, sub_agent_generator):
        """Test specification validation with invalid resource limits"""
        spec = AgentSpecification(
            name="test_processor",
            agent_type=AgentType.DATA_PROCESSOR,
            task_description="Process data",
            parameters={
                "input_source": "data.csv",
                "output_format": "json"
            },
            max_memory_mb=-100,  # Invalid negative memory
            max_cpu_percent=150,  # Invalid > 100% CPU
            timeout_seconds=0     # Invalid zero timeout
        )
        
        errors = await sub_agent_generator.validate_specification(spec)
        assert len(errors) >= 3
        
        error_text = " ".join(errors).lower()
        assert "memory limit must be positive" in error_text
        assert "cpu percent must be between" in error_text
        assert "timeout must be positive" in error_text
    
    @pytest.mark.asyncio
    async def test_estimate_resource_usage(self, sub_agent_generator):
        """Test resource usage estimation"""
        specifications = [
            AgentSpecification(
                name="agent_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"},
                max_memory_mb=512,
                max_cpu_percent=25,
                timeout_seconds=300
            ),
            AgentSpecification(
                name="agent_2",
                agent_type=AgentType.API_CALLER,
                task_description="Call API",
                parameters={"endpoint": "http://api.com", "method": "GET"},
                max_memory_mb=256,
                max_cpu_percent=15,
                timeout_seconds=180
            )
        ]
        
        estimates = await sub_agent_generator.estimate_resource_usage(specifications)
        
        assert estimates["total_memory_mb"] == 768  # 512 + 256
        assert estimates["total_cpu_percent"] == 40  # 25 + 15
        assert estimates["estimated_time_seconds"] == 300  # max(300, 180)
        assert estimates["agent_count"] == 2
        assert "estimated_cost" in estimates
        assert "memory_cost" in estimates["estimated_cost"]
        assert "cpu_cost" in estimates["estimated_cost"]
        assert "time_cost" in estimates["estimated_cost"]
    
    @pytest.mark.asyncio
    async def test_estimate_resource_usage_with_defaults(self, sub_agent_generator):
        """Test resource usage estimation using template defaults"""
        specifications = [
            AgentSpecification(
                name="agent_1",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"}
                # No explicit resource limits - should use template defaults
            )
        ]
        
        estimates = await sub_agent_generator.estimate_resource_usage(specifications)
        
        # Should use template defaults
        template = sub_agent_generator._templates[AgentType.DATA_PROCESSOR]
        expected_memory = template["default_memory_mb"]
        expected_cpu = 25  # Default CPU percentage
        expected_timeout = template["default_timeout"]
        
        assert estimates["total_memory_mb"] == expected_memory
        assert estimates["total_cpu_percent"] == expected_cpu
        assert estimates["estimated_time_seconds"] == expected_timeout
        assert estimates["agent_count"] == 1
    
    @pytest.mark.asyncio
    async def test_check_resource_availability_within_limits(self, sub_agent_generator):
        """Test resource availability check within limits"""
        estimated_resources = {
            "total_memory_mb": 1024,   # 1GB - within 10GB limit
            "total_cpu_percent": 100   # 100% - within 500% limit
        }
        
        available = await sub_agent_generator._check_resource_availability(estimated_resources)
        assert available is True
    
    @pytest.mark.asyncio
    async def test_check_resource_availability_exceeds_limits(self, sub_agent_generator):
        """Test resource availability check exceeding limits"""
        estimated_resources = {
            "total_memory_mb": 12000,  # 12GB - exceeds 10GB limit
            "total_cpu_percent": 600   # 600% - exceeds 500% limit
        }
        
        available = await sub_agent_generator._check_resource_availability(estimated_resources)
        assert available is False
    
    @pytest.mark.asyncio
    async def test_validate_generation_request_valid(self, sub_agent_generator):
        """Test generation request validation with valid request"""
        # Setup mocks
        sub_agent_generator.execution_tree.get_tree_snapshot.return_value = MagicMock()
        sub_agent_generator.context_manager.get_context.return_value = MagicMock()
        
        specifications = [
            AgentSpecification(
                name="test_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"}
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="parent_123",
            parent_context_id="context_123",
            tree_id="tree_123",
            specifications=specifications
        )
        
        errors = await sub_agent_generator._validate_generation_request(request)
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_generation_request_no_specifications(self, sub_agent_generator):
        """Test generation request validation with no specifications"""
        request = GenerationRequest(
            parent_agent_id="parent_123",
            parent_context_id="context_123",
            tree_id="tree_123",
            specifications=[]  # Empty specifications
        )
        
        errors = await sub_agent_generator._validate_generation_request(request)
        assert len(errors) > 0
        assert any("no agent specifications provided" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_generation_request_invalid_tree(self, sub_agent_generator):
        """Test generation request validation with invalid tree"""
        # Setup mocks
        sub_agent_generator.execution_tree.get_tree_snapshot.return_value = None  # Tree not found
        sub_agent_generator.context_manager.get_context.return_value = MagicMock()
        
        specifications = [
            AgentSpecification(
                name="test_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"}
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="parent_123",
            parent_context_id="context_123",
            tree_id="invalid_tree",
            specifications=specifications
        )
        
        errors = await sub_agent_generator._validate_generation_request(request)
        assert len(errors) > 0
        assert any("execution tree" in error.lower() and "not found" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_generation_request_invalid_context(self, sub_agent_generator):
        """Test generation request validation with invalid context"""
        # Setup mocks
        sub_agent_generator.execution_tree.get_tree_snapshot.return_value = MagicMock()
        sub_agent_generator.context_manager.get_context.return_value = None  # Context not found
        
        specifications = [
            AgentSpecification(
                name="test_agent",
                agent_type=AgentType.DATA_PROCESSOR,
                task_description="Process data",
                parameters={"input_source": "data.csv", "output_format": "json"}
            )
        ]
        
        request = GenerationRequest(
            parent_agent_id="parent_123",
            parent_context_id="invalid_context",
            tree_id="tree_123",
            specifications=specifications
        )
        
        errors = await sub_agent_generator._validate_generation_request(request)
        assert len(errors) > 0
        assert any("parent context" in error.lower() and "not found" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_get_generation_templates(self, sub_agent_generator):
        """Test getting generation templates"""
        templates = await sub_agent_generator.get_generation_templates()
        
        # Should return a copy of templates
        assert templates is not sub_agent_generator._templates
        assert len(templates) == len(sub_agent_generator._templates)
        
        # Verify all agent types are included
        expected_types = [
            AgentType.DATA_PROCESSOR, AgentType.API_CALLER, AgentType.FILE_HANDLER,
            AgentType.ANALYZER, AgentType.VALIDATOR, AgentType.TRANSFORMER,
            AgentType.AGGREGATOR, AgentType.NOTIFIER, AgentType.CUSTOM
        ]
        
        for agent_type in expected_types:
            assert agent_type in templates
            template = templates[agent_type]
            assert "class_name" in template
            assert "required_params" in template
            assert "default_memory_mb" in template
            assert "default_timeout" in template
            assert "capabilities" in template
    
    @pytest.mark.asyncio
    async def test_get_sub_agent_status(self, sub_agent_generator):
        """Test getting sub-agent status"""
        # Create a mock status
        status = SubAgentStatus(
            agent_id="agent_123",
            name="test_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            status=ExecutionStatus.RUNNING,
            node_id="node_123",
            context_id="context_123",
            parent_agent_id="parent_123"
        )
        
        # Add to active agents
        sub_agent_generator._active_agents["agent_123"] = status
        
        # Test retrieval
        retrieved_status = await sub_agent_generator.get_sub_agent_status("agent_123")
        assert retrieved_status == status
        assert retrieved_status.agent_id == "agent_123"
        assert retrieved_status.name == "test_agent"
        
        # Test non-existent agent
        not_found = await sub_agent_generator.get_sub_agent_status("nonexistent")
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_list_sub_agents(self, sub_agent_generator):
        """Test listing sub-agents for a parent"""
        # Create mock statuses for different parents
        status1 = SubAgentStatus(
            agent_id="agent_1",
            name="agent_1",
            agent_type=AgentType.DATA_PROCESSOR,
            status=ExecutionStatus.RUNNING,
            node_id="node_1",
            context_id="context_1",
            parent_agent_id="parent_A"
        )
        
        status2 = SubAgentStatus(
            agent_id="agent_2",
            name="agent_2",
            agent_type=AgentType.API_CALLER,
            status=ExecutionStatus.PENDING,
            node_id="node_2",
            context_id="context_2",
            parent_agent_id="parent_A"
        )
        
        status3 = SubAgentStatus(
            agent_id="agent_3",
            name="agent_3",
            agent_type=AgentType.VALIDATOR,
            status=ExecutionStatus.COMPLETED,
            node_id="node_3",
            context_id="context_3",
            parent_agent_id="parent_B"
        )
        
        # Add to active agents
        sub_agent_generator._active_agents.update({
            "agent_1": status1,
            "agent_2": status2,
            "agent_3": status3
        })
        
        # Test listing for parent_A
        parent_a_agents = await sub_agent_generator.list_sub_agents("parent_A")
        assert len(parent_a_agents) == 2
        agent_ids = {agent.agent_id for agent in parent_a_agents}
        assert agent_ids == {"agent_1", "agent_2"}
        
        # Test listing for parent_B
        parent_b_agents = await sub_agent_generator.list_sub_agents("parent_B")
        assert len(parent_b_agents) == 1
        assert parent_b_agents[0].agent_id == "agent_3"
        
        # Test listing for non-existent parent
        no_agents = await sub_agent_generator.list_sub_agents("nonexistent_parent")
        assert len(no_agents) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_agents(self, sub_agent_generator):
        """Test cleanup of completed agents"""
        # Create mock statuses with different completion times
        old_time = datetime.utcnow().replace(year=2023)  # Old completed agent
        recent_time = datetime.utcnow()  # Recent completed agent
        
        status1 = SubAgentStatus(
            agent_id="old_agent",
            name="old_agent",
            agent_type=AgentType.DATA_PROCESSOR,
            status=ExecutionStatus.COMPLETED,
            node_id="node_1",
            context_id="context_1",
            parent_agent_id="parent_1",
            completed_at=old_time
        )
        
        status2 = SubAgentStatus(
            agent_id="recent_agent",
            name="recent_agent",
            agent_type=AgentType.API_CALLER,
            status=ExecutionStatus.COMPLETED,
            node_id="node_2",
            context_id="context_2",
            parent_agent_id="parent_1",
            completed_at=recent_time
        )
        
        status3 = SubAgentStatus(
            agent_id="running_agent",
            name="running_agent",
            agent_type=AgentType.VALIDATOR,
            status=ExecutionStatus.RUNNING,
            node_id="node_3",
            context_id="context_3",
            parent_agent_id="parent_1"
        )
        
        # Add to active agents
        sub_agent_generator._active_agents.update({
            "old_agent": status1,
            "recent_agent": status2,
            "running_agent": status3
        })
        
        # Mock context manager cleanup
        sub_agent_generator.context_manager.delete_context = AsyncMock(return_value=True)
        
        # Run cleanup (1 hour retention)
        cleaned_count = await sub_agent_generator.cleanup_completed_agents(max_age_hours=1)
        
        # Should clean up old agent but not recent or running
        assert cleaned_count == 1
        assert "old_agent" not in sub_agent_generator._active_agents
        assert "recent_agent" in sub_agent_generator._active_agents
        assert "running_agent" in sub_agent_generator._active_agents
        
        # Verify context cleanup was called
        sub_agent_generator.context_manager.delete_context.assert_called_once_with("context_1")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])