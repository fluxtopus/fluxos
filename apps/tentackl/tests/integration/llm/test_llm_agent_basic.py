"""Basic test for LLMAgent to isolate issues."""

import pytest
import uuid
import asyncio
from typing import Dict, Any, List, Optional

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse


class BasicMockLLMClient(LLMInterface):
    """Basic mock LLM client."""
    
    async def create_completion(self, messages, model, **kwargs):
        """Return a basic response."""
        print(f"Mock create_completion called with model={model}")
        await asyncio.sleep(0.05)
        
        return LLMResponse(
            content='{"status": "success", "result": "done"}',
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
class TestLLMAgentBasic:
    """Basic test for LLMAgent."""
    
    @pytest.mark.asyncio
    async def test_basic_execution(self, test_db):
        """Test basic LLMAgent execution without conversation tracking."""
        # Create agent config
        config = AgentConfig(
            name="Basic Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )

        # Create agent without conversation tracking
        agent = LLMAgent(
            config=config,
            llm_client=BasicMockLLMClient(),
            enable_conversation_tracking=False
        )
        
        try:
            # Initialize
            await agent.initialize()
            
            # Execute task
            task = {"description": "Basic test"}
            result = await agent.execute(task)
            
            # Check result
            print(f"Result: {result}")
            assert result["status"] == "success"
            assert result["result"] == "done"
            assert result["metadata"]["model"] == "test-model"
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_with_conversation_tracking(self, test_db):
        """Test LLMAgent with conversation tracking enabled."""
        # Create agent config
        config = AgentConfig(
            name="Tracked Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )

        # Create agent with conversation tracking
        agent = LLMAgent(
            config=config,
            llm_client=BasicMockLLMClient(),
            enable_conversation_tracking=True
        )
        
        try:
            # Initialize
            await agent.initialize()
            
            # Verify conversation tracking is enabled
            assert agent.enable_conversation_tracking is True
            assert agent.conversation_store is not None
            
            # Execute task
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "description": "Tracked test"
            }
            
            result = await agent.execute(task)
            
            # Check result
            print(f"Result: {result}")
            assert result["status"] == "success"
            
            # Basic check that conversation was created
            assert agent.current_conversation_id is not None
            
        finally:
            await agent.shutdown()