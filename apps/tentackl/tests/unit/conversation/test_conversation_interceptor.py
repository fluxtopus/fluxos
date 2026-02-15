"""Unit tests for ConversationInterceptor."""

import pytest
import uuid
from datetime import datetime
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock

from src.database.conversation_interceptor import (
    ConversationInterceptor, MessageInterception, LLMClientWrapper,
    current_conversation_id, current_agent_id
)
from src.database.conversation_store import ConversationStore, ConversationTrigger
from src.database.models import TriggerType, MessageType, MessageDirection


@pytest.mark.interceptor
class TestConversationInterceptor:
    """Test ConversationInterceptor functionality."""
    
    @pytest.mark.asyncio
    async def test_set_context(self):
        """Test setting conversation context."""
        store = Mock(spec=ConversationStore)
        interceptor = ConversationInterceptor(store)
        
        conv_id = str(uuid.uuid4())
        agent_id = "test_agent"
        
        interceptor.set_context(conv_id, agent_id)
        
        assert current_conversation_id.get() == conv_id
        assert current_agent_id.get() == agent_id
    
    @pytest.mark.asyncio
    async def test_intercept_llm_call(self):
        """Test intercepting LLM calls."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        
        # Set context
        conv_id = str(uuid.uuid4())
        interceptor.set_context(conv_id, "test_agent")
        
        # Intercept LLM call
        result = await interceptor.intercept_llm_call(
            agent_id="test_agent",
            prompt="Test prompt",
            model="gpt-4",
            temperature=0.7,
            max_tokens=100
        )
        
        assert isinstance(result, MessageInterception)
        assert result.message_id is not None
        
        # Verify store was called
        store.add_message.assert_called_once()
        call_args = store.add_message.call_args[0]
        assert call_args[0] == conv_id
        
        message_data = call_args[1]
        assert message_data.agent_id == "test_agent"
        assert message_data.message_type == MessageType.LLM_PROMPT
        assert message_data.direction == MessageDirection.OUTBOUND
        assert message_data.content.text == "Test prompt"
        assert message_data.metadata.model == "gpt-4"
        assert message_data.metadata.temperature == 0.7
    
    @pytest.mark.asyncio
    async def test_intercept_llm_response_openai_format(self):
        """Test intercepting LLM response in OpenAI format."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        interceptor.set_context(str(uuid.uuid4()), "test_agent")
        
        # Mock OpenAI response
        response = Mock()
        response.choices = [Mock(message=Mock(content="Test response"))]
        response.usage = Mock(
            prompt_tokens=50,
            completion_tokens=100,
            total_tokens=150
        )
        response.model = "gpt-4"
        
        result = await interceptor.intercept_llm_response(
            agent_id="test_agent",
            response=response,
            latency_ms=1200
        )
        
        assert isinstance(result, MessageInterception)
        
        # Verify message data
        call_args = store.add_message.call_args[0]
        message_data = call_args[1]
        
        assert message_data.message_type == MessageType.LLM_RESPONSE
        assert message_data.direction == MessageDirection.INBOUND
        assert message_data.content.text == "Test response"
        assert message_data.metadata.tokens == {
            'prompt': 50,
            'completion': 100,
            'total': 150
        }
        assert message_data.metadata.latency_ms == 1200
    
    @pytest.mark.asyncio
    async def test_intercept_llm_response_dict_format(self):
        """Test intercepting LLM response in dict format."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        interceptor.set_context(str(uuid.uuid4()), "test_agent")
        
        # Dict format response
        response = {
            "content": "Test response",
            "model": "claude-3",
            "usage": {
                "prompt": 60,
                "completion": 120,
                "total": 180
            },
            "cost": 0.003
        }
        
        result = await interceptor.intercept_llm_response(
            agent_id="test_agent",
            response=response,
            latency_ms=800
        )
        
        # Verify message data
        call_args = store.add_message.call_args[0]
        message_data = call_args[1]
        
        assert message_data.content.text == "Test response"
        assert message_data.metadata.model == "claude-3"
        assert message_data.cost.amount == 0.003
    
    @pytest.mark.asyncio
    async def test_intercept_tool_call(self):
        """Test intercepting tool calls."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        interceptor.set_context(str(uuid.uuid4()), "test_agent")
        
        result = await interceptor.intercept_tool_call(
            agent_id="test_agent",
            tool_name="weather_api",
            parameters={"location": "Porto", "date": "2025-08-02"}
        )
        
        assert isinstance(result, MessageInterception)
        
        # Verify message data
        call_args = store.add_message.call_args[0]
        message_data = call_args[1]
        
        assert message_data.message_type == MessageType.TOOL_CALL
        assert message_data.direction == MessageDirection.OUTBOUND
        assert "weather_api" in message_data.content.text
        assert message_data.content.tool_calls[0]["tool"] == "weather_api"
        assert message_data.content.tool_calls[0]["parameters"]["location"] == "Porto"
    
    @pytest.mark.asyncio
    async def test_intercept_tool_response(self):
        """Test intercepting tool responses."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        interceptor.set_context(str(uuid.uuid4()), "test_agent")
        
        response_data = {"precipitation": 75, "temperature": 22}
        
        result = await interceptor.intercept_tool_response(
            agent_id="test_agent",
            tool_name="weather_api",
            response=response_data,
            latency_ms=500,
            parent_message_id="parent_123"
        )
        
        # Verify message data
        call_args = store.add_message.call_args[0]
        message_data = call_args[1]
        
        assert message_data.message_type == MessageType.TOOL_RESPONSE
        assert message_data.direction == MessageDirection.INBOUND
        assert message_data.content.data["response"] == response_data
        assert message_data.metadata.latency_ms == 500
        assert message_data.parent_message_id == "parent_123"
    
    @pytest.mark.asyncio
    async def test_intercept_error(self):
        """Test intercepting errors."""
        store = Mock(spec=ConversationStore)
        store.add_message = AsyncMock(return_value=True)
        
        interceptor = ConversationInterceptor(store)
        interceptor.set_context(str(uuid.uuid4()), "test_agent")
        
        error = ValueError("Test error message")
        context = {"operation": "test_operation", "input": "test_input"}
        
        result = await interceptor.intercept_error(
            agent_id="test_agent",
            error=error,
            context=context
        )
        
        # Verify message data
        call_args = store.add_message.call_args[0]
        message_data = call_args[1]
        
        assert message_data.message_type == MessageType.ERROR
        assert message_data.direction == MessageDirection.INTERNAL
        assert "ValueError" in message_data.content.text
        assert "Test error message" in message_data.content.text
        assert message_data.content.data["error_type"] == "ValueError"
        assert message_data.content.data["context"] == context
    
    @pytest.mark.asyncio
    async def test_no_context_handling(self):
        """Test handling calls without context."""
        store = Mock(spec=ConversationStore)
        interceptor = ConversationInterceptor(store)
        
        # Clear any existing context
        current_conversation_id.set(None)
        
        # Try to intercept without context
        result = await interceptor.intercept_llm_call(
            agent_id="test_agent",
            prompt="Test",
            model="gpt-4"
        )
        
        assert result.message_id == "no-context"
        
        # Store should not be called
        store.add_message.assert_not_called()


@pytest.mark.interceptor
class TestLLMClientWrapper:
    """Test LLMClientWrapper functionality."""
    
    @pytest.mark.asyncio
    async def test_successful_llm_call(self):
        """Test wrapping a successful LLM call."""
        # Mock LLM client
        mock_client = AsyncMock()
        mock_response = {"content": "Test response", "model": "gpt-4"}
        mock_client.return_value = mock_response
        
        # Mock interceptor
        mock_interceptor = Mock(spec=ConversationInterceptor)
        mock_interceptor.intercept_llm_call = AsyncMock(
            return_value=MessageInterception("msg_123", datetime.utcnow())
        )
        mock_interceptor.intercept_llm_response = AsyncMock(
            return_value=MessageInterception("msg_124", datetime.utcnow())
        )
        
        # Create wrapper
        current_agent_id.set("test_agent")
        wrapper = LLMClientWrapper(mock_client, mock_interceptor)
        
        # Make call
        result = await wrapper("Test prompt", model="gpt-4", temperature=0.7)
        
        assert result == mock_response
        
        # Verify interceptor was called
        mock_interceptor.intercept_llm_call.assert_called_once_with(
            "test_agent",
            "Test prompt",
            "gpt-4",
            model="gpt-4",
            temperature=0.7
        )
        
        mock_interceptor.intercept_llm_response.assert_called_once()
        response_args = mock_interceptor.intercept_llm_response.call_args[0]
        assert response_args[0] == "test_agent"
        assert response_args[1] == mock_response
        assert response_args[2] >= 0  # latency_ms
    
    @pytest.mark.asyncio
    async def test_llm_call_with_error(self):
        """Test wrapping an LLM call that raises an error."""
        # Mock LLM client that raises error
        mock_client = AsyncMock()
        mock_client.side_effect = Exception("LLM API Error")
        
        # Mock interceptor
        mock_interceptor = Mock(spec=ConversationInterceptor)
        mock_interceptor.intercept_llm_call = AsyncMock(
            return_value=MessageInterception("msg_123", datetime.utcnow())
        )
        mock_interceptor.intercept_error = AsyncMock(
            return_value=MessageInterception("msg_125", datetime.utcnow())
        )
        
        # Create wrapper
        wrapper = LLMClientWrapper(mock_client, mock_interceptor)
        
        # Make call that should raise error
        with pytest.raises(Exception, match="LLM API Error"):
            await wrapper("Test prompt", model="gpt-4")
        
        # Verify error was intercepted
        mock_interceptor.intercept_error.assert_called_once()
        error_args = mock_interceptor.intercept_error.call_args[0]
        assert isinstance(error_args[1], Exception)
        assert str(error_args[1]) == "LLM API Error"