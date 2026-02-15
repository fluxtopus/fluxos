"""Debug test for LLMAgent conversation tracking context issue."""

import pytest
import uuid
import asyncio
from typing import Dict, Any, List, Optional
import structlog

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.database.conversation_interceptor import current_conversation_id, current_agent_id

logger = structlog.get_logger()


class DebugMockLLMClient(LLMInterface):
    """Debug mock LLM client."""
    
    async def create_completion(self, messages, model, **kwargs):
        """Create a response with debug logging."""
        logger.info("MockLLMClient.create_completion called",
                   model=model,
                   conversation_id=current_conversation_id.get(),
                   agent_id=current_agent_id.get())
        
        await asyncio.sleep(0.05)
        
        return LLMResponse(
            content='{"status": "success", "result": "debug test complete"}',
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
class TestLLMAgentDebug:
    """Debug test for context variable issue."""
    
    @pytest.mark.asyncio
    async def test_context_propagation(self, test_db):
        """Test context variable propagation to LLM wrapper."""
        # Create agent
        config = AgentConfig(
            name="Debug Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=DebugMockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "debug_agent"  # Set for test verification
        
        try:
            # Initialize
            await agent.initialize()
            
            # Log initial state
            logger.info("After initialize",
                       enable_tracking=agent.enable_conversation_tracking,
                       has_interceptor=agent.conversation_interceptor is not None,
                       has_wrapper=agent._wrapped_client is not None)
            
            # Execute task
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "description": "Debug context test"
            }
            
            # Log context before execute
            logger.info("Before execute",
                       conversation_id=current_conversation_id.get(),
                       agent_id=current_agent_id.get())
            
            result = await agent.execute(task)
            
            # Log context after execute
            logger.info("After execute",
                       conversation_id=current_conversation_id.get(),
                       agent_id=current_agent_id.get(),
                       result_status=result.get("status"))
            
            # Check result
            assert result["status"] == "success"
            
            # Check if conversation was created
            if agent.enable_conversation_tracking:
                assert agent.current_conversation_id is not None
                logger.info("Conversation created",
                           conversation_id=agent.current_conversation_id)
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_manual_context_setting(self, test_db):
        """Test manually setting context variables."""
        # Set context variables manually
        test_conv_id = str(uuid.uuid4())
        test_agent_id = "manual_test_agent"
        
        current_conversation_id.set(test_conv_id)
        current_agent_id.set(test_agent_id)
        
        # Verify they are set
        assert current_conversation_id.get() == test_conv_id
        assert current_agent_id.get() == test_agent_id

        # Create agent
        config = AgentConfig(
            name="Manual Agent",
            agent_type="llm_agent",
            metadata={"model": "test-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=DebugMockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "manual_agent"  # Set for test verification
        
        try:
            await agent.initialize()
            
            # The context should still be set
            logger.info("After agent init with manual context",
                       conversation_id=current_conversation_id.get(),
                       agent_id=current_agent_id.get())
            
            # Execute task
            result = await agent.process_task({
                "description": "Manual context test"
            })
            
            assert result["status"] == "success"
            
        finally:
            await agent.shutdown()