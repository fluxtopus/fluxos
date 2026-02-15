"""Integration test for LLMAgent with conversation tracking."""

import pytest
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.agents.stateful_agent import StatefulAgentConfig
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.database.models import ConversationStatus, TriggerType, MessageType
from src.database.conversation_store import ConversationQuery
from src.core.config import settings
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse


class MockLLMClient(LLMInterface):
    """Mock LLM client for testing."""
    
    def __init__(self):
        self.call_count = 0
        self.last_messages = None
        self.last_kwargs = None
    
    async def create_completion(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """Mock completion that returns a structured response."""
        self.call_count += 1
        self.last_messages = messages
        self.last_kwargs = kwargs
        
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        # Return a mock response based on the user message
        user_message = messages[-1].content if messages else ""
        
        # Return an LLMResponse object with all required fields
        response = LLMResponse(
            content='{"status": "success", "result": "Task processed successfully", "metadata": {"processed": true}}',
            model=model,
            usage={"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
        )
        # Ensure the response has the model attribute
        response.model = model
        return response
    
    async def create_completion_stream(self, messages, model, **kwargs):
        """Mock streaming completion."""
        yield "Mock stream response"
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Mock model listing."""
        return [{"id": "mock-model", "name": "Mock Model"}]
    
    async def health_check(self) -> bool:
        """Mock health check."""
        return True


@pytest.mark.integration
@pytest.mark.conversation
class TestLLMAgentConversation:
    """Test LLMAgent with conversation tracking integration."""
    
    @pytest.mark.asyncio
    async def test_llm_agent_conversation_tracking(self, test_db):
        """Test that LLMAgent automatically tracks LLM calls."""
        # Create mock LLM client
        mock_client = MockLLMClient()

        # Create LLM agent with conversation tracking enabled
        config = AgentConfig(
            name="Test LLM Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model", "temperature": 0.7}
        )
        agent = LLMAgent(
            config=config,
            llm_client=mock_client,
            enable_conversation_tracking=True
        )
        agent.agent_id = "test_llm_agent"  # Set for test verification
        
        try:
            # Initialize agent
            await agent.initialize()
            
            # Verify conversation tracking is enabled
            assert agent.enable_conversation_tracking is True
            assert agent.conversation_store is not None
            assert agent.conversation_interceptor is not None
            assert agent._wrapped_client is not None
            
            # Execute a task
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "description": "Analyze this data",
                "data": {"values": [1, 2, 3, 4, 5]},
                "max_tokens": 500
            }
            
            result = await agent.execute(task)
            
            # Verify result
            assert result["status"] == "success"
            assert result["result"] == "Task processed successfully"
            assert mock_client.call_count == 1
            
            # Query the conversation
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await agent.conversation_store.search_conversations(query)
            
            assert len(conversations) == 1
            conversation = conversations[0]
            
            assert conversation.workflow_id == uuid.UUID(workflow_id)
            assert conversation.root_agent_id == "test_llm_agent"  # We passed this as agent_id
            assert conversation.status == ConversationStatus.COMPLETED
            
            # Get conversation with messages
            conv_view = await agent.conversation_store.get_conversation(
                str(conversation.id),
                include_messages=True
            )
            
            # Debug: print all messages
            print(f"\nTotal messages: {len(conv_view.messages)}")
            for msg in conv_view.messages:
                print(f"  - {msg.message_type.value}: {msg.direction.value if msg.direction else 'N/A'}")
            
            # Find LLM messages
            llm_messages = [
                msg for msg in conv_view.messages
                if msg.message_type.value in [MessageType.LLM_PROMPT.value, MessageType.LLM_RESPONSE.value]
            ]
            
            # Should have at least one LLM call and one response
            assert len(llm_messages) >= 2
            
            # Find the request message
            request_msgs = [m for m in llm_messages if m.direction.value == "outbound"]
            assert len(request_msgs) >= 1
            request_msg = request_msgs[0]
            
            assert "Analyze this data" in request_msg.content_text
            assert request_msg.model == "mock-model"
            assert request_msg.temperature == 0.7
            
            # Find the response message
            response_msgs = [m for m in llm_messages if m.direction.value == "inbound"]
            assert len(response_msgs) >= 1
            response_msg = response_msgs[0]
            
            assert "Task processed successfully" in response_msg.content_text
            assert response_msg.prompt_tokens == 50
            assert response_msg.completion_tokens == 30
            assert response_msg.total_tokens == 80
            assert response_msg.latency_ms > 0
            
            # Verify state updates were tracked
            state_messages = [
                msg for msg in conv_view.messages
                if msg.message_type == MessageType.STATE_UPDATE
            ]
            
            assert len(state_messages) > 0
            
            # Verify cost tracking
            metrics = await agent.conversation_store._get_or_create_metrics(conversation.id)
            assert metrics.total_llm_calls == 1
            assert metrics.total_tokens == 80
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_llm_agent_error_tracking(self, test_db):
        """Test conversation tracking when LLM call fails."""
        # Create mock LLM client that raises error
        mock_client = AsyncMock(spec=LLMInterface)
        mock_client.health_check.return_value = True
        mock_client.create_completion.side_effect = Exception("LLM API error")

        config = AgentConfig(
            name="Test Error Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=mock_client,
            enable_conversation_tracking=True
        )
        agent.agent_id = "test_error_agent"  # Set for test verification
        
        try:
            await agent.initialize()
            
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "description": "This will fail"
            }
            
            # Execute should raise error
            with pytest.raises(Exception, match="LLM API error"):
                await agent.execute(task)
            
            # Verify conversation was marked as failed
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await agent.conversation_store.search_conversations(query)
            
            assert len(conversations) == 1
            conversation = conversations[0]
            
            assert conversation.status == ConversationStatus.FAILED
            
            # Get messages to verify error was logged
            conv_view = await agent.conversation_store.get_conversation(
                str(conversation.id),
                include_messages=True
            )
            
            # Find error messages
            error_messages = [
                msg for msg in conv_view.messages
                if msg.message_type == MessageType.ERROR
            ]
            
            assert len(error_messages) >= 1
            assert "LLM API error" in error_messages[0].content_text
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_llm_agent_without_conversation_tracking(self, test_db):
        """Test that LLM agent works without conversation tracking."""
        mock_client = MockLLMClient()
        
        # Create config with conversation tracking disabled
        config = StatefulAgentConfig(
            name="test_no_tracking",
            agent_type="llm_agent",
            state_store=RedisStateStore(
                redis_url=settings.REDIS_URL.replace('/0', '/13'),
                db=13
            ),
            enable_conversation_tracking=False
        )
        
        # We need to create a custom LLMAgent that accepts StatefulAgentConfig
        from src.agents.llm_agent import LLMAgent as BaseLLMAgent
        
        class TestLLMAgent(BaseLLMAgent):
            def __init__(self, config: StatefulAgentConfig, llm_client, model):
                # Initialize StatefulAgent with config
                from src.agents.stateful_agent import StatefulAgent
                StatefulAgent.__init__(self, config)
                
                self.agent_id = str(uuid.uuid4())
                self.name = config.name
                self.llm_client = llm_client
                self.model = model
                self.temperature = 0.7
                self.system_prompt = self._default_system_prompt()
                self._client_context = None
                self._wrapped_client = None
        
        agent = TestLLMAgent(config, mock_client, "mock-model")
        
        try:
            await agent.initialize()
            
            # Verify conversation tracking is disabled
            assert agent.enable_conversation_tracking is False
            assert agent.conversation_store is None
            assert agent.conversation_interceptor is None
            assert agent._wrapped_client == mock_client  # No wrapper
            
            # Execute should work without conversation tracking
            result = await agent.execute({
                "description": "Test task",
                "data": {"test": "value"}
            })
            
            assert result["status"] == "success"
            assert mock_client.call_count == 1
            
        finally:
            await agent.shutdown()