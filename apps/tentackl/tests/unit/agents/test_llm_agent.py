import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from src.agents.llm_agent import (
    LLMAgent, LLMWorkerAgent, LLMAnalyzerAgent,
    LLMValidatorAgent, LLMOrchestratorAgent
)
from src.agents.base import AgentConfig
from src.interfaces.llm import LLMMessage, LLMResponse
from src.llm.openrouter_client import OpenRouterClient


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client"""
    client = AsyncMock(spec=OpenRouterClient)
    client.health_check = AsyncMock(return_value=True)
    client.create_completion = AsyncMock()
    return client


@pytest.fixture
def mock_state_store():
    """Create a mock state store"""
    store = AsyncMock()
    store.initialize = AsyncMock()
    store.cleanup = AsyncMock()
    return store


class TestLLMAgent:
    """Test base LLM agent functionality"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, mock_llm_client, mock_state_store):
        """Test LLM agent initialization"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(
                name="Test Agent",
                agent_type="llm_agent",
                metadata={
                    "model": "test-model",
                    "temperature": 0.5
                }
            )
            agent = LLMAgent(
                config=config,
                llm_client=mock_llm_client
            )

            await agent.initialize()

            assert agent.name == "Test Agent"
            assert agent.model == "test-model"
            assert agent.temperature == 0.5
            mock_llm_client.health_check.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_task_success(self, mock_llm_client, mock_state_store):
        """Test successful task processing"""
        # Mock LLM response
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Task completed"}',
            model="test-model",
            usage={"total_tokens": 100}
        )
        mock_llm_client.create_completion.return_value = mock_response

        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Test Agent", agent_type="llm_agent")
            agent = LLMAgent(config=config, llm_client=mock_llm_client)
            await agent.initialize()

            task = {
                "description": "Test task",
                "data": {"key": "value"}
            }

            result = await agent.process_task(task)

            assert result["status"] == "success"
            # Parsed JSON is returned in normalized top-level shape
            assert result["result"] == "Task completed"
            assert result["metadata"]["model"] == "test-model"
            assert result["metadata"]["usage"]["total_tokens"] == 100
    
    @pytest.mark.asyncio
    async def test_process_task_non_json_response(self, mock_llm_client, mock_state_store):
        """Test handling non-JSON response"""
        mock_response = LLMResponse(
            content="This is a plain text response",
            model="test-model"
        )
        mock_llm_client.create_completion.return_value = mock_response

        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Test Agent", agent_type="llm_agent")
            agent = LLMAgent(config=config, llm_client=mock_llm_client)
            await agent.initialize()

            result = await agent.process_task({"description": "Test"})

            assert result["status"] == "success"
            assert result["result"] == "This is a plain text response"
            assert result["metadata"]["raw_response"] is True
    
    @pytest.mark.asyncio
    async def test_process_task_error(self, mock_llm_client, mock_state_store):
        """Test error handling in task processing"""
        mock_llm_client.create_completion.side_effect = Exception("API Error")

        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Test Agent", agent_type="llm_agent")
            agent = LLMAgent(config=config, llm_client=mock_llm_client)
            await agent.initialize()

            result = await agent.process_task({"description": "Test"})

            assert result["status"] == "error"
            assert result["error"] == "API Error"
            assert result["metadata"]["agent"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_auto_client_creation(self, mock_state_store):
        """Test automatic client creation when none provided"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            with patch('src.agents.llm_agent.OpenRouterClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.health_check = AsyncMock(return_value=True)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_class.return_value = mock_client

                config = AgentConfig(name="Test Agent", agent_type="llm_agent")
                agent = LLMAgent(config=config)

                await agent.initialize()
                assert agent.llm_client is not None

                await agent.cleanup()
                mock_client.__aexit__.assert_called_once()


class TestSpecializedAgents:
    """Test specialized LLM agent types"""
    
    @pytest.mark.asyncio
    async def test_llm_worker_agent(self, mock_llm_client, mock_state_store):
        """Test LLM Worker Agent"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Worker", agent_type="llm_worker")
            agent = LLMWorkerAgent(config=config, llm_client=mock_llm_client)

            await agent.initialize()

            assert agent.model == "x-ai/grok-3-mini"
            assert agent.temperature == 0.7
            assert "worker agent" in agent.system_prompt.lower()

    @pytest.mark.asyncio
    async def test_llm_analyzer_agent(self, mock_llm_client, mock_state_store):
        """Test LLM Analyzer Agent"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Analyzer", agent_type="llm_analyzer")
            agent = LLMAnalyzerAgent(config=config, llm_client=mock_llm_client)

            await agent.initialize()

            assert agent.model == "openai/gpt-4o"
            assert agent.temperature == 0.3
            assert "analyzer agent" in agent.system_prompt.lower()
            assert "data analysis" in agent.system_prompt.lower()

    @pytest.mark.asyncio
    async def test_llm_validator_agent(self, mock_llm_client, mock_state_store):
        """Test LLM Validator Agent"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Validator", agent_type="llm_validator")
            agent = LLMValidatorAgent(config=config, llm_client=mock_llm_client)

            await agent.initialize()

            assert agent.model == "x-ai/grok-3-mini"
            assert agent.temperature == 0.1  # Very low for consistency
            assert "validator agent" in agent.system_prompt.lower()
            assert "validation" in agent.system_prompt.lower()

    @pytest.mark.asyncio
    async def test_llm_orchestrator_agent(self, mock_llm_client, mock_state_store):
        """Test LLM Orchestrator Agent"""
        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Orchestrator", agent_type="llm_orchestrator")
            agent = LLMOrchestratorAgent(config=config, llm_client=mock_llm_client)

            await agent.initialize()

            assert agent.model == "x-ai/grok-4.1-fast"
            assert agent.temperature == 0.5
            assert "orchestrator agent" in agent.system_prompt.lower()
    
    @pytest.mark.asyncio
    async def test_orchestrator_create_plan(self, mock_llm_client, mock_state_store):
        """Test orchestrator's execution plan creation"""
        mock_response = LLMResponse(
            content=json.dumps({
                "plan": {
                    "steps": ["step1", "step2"],
                    "dependencies": {},
                    "agent_assignments": {"step1": "worker", "step2": "analyzer"}
                }
            }),
            model="claude-3-5-sonnet-20241022"
        )
        mock_llm_client.create_completion.return_value = mock_response

        with patch('src.infrastructure.state.redis_state_store.RedisStateStore', return_value=mock_state_store):
            config = AgentConfig(name="Orchestrator", agent_type="llm_orchestrator")
            agent = LLMOrchestratorAgent(config=config, llm_client=mock_llm_client)
            await agent.initialize()

            task = {"description": "Complex task", "data": {}}
            result = await agent.create_execution_plan(task)

            # create_execution_plan returns normalized parsed plan payload
            assert result["status"] == "success"
            assert "plan" in result
            assert "steps" in result["plan"]
            assert len(result["plan"]["steps"]) == 2
