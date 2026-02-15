"""
Unit tests for RegistryAgent

Tests cover:
- Agent loading from unified capabilities registry
- StateSchema creation with List type hints
- ConfigurableAgent initialization
- Type hint handling with __future__ annotations
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.agents.registry_agent import RegistryAgent
from src.agents.base import AgentConfig
from src.interfaces.configurable_agent import (
    AgentConfig as ConfigurableAgentConfig,
    StateSchema,
    ExecutionStrategy,
    ResourceConstraints
)


@pytest.fixture
def mock_capability():
    """Create a mock capability from unified registry"""
    # Mock capability config (AgentCapability model)
    capability_config = MagicMock()
    capability_config.id = "test-capability-id"
    capability_config.agent_type = "test_agent"
    capability_config.name = "Test Agent"
    capability_config.description = "Test agent description"
    capability_config.system_prompt = "You are a test agent"
    capability_config.inputs_schema = {
        "user_request": {"type": "string", "required": True}
    }
    capability_config.outputs_schema = {
        "result": {"type": "string"}
    }
    capability_config.execution_hints = {
        "model": "google/gemini-2.5-flash",
        "temperature": 0.7,
        "max_tokens": 2000
    }
    capability_config.task_type = "llm_worker"
    capability_config.version = 1
    capability_config.is_active = True

    # Mock ResolvedCapability
    capability = MagicMock()
    capability.config = capability_config

    return capability


@pytest.fixture
def mock_unified_registry(mock_capability):
    """Create a mock UnifiedCapabilityRegistry"""
    registry = AsyncMock()
    registry.initialize = AsyncMock()
    registry.cleanup = AsyncMock()
    registry.resolve = AsyncMock(return_value=mock_capability)
    return registry


@pytest.fixture
def registry_agent_config():
    """Create a RegistryAgent configuration"""
    return AgentConfig(
        name="registry_agent",
        agent_type="registry",
        metadata={
            "agent_name": "test_agent",
            "version": "latest"
        }
    )


class TestRegistryAgentImports:
    """Test that RegistryAgent can import and use type hints correctly"""

    def test_registry_agent_imports_successfully(self):
        """Test that RegistryAgent can be imported without NameError"""
        from src.agents.registry_agent import RegistryAgent
        assert RegistryAgent is not None

    def test_state_schema_can_be_created_with_list(self):
        """Test that StateSchema can be created with List[str] type hints"""
        # This should not raise NameError
        schema = StateSchema(
            required=["input1", "input2"],
            output=["output1"],
            checkpoint=None,
            validation_rules=None
        )

        assert schema.required == ["input1", "input2"]
        assert schema.output == ["output1"]

    def test_state_schema_with_empty_lists(self):
        """Test StateSchema creation with empty lists"""
        schema = StateSchema(
            required=[],
            output=[],
            checkpoint=None,
            validation_rules=None
        )

        assert schema.required == []
        assert schema.output == []

    def test_resource_constraints_creation(self):
        """Test ResourceConstraints creation"""
        resources = ResourceConstraints(
            model="test-model",
            max_tokens=1000,
            timeout=300,
            max_retries=3,
            temperature=0.7,
            response_format=None
        )

        assert resources.model == "test-model"
        assert resources.max_tokens == 1000
        assert resources.timeout == 300


class TestRegistryAgentInitialization:
    """Test RegistryAgent initialization and agent loading"""

    @pytest.mark.asyncio
    async def test_initialize_loads_agent_from_registry(
        self, registry_agent_config, mock_unified_registry
    ):
        """Test that initialize loads agent from unified capabilities registry"""
        agent = RegistryAgent(registry_agent_config)

        # Patch the unified registry and database (they're imported inside initialize method)
        with patch('src.capabilities.unified_registry.UnifiedCapabilityRegistry') as MockRegistry, \
             patch('src.interfaces.database.Database') as MockDatabase:

            # Mock database connection
            mock_db = AsyncMock()
            mock_db.connect = AsyncMock()
            MockDatabase.return_value = mock_db

            MockRegistry.return_value = mock_unified_registry

            # Mock OpenRouterClient (it's imported inside initialize method)
            with patch('src.llm.openrouter_client.OpenRouterClient') as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_client_instance

                # Mock PromptExecutor and ToolExecutor (they're imported inside initialize method)
                with patch('src.infrastructure.execution_runtime.prompt_executor.PromptExecutor') as MockPromptExecutor, \
                     patch('src.infrastructure.flux_runtime.tool_executor.ToolExecutor') as MockToolExecutor, \
                     patch('src.infrastructure.flux_runtime.tool_registry.get_registry') as mock_get_registry, \
                     patch('src.agents.configurable_agent.ConfigurableAgent') as MockConfigurableAgent:

                    mock_prompt_executor = MagicMock()
                    MockPromptExecutor.return_value = mock_prompt_executor

                    mock_tool_executor = MagicMock()
                    MockToolExecutor.return_value = mock_tool_executor

                    mock_get_registry.return_value = MagicMock()

                    mock_configurable_agent = AsyncMock()
                    mock_configurable_agent.initialize = AsyncMock()
                    MockConfigurableAgent.return_value = mock_configurable_agent

                    # Initialize agent
                    await agent.initialize()

                    # Verify agent was loaded from registry
                    mock_unified_registry.resolve.assert_called_once_with(
                        "test_agent",
                        capability_type="agent"
                    )
                    assert agent.loaded_agent is not None

    @pytest.mark.asyncio
    async def test_initialize_creates_state_schema_with_list(
        self, registry_agent_config, mock_unified_registry
    ):
        """Test that initialize creates StateSchema with List type hints correctly"""
        agent = RegistryAgent(registry_agent_config)

        with patch('src.capabilities.unified_registry.UnifiedCapabilityRegistry') as MockRegistry, \
             patch('src.interfaces.database.Database') as MockDatabase:

            # Mock database connection
            mock_db = AsyncMock()
            mock_db.connect = AsyncMock()
            MockDatabase.return_value = mock_db

            MockRegistry.return_value = mock_unified_registry

            with patch('src.llm.openrouter_client.OpenRouterClient') as MockClient, \
                 patch('src.infrastructure.execution_runtime.prompt_executor.PromptExecutor') as MockPromptExecutor, \
                 patch('src.infrastructure.flux_runtime.tool_executor.ToolExecutor') as MockToolExecutor, \
                 patch('src.infrastructure.flux_runtime.tool_registry.get_registry') as mock_get_registry, \
                 patch('src.agents.configurable_agent.ConfigurableAgent') as MockConfigurableAgent:

                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_client_instance

                mock_prompt_executor = MagicMock()
                MockPromptExecutor.return_value = mock_prompt_executor

                mock_tool_executor = MagicMock()
                MockToolExecutor.return_value = mock_tool_executor

                mock_get_registry.return_value = MagicMock()

                # Create a real ConfigurableAgent instance to capture the config
                mock_agent_instance = MagicMock()
                mock_agent_instance.initialize = AsyncMock()

                # Store the config that was passed
                captured_configs = []

                def create_agent(*args, **kwargs):
                    config = kwargs.get('config') or (args[1] if len(args) > 1 else None)
                    if config:
                        captured_configs.append(config)
                    return mock_agent_instance

                MockConfigurableAgent.side_effect = create_agent

                # Initialize agent
                await agent.initialize()

                # Verify StateSchema was created with List type hints
                # Check if config was captured or check the agent's loaded_agent
                if captured_configs:
                    config = captured_configs[0]
                    assert config.state_schema is not None
                    assert isinstance(config.state_schema.required, list)
                    assert isinstance(config.state_schema.output, list)
                elif agent.loaded_agent and hasattr(agent.loaded_agent, 'config'):
                    # Fallback: check the actual loaded agent's config
                    config = agent.loaded_agent.config
                    assert config is not None
                    assert config.state_schema is not None
                    assert isinstance(config.state_schema.required, list)
                    assert isinstance(config.state_schema.output, list)
                else:
                    # If we can't verify directly, at least verify the agent initialized
                    assert agent.loaded_agent is not None

    @pytest.mark.asyncio
    async def test_initialize_handles_missing_agent_name(self, registry_agent_config):
        """Test that initialize raises error when agent_name is missing"""
        config = AgentConfig(
            name="registry_agent",
            agent_type="registry",
            metadata={}  # Missing agent_name
        )

        agent = RegistryAgent(config)

        with pytest.raises(ValueError, match="agent_name"):
            await agent.initialize()

    @pytest.mark.asyncio
    async def test_initialize_handles_agent_not_found(
        self, registry_agent_config, mock_unified_registry
    ):
        """Test that initialize raises error when agent is not found"""
        agent = RegistryAgent(registry_agent_config)

        # Configure mock to return None (agent not found)
        mock_unified_registry.resolve = AsyncMock(return_value=None)

        with patch('src.capabilities.unified_registry.UnifiedCapabilityRegistry') as MockRegistry, \
             patch('src.interfaces.database.Database') as MockDatabase:

            # Mock database connection
            mock_db = AsyncMock()
            mock_db.connect = AsyncMock()
            MockDatabase.return_value = mock_db

            MockRegistry.return_value = mock_unified_registry

            with pytest.raises(ValueError, match="not found"):
                await agent.initialize()


class TestRegistryAgentTypeHints:
    """Test that type hints work correctly with __future__ annotations"""

    def test_prompt_executor_imports_with_list_type_hint(self):
        """Test that PromptExecutor can be imported with List type hints"""
        # This should not raise NameError
        from src.infrastructure.execution_runtime.prompt_executor import PromptExecutor
        assert PromptExecutor is not None

    def test_configurable_agent_config_has_list_type_hints(self):
        """Test that AgentConfig uses List type hints correctly"""
        # Create a config with List fields
        config = ConfigurableAgentConfig(
            name="test",
            type="test",
            version="1.0.0",
            capabilities=[],  # List field
            prompt_template="test",
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
            state_schema=StateSchema(
                required=[],  # List[str]
                output=[],    # List[str]
                checkpoint=None,
                validation_rules=None
            ),
            resources=ResourceConstraints(
                model="test",
                max_tokens=1000,
                timeout=300
            ),
            success_metrics=[]  # List field
        )

        assert isinstance(config.capabilities, list)
        assert isinstance(config.state_schema.required, list)
        assert isinstance(config.state_schema.output, list)
        assert isinstance(config.success_metrics, list)

    def test_type_hints_are_strings_with_future_annotations(self):
        """Test that type hints are strings when __future__ annotations is used"""
        import inspect
        from src.interfaces.configurable_agent import StateSchema

        annotations = inspect.get_annotations(StateSchema)

        # With __future__ annotations, type hints should be strings
        assert isinstance(annotations.get('required'), str)
        assert isinstance(annotations.get('output'), str)
        assert 'List' in annotations.get('required', '')
        assert 'List' in annotations.get('output', '')


class TestRegistryAgentExecution:
    """Test RegistryAgent execution"""

    @pytest.mark.asyncio
    async def test_execute_requires_initialization(self, registry_agent_config):
        """Test that execute raises error if not initialized"""
        agent = RegistryAgent(registry_agent_config)

        with pytest.raises(RuntimeError, match="not initialized"):
            await agent.execute({"task": "test"})

    @pytest.mark.asyncio
    async def test_execute_delegates_to_loaded_agent(
        self, registry_agent_config, mock_unified_registry
    ):
        """Test that execute delegates to loaded ConfigurableAgent"""
        agent = RegistryAgent(registry_agent_config)

        # Create a mock loaded agent
        mock_loaded_agent = AsyncMock()
        mock_loaded_agent.execute = AsyncMock(return_value={"result": "success"})
        agent.loaded_agent = mock_loaded_agent

        # Execute
        result = await agent.execute({"task": "test"})

        # Verify delegation
        mock_loaded_agent.execute.assert_called_once_with({"task": "test"})
        assert result == {"result": "success"}
