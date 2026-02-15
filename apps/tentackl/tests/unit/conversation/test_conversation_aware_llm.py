"""Unit tests for conversation-aware LLM agent functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from src.agents.llm_agent import (
    LLMAgent,
    ConversationAwareLLMWrapper,
    LLMWorkerAgent,
    LLMAnalyzerAgent,
    LLMValidatorAgent,
    LLMOrchestratorAgent
)
from src.agents.base import AgentConfig
from src.agents.conversation_aware_agent import ConversationAwareAgent
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.database.conversation_interceptor import ConversationInterceptor
from src.database.models import MessageType


class TestLLMAgentInheritance:
    """Test LLMAgent class hierarchy and initialization."""
    
    def test_llm_agent_inherits_from_conversation_aware(self):
        """Verify LLMAgent inherits from ConversationAwareAgent."""
        assert issubclass(LLMAgent, ConversationAwareAgent)
    
    def test_specialized_agents_inherit_from_llm_agent(self):
        """Verify all specialized agents inherit from LLMAgent."""
        assert issubclass(LLMWorkerAgent, LLMAgent)
        assert issubclass(LLMAnalyzerAgent, LLMAgent)
        assert issubclass(LLMValidatorAgent, LLMAgent)
        assert issubclass(LLMOrchestratorAgent, LLMAgent)
    
    @pytest.mark.asyncio
    async def test_conversation_tracking_enabled_by_default(self):
        """Test that conversation tracking is enabled by default."""
        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(config=config)

        assert agent.enable_conversation_tracking is True
    
    @pytest.mark.asyncio
    async def test_conversation_tracking_can_be_disabled(self):
        """Test that conversation tracking can be disabled."""
        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(config=config, enable_conversation_tracking=False)

        assert agent.enable_conversation_tracking is False


class TestConversationAwareLLMWrapper:
    """Test the conversation-aware wrapper functionality."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = AsyncMock(spec=LLMInterface)
        client.create_completion = AsyncMock(return_value=LLMResponse(
            content='{"status": "success"}',
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        ))
        return client
    
    @pytest.fixture
    def mock_interceptor(self):
        """Create a mock conversation interceptor."""
        interceptor = AsyncMock(spec=ConversationInterceptor)
        interceptor.intercept_llm_call = AsyncMock(return_value=MagicMock(message_id="msg-123"))
        interceptor.intercept_llm_response = AsyncMock()
        interceptor.intercept_error = AsyncMock()
        return interceptor
    
    @pytest.mark.asyncio
    async def test_wrapper_initialization(self, mock_llm_client, mock_interceptor):
        """Test wrapper is initialized correctly."""
        wrapper = ConversationAwareLLMWrapper(
            client=mock_llm_client,
            interceptor=mock_interceptor,
            agent_id="test-agent",
            default_model="test-model"
        )
        
        assert wrapper.client == mock_llm_client
        assert wrapper.interceptor == mock_interceptor
        assert wrapper.agent_id == "test-agent"
        assert wrapper.default_model == "test-model"
    
    @pytest.mark.asyncio
    async def test_wrapper_intercepts_llm_calls(self, mock_llm_client, mock_interceptor):
        """Test wrapper intercepts LLM calls."""
        wrapper = ConversationAwareLLMWrapper(
            client=mock_llm_client,
            interceptor=mock_interceptor,
            agent_id="test-agent",
            default_model="test-model"
        )
        
        messages = [
            LLMMessage(role="system", content="You are a test assistant"),
            LLMMessage(role="user", content="Test prompt")
        ]
        
        response = await wrapper.create_completion(
            messages=messages,
            model="test-model",
            temperature=0.7
        )
        
        # Verify interceptor was called for request
        mock_interceptor.intercept_llm_call.assert_called_once()
        call_args = mock_interceptor.intercept_llm_call.call_args
        assert call_args.kwargs['agent_id'] == "test-agent"
        assert call_args.kwargs['prompt'] == "Test prompt"
        assert call_args.kwargs['model'] == "test-model"
        
        # Verify LLM client was called
        mock_llm_client.create_completion.assert_called_once_with(
            messages, model="test-model", temperature=0.7
        )
        
        # Verify interceptor was called for response
        mock_interceptor.intercept_llm_response.assert_called_once()
        resp_args = mock_interceptor.intercept_llm_response.call_args
        assert resp_args.kwargs['agent_id'] == "test-agent"
        assert resp_args.kwargs['response'] == response
        assert resp_args.kwargs['latency_ms'] >= 0  # Can be 0 in fast tests
        assert resp_args.kwargs['parent_message_id'] == "msg-123"
    
    @pytest.mark.asyncio
    async def test_wrapper_handles_errors(self, mock_llm_client, mock_interceptor):
        """Test wrapper handles and intercepts errors."""
        wrapper = ConversationAwareLLMWrapper(
            client=mock_llm_client,
            interceptor=mock_interceptor,
            agent_id="test-agent",
            default_model="test-model"
        )
        
        # Make LLM client raise an error
        mock_llm_client.create_completion.side_effect = Exception("LLM error")
        
        messages = [LLMMessage(role="user", content="Test prompt")]
        
        with pytest.raises(Exception, match="LLM error"):
            await wrapper.create_completion(messages=messages)
        
        # Verify error was intercepted
        mock_interceptor.intercept_error.assert_called_once()
        error_args = mock_interceptor.intercept_error.call_args
        assert error_args.args[0] == "test-agent"
        assert str(error_args.args[1]) == "LLM error"
    
    @pytest.mark.asyncio
    async def test_wrapper_context_propagation(self, mock_llm_client, mock_interceptor):
        """Test wrapper propagates conversation context from agent."""
        # Create wrapper with agent reference
        mock_agent = MagicMock()
        mock_agent.current_conversation_id = "conv-123"
        
        wrapper = ConversationAwareLLMWrapper(
            client=mock_llm_client,
            interceptor=mock_interceptor,
            agent_id="test-agent",
            default_model="test-model",
            agent_ref=mock_agent
        )
        
        messages = [LLMMessage(role="user", content="Test")]
        
        # Mock context vars
        with patch('src.database.conversation_interceptor.current_conversation_id') as mock_conv_id:
            with patch('src.database.conversation_interceptor.current_agent_id') as mock_agent_id:
                mock_conv_id.get.return_value = None  # No context set initially
                
                await wrapper.create_completion(messages=messages)
                
                # Verify context was set from agent
                mock_conv_id.set.assert_called_with("conv-123")
                mock_agent_id.set.assert_called_with("test-agent")


class TestLLMAgentInitialization:
    """Test LLM agent initialization with conversation tracking."""
    
    @pytest.mark.asyncio
    @patch('src.agents.llm_agent.OpenRouterClient')
    async def test_agent_initializes_with_wrapped_client(self, mock_client_class):
        """Test agent initializes with wrapped client when tracking enabled."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(config=config, enable_conversation_tracking=True)

        # Mock the conversation components
        with patch.object(agent, 'conversation_interceptor', AsyncMock()):
            with patch.object(agent, 'conversation_store', AsyncMock()):
                await agent.initialize()

                # Verify wrapped client was created
                assert agent._wrapped_client is not None
                assert isinstance(agent._wrapped_client, ConversationAwareLLMWrapper)
                assert agent._wrapped_client.agent_id == agent.agent_id
                assert agent._wrapped_client.default_model == "test-model"
    
    @pytest.mark.asyncio
    @patch('src.agents.llm_agent.OpenRouterClient')
    async def test_agent_no_wrapper_when_tracking_disabled(self, mock_client_class):
        """Test agent doesn't create wrapper when tracking disabled."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(config=config, enable_conversation_tracking=False)

        await agent.initialize()

        # Verify no wrapped client, using direct client
        assert agent._wrapped_client == mock_client
        assert not isinstance(agent._wrapped_client, ConversationAwareLLMWrapper)


class TestSpecializedAgents:
    """Test specialized LLM agent types."""
    
    @pytest.mark.parametrize("agent_class,expected_model,expected_temp", [
        (LLMWorkerAgent, "x-ai/grok-3-mini", 0.7),
        (LLMAnalyzerAgent, "openai/gpt-4o", 0.3),
        (LLMValidatorAgent, "x-ai/grok-3-mini", 0.1),
        (LLMOrchestratorAgent, "x-ai/grok-4.1-fast", 0.5),
    ])
    def test_specialized_agent_defaults(self, agent_class, expected_model, expected_temp):
        """Test specialized agents have correct default settings."""
        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent"
        )
        agent = agent_class(config=config)

        assert agent.model == expected_model
        assert agent.temperature == expected_temp
        assert agent.enable_conversation_tracking is True
    
    def test_specialized_agents_can_override_tracking(self):
        """Test specialized agents can disable conversation tracking."""
        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent"
        )
        agent = LLMWorkerAgent(config=config, enable_conversation_tracking=False)

        assert agent.enable_conversation_tracking is False
    
    def test_specialized_agents_have_appropriate_prompts(self):
        """Test each specialized agent has appropriate system prompts."""
        worker_config = AgentConfig(name="Worker", agent_type="llm_worker")
        worker = LLMWorkerAgent(config=worker_config)
        assert "worker agent" in worker.system_prompt.lower()

        analyzer_config = AgentConfig(name="Analyzer", agent_type="llm_analyzer")
        analyzer = LLMAnalyzerAgent(config=analyzer_config)
        assert "analyzer" in analyzer.system_prompt.lower()
        assert "analysis" in analyzer.system_prompt.lower()

        validator_config = AgentConfig(name="Validator", agent_type="llm_validator")
        validator = LLMValidatorAgent(config=validator_config)
        assert "validator" in validator.system_prompt.lower()
        assert "validation" in validator.system_prompt.lower()

        orchestrator_config = AgentConfig(name="Orchestrator", agent_type="llm_orchestrator")
        orchestrator = LLMOrchestratorAgent(config=orchestrator_config)
        assert "orchestrator" in orchestrator.system_prompt.lower()
        assert "workflow" in orchestrator.system_prompt.lower()