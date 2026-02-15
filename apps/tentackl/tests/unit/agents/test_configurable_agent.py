"""
Unit tests for ConfigurableAgent
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.configurable_agent import ConfigurableAgent
from src.interfaces.configurable_agent import (
    AgentConfig,
    ExecutionStrategy,
    CapabilityConfig,
    StateSchema,
    ResourceConstraints,
    SuccessMetric
)
from src.interfaces.agent import AgentState, AgentResult
from src.interfaces.budget_controller import ResourceType
from src.interfaces.state_store import StateType
from src.core.exceptions import (
    AgentExecutionError,
    ValidationError
)


@pytest.fixture
def sample_config():
    """Create a sample agent configuration"""
    return AgentConfig(
        name="test-agent",
        type="analyzer",
        version="1.0.0",
        description="Test analyzer agent",
        capabilities=[
            CapabilityConfig(
                tool="file_read",
                config={"formats": ["txt", "json"], "max_size_mb": 10},
                sandbox=True
            ),
            CapabilityConfig(
                tool="data_transform",
                config={"operations": ["filter", "map"], "memory_limit_mb": 512}
            )
        ],
        prompt_template="Analyze {data_type} with focus on {analysis_focus}. Context: {context.description}",
        execution_strategy=ExecutionStrategy.SEQUENTIAL,
        state_schema=StateSchema(
            required=["data_type", "analysis_focus"],
            output=["summary", "insights", "score"],
            checkpoint={"enabled": True, "interval": 100},
            validation_rules={
                "score": {"type": "float", "min": 0.0, "max": 1.0}
            }
        ),
        resources=ResourceConstraints(
            model="gpt-3.5-turbo",
            max_tokens=1000,
            timeout=300,
            max_retries=3,
            memory_mb=1024
        ),
        success_metrics=[
            SuccessMetric(metric="completion_rate", threshold=0.95, operator="gte"),
            SuccessMetric(metric="score", threshold=0.7, operator="gte")
        ],
        metadata={"team": "data-science", "project": "analysis"}
    )


@pytest.fixture
def mock_capability_binder():
    """Create a mock capability binder"""
    binder = AsyncMock()
    binder.validate_capability = AsyncMock(return_value=True)
    binder.bind_capability = AsyncMock()
    return binder


@pytest.fixture
def mock_prompt_executor():
    """Create a mock prompt executor"""
    executor = AsyncMock()
    executor.execute_prompt = AsyncMock(return_value={
        "summary": "Test summary",
        "insights": ["insight1", "insight2"],
        "score": 0.85
    })
    return executor


@pytest.fixture
def mock_budget_controller():
    """Create a mock budget controller"""
    controller = AsyncMock()
    controller.check_budget = AsyncMock(return_value=True)
    controller.consume_budget = AsyncMock()
    return controller


@pytest.fixture
def mock_state_store():
    """Create a mock state store"""
    store = AsyncMock()
    store.get_latest_state = AsyncMock(return_value=None)
    store.save_state = AsyncMock()
    return store


@pytest.fixture
def mock_context_manager():
    """Create a mock context manager"""
    manager = AsyncMock()
    manager.get_context = AsyncMock(return_value=None)
    return manager


class TestConfigurableAgent:
    """Test ConfigurableAgent functionality"""
    
    async def test_agent_creation(self, sample_config):
        """Test agent creation with config"""
        agent = ConfigurableAgent(
            agent_id="test-123",
            config=sample_config
        )
        
        assert agent.agent_id == "test-123"
        assert agent.config == sample_config
        assert agent._execution_count == 0
        assert isinstance(agent._state, dict)
        assert isinstance(agent._capabilities, dict)
    
    async def test_load_config(
        self,
        sample_config,
        mock_capability_binder
    ):
        """Test loading configuration"""
        agent = ConfigurableAgent(
            capability_binder=mock_capability_binder
        )
        
        await agent.load_config(sample_config)
        
        assert agent.config == sample_config
        assert len(agent._capabilities) == 2
        assert "file_read" in agent._capabilities
        assert "data_transform" in agent._capabilities
        
        # Verify capabilities were bound
        assert mock_capability_binder.bind_capability.call_count == 2
    
    async def test_load_invalid_config(self, mock_capability_binder):
        """Test loading invalid configuration"""
        # Create invalid config (missing name)
        invalid_config = AgentConfig(
            name="",  # Invalid
            type="analyzer",
            version="1.0.0",
            capabilities=[],
            prompt_template="Test",
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
            state_schema=StateSchema(required=[], output=[]),
            resources=ResourceConstraints(
                model="gpt-3.5-turbo",
                max_tokens=1000,
                timeout=300
            ),
            success_metrics=[]
        )
        
        agent = ConfigurableAgent(
            capability_binder=mock_capability_binder
        )
        
        with pytest.raises(ValidationError) as exc_info:
            await agent.load_config(invalid_config)
        
        assert "Invalid configuration" in str(exc_info.value)
    
    async def test_reload_config(
        self,
        sample_config,
        mock_capability_binder
    ):
        """Test hot reload of configuration"""
        agent = ConfigurableAgent(
            capability_binder=mock_capability_binder
        )
        
        # Load initial config
        await agent.load_config(sample_config)
        
        # Set some state
        agent._state["data_type"] = "csv"
        agent._state["analysis_focus"] = "patterns"
        agent._state["custom_field"] = "value"
        
        # Create new config with different schema
        new_config = AgentConfig(
            name="test-agent-v2",
            type="analyzer",
            version="2.0.0",
            capabilities=[],
            prompt_template="New template",
            execution_strategy=ExecutionStrategy.PARALLEL,
            state_schema=StateSchema(
                required=["data_type"],  # Only data_type required now
                output=["result"]
            ),
            resources=ResourceConstraints(
                model="gpt-4",
                max_tokens=2000,
                timeout=600
            ),
            success_metrics=[]
        )
        
        await agent.reload_config(new_config)
        
        assert agent.config == new_config
        assert agent._state["data_type"] == "csv"  # Preserved
        assert "analysis_focus" not in agent._state  # Not in new schema
        assert "custom_field" not in agent._state  # Not in new schema
    
    async def test_validate_state(self, sample_config):
        """Test state validation"""
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)  # Let async load complete
        
        # Valid state
        valid_state = {
            "data_type": "csv",
            "analysis_focus": "patterns",
            "summary": "Test summary",
            "insights": ["insight1"],
            "score": 0.85
        }
        
        result = await agent.validate_state(valid_state)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        
        # Invalid state - missing required field
        invalid_state = {
            "data_type": "csv"
            # Missing analysis_focus
        }
        
        result = await agent.validate_state(invalid_state)
        assert result["valid"] is False
        assert "Required field missing: analysis_focus" in result["errors"]
        
        # Invalid state - wrong type
        invalid_state = {
            "data_type": "csv",
            "analysis_focus": "patterns",
            "score": "high"  # Should be float
        }
        
        result = await agent.validate_state(invalid_state)
        assert result["valid"] is False
        assert any("wrong type" in err for err in result["errors"])
    
    async def test_check_success_metrics(self, sample_config):
        """Test success metrics checking"""
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        # Successful execution result
        success_result = {
            "completion_rate": 1.0,
            "score": 0.85
        }
        
        metrics = await agent.check_success_metrics(success_result)
        assert metrics["completion_rate"] is True  # 1.0 >= 0.95
        assert metrics["score"] is True  # 0.85 >= 0.7
        
        # Failed execution result
        failed_result = {
            "completion_rate": 0.5,
            "score": 0.6
        }
        
        metrics = await agent.check_success_metrics(failed_result)
        assert metrics["completion_rate"] is False  # 0.5 < 0.95
        assert metrics["score"] is False  # 0.6 < 0.7
    
    async def test_execute_with_strategy_sequential(self, sample_config):
        """Test sequential execution strategy"""
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        task_list = ["task1", "task2", "task3"]
        context = {"test": True}
        
        result = await agent.execute_with_strategy(task_list, context)
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert all("task" in r for r in result)
    
    async def test_execute_with_strategy_parallel(self, sample_config):
        """Test parallel execution strategy"""
        # Modify config for parallel execution
        sample_config.execution_strategy = ExecutionStrategy.PARALLEL
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        task_list = ["task1", "task2", "task3"]
        context = {"test": True}
        
        result = await agent.execute_with_strategy(task_list, context)
        
        assert isinstance(result, list)
        assert len(result) == 3
    
    async def test_execute_task_success(
        self,
        sample_config,
        mock_capability_binder,
        mock_prompt_executor,
        mock_budget_controller,
        mock_state_store,
        mock_context_manager
    ):
        """Test successful task execution"""
        agent = ConfigurableAgent(
            config=sample_config,
            capability_binder=mock_capability_binder,
            prompt_executor=mock_prompt_executor,
            budget_controller=mock_budget_controller,
            state_store=mock_state_store,
            context_manager=mock_context_manager
        )
        await asyncio.sleep(0.1)
        
        # Execute task
        task = {
            "data_type": "csv",
            "analysis_focus": "patterns",
            "context": {"description": "Sales data analysis"}
        }
        
        result = await agent.execute(task)
        
        assert isinstance(result, AgentResult)
        assert result.state == AgentState.COMPLETED
        assert result.error is None
        assert "summary" in agent._state
        assert agent._state["score"] == 0.85
        
        # Verify budget was checked and consumed
        assert mock_budget_controller.check_budget.call_count >= 2
        assert mock_budget_controller.consume_budget.call_count >= 2
        
        # Verify prompt was executed
        mock_prompt_executor.execute_prompt.assert_called_once()
    
    async def test_execute_task_budget_exceeded(
        self,
        sample_config,
        mock_capability_binder,
        mock_prompt_executor,
        mock_budget_controller,
        mock_state_store,
        mock_context_manager
    ):
        """Test task execution when budget is exceeded"""
        # Configure budget controller to reject
        mock_budget_controller.check_budget = AsyncMock(return_value=False)
        
        agent = ConfigurableAgent(
            config=sample_config,
            capability_binder=mock_capability_binder,
            prompt_executor=mock_prompt_executor,
            budget_controller=mock_budget_controller,
            state_store=mock_state_store,
            context_manager=mock_context_manager
        )
        await asyncio.sleep(0.1)
        
        task = {"data_type": "csv", "analysis_focus": "patterns"}
        result = await agent.execute(task)
        
        assert result.state == AgentState.FAILED
        assert "Budget exceeded" in result.error
        assert mock_prompt_executor.execute_prompt.call_count == 0
    
    async def test_execute_with_checkpoint(
        self,
        sample_config,
        mock_capability_binder,
        mock_prompt_executor,
        mock_budget_controller,
        mock_state_store,
        mock_context_manager
    ):
        """Test execution with checkpoint saving"""
        agent = ConfigurableAgent(
            config=sample_config,
            capability_binder=mock_capability_binder,
            prompt_executor=mock_prompt_executor,
            budget_controller=mock_budget_controller,
            state_store=mock_state_store,
            context_manager=mock_context_manager
        )
        await asyncio.sleep(0.1)
        
        task = {"data_type": "csv", "analysis_focus": "patterns"}
        result = await agent.execute(task)
        
        assert result.state == AgentState.COMPLETED
        
        # Verify checkpoint was saved
        mock_state_store.save_state.assert_called()
        call_args = mock_state_store.save_state.call_args
        assert call_args[0][1] == StateType.CHECKPOINT
    
    async def test_initialize_with_state_restore(
        self,
        sample_config,
        mock_state_store
    ):
        """Test initialization with state restoration"""
        # Configure state store to return saved state
        from dataclasses import dataclass
        
        @dataclass
        class MockState:
            id: str = "state-123"
            data: dict = None
            
            def __post_init__(self):
                if self.data is None:
                    self.data = {
                        "data_type": "json",
                        "analysis_focus": "anomalies",
                        "previous_score": 0.92
                    }
        
        mock_state_store.get_latest_state = AsyncMock(
            return_value=MockState()
        )
        
        agent = ConfigurableAgent(
            config=sample_config,
            state_store=mock_state_store
        )
        await asyncio.sleep(0.1)
        
        await agent.initialize()
        
        assert agent._state["data_type"] == "json"
        assert agent._state["analysis_focus"] == "anomalies"
        assert agent._state["previous_score"] == 0.92
    
    async def test_cleanup(self, sample_config, mock_state_store):
        """Test agent cleanup"""
        agent = ConfigurableAgent(
            config=sample_config,
            state_store=mock_state_store
        )
        await asyncio.sleep(0.1)
        
        # Set some state and execute
        agent._state = {"data_type": "csv", "score": 0.85}
        agent._execution_count = 5
        
        await agent.cleanup()
        
        # Verify final state was saved
        mock_state_store.save_state.assert_called()
        call_args = mock_state_store.save_state.call_args
        assert call_args[0][1] == StateType.FINAL
        assert call_args[0][3]["execution_count"] == 5
        
        # Verify runtime data was cleared
        assert len(agent._state) == 0
        assert len(agent._capabilities) == 0
        assert len(agent._metrics) == 0
    
    async def test_get_state(self, sample_config):
        """Test getting agent state"""
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        # Initial state
        state = await agent.get_state()
        assert state == AgentState.IDLE
        
        # After execution
        agent._execution_count = 1
        state = await agent.get_state()
        assert state == AgentState.COMPLETED
    
    async def test_get_capabilities(self, sample_config, mock_capability_binder):
        """Test getting agent capabilities"""
        agent = ConfigurableAgent(
            config=sample_config,
            capability_binder=mock_capability_binder
        )
        await agent.load_config(sample_config)
        
        capabilities = await agent.get_capabilities()
        assert len(capabilities) > 0
        # Capabilities are converted to enums or CUSTOM
    
    async def test_conditional_execution(self, sample_config):
        """Test conditional execution strategy"""
        sample_config.execution_strategy = ExecutionStrategy.CONDITIONAL
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        # Task with condition
        task = {
            "condition": "context.get('execute', False)",
            "then": {"action": "process"},
            "else": {"action": "skip"}
        }
        
        # Condition true
        result = await agent.execute_with_strategy(
            task,
            {"execute": True}
        )
        assert result["task"]["action"] == "process"
        
        # Condition false
        result = await agent.execute_with_strategy(
            task,
            {"execute": False}
        )
        assert result["task"]["action"] == "skip"
    
    async def test_iterative_execution(self, sample_config):
        """Test iterative execution strategy"""
        sample_config.execution_strategy = ExecutionStrategy.ITERATIVE
        agent = ConfigurableAgent(config=sample_config)
        await asyncio.sleep(0.1)
        
        # Task with iteration
        task = {
            "iterate": {"process": "data"},
            "while": "iteration < 3"
        }
        
        result = await agent.execute_with_strategy(task, {})
        assert isinstance(result, list)
        assert len(result) == 3  # Should iterate 3 times
    
    async def test_error_handling(
        self,
        sample_config,
        mock_prompt_executor
    ):
        """Test error handling during execution"""
        # Configure prompt executor to raise error
        mock_prompt_executor.execute_prompt = AsyncMock(
            side_effect=Exception("LLM error")
        )
        
        agent = ConfigurableAgent(
            config=sample_config,
            prompt_executor=mock_prompt_executor
        )
        await asyncio.sleep(0.1)
        
        task = {"data_type": "csv", "analysis_focus": "patterns"}
        result = await agent.execute(task)
        
        assert result.state == AgentState.FAILED
        assert "LLM error" in result.error
        assert result.metadata["execution_time"] > 0
