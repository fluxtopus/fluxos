"""Simplified integration test for LLMAgent with conversation tracking."""

import pytest
import uuid
import asyncio
from typing import Dict, Any, List, Optional

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.database.models import ConversationStatus
from src.database.conversation_store import ConversationQuery
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse


class SimpleMockLLMClient(LLMInterface):
    """Simple mock LLM client for testing."""
    
    async def create_completion(self, messages, model, **kwargs):
        """Create a simple response."""
        await asyncio.sleep(0.1)  # Simulate processing
        
        return LLMResponse(
            content='{"status": "success", "result": "processed"}',
            model=model,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )
    
    async def create_completion_stream(self, messages, model, **kwargs):
        yield "test"
    
    async def list_models(self):
        return [{"id": "test-model"}]
    
    async def health_check(self):
        return True


@pytest.mark.integration
@pytest.mark.conversation
class TestLLMAgentConversationSimple:
    """Simplified test for LLMAgent conversation tracking."""
    
    @pytest.mark.asyncio
    async def test_basic_llm_agent_conversation(self, test_db):
        """Test basic LLMAgent conversation tracking."""
        # Create agent
        config = AgentConfig(
            name="Test Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=SimpleMockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "test_agent"  # Set for test verification
        
        try:
            # Initialize
            await agent.initialize()
            
            # Execute task
            task = {
                "workflow_id": str(uuid.uuid4()),
                "description": "Test task"
            }
            
            result = await agent.execute(task)
            
            # Check result
            print(f"Result: {result}")
            assert result["status"] == "success"
            
            # Verify conversation was created
            query = ConversationQuery(workflow_id=task["workflow_id"])
            conversations = await agent.conversation_store.search_conversations(query)
            
            assert len(conversations) == 1
            assert conversations[0].status == ConversationStatus.COMPLETED
            
        finally:
            await agent.shutdown()