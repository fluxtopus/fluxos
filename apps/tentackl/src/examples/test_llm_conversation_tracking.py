"""Test script to verify LLM conversation tracking."""

import asyncio
import uuid
from src.agents.llm_agent import LLMAgent
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from typing import List, Optional
import structlog

logger = structlog.get_logger()


class TestLLMClient(LLMInterface):
    """Test LLM client that returns predictable responses."""
    
    async def create_completion(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Return a test response."""
        logger.info("TestLLMClient.create_completion called", model=model, temperature=temperature)
        return LLMResponse(
            content='{"status": "success", "result": "Test response", "metadata": {"test": true}}',
            model=model,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        )
    
    async def create_completion_stream(self, messages, **kwargs):
        yield "Test stream"
    
    async def list_models(self):
        return [{"id": "test-model", "name": "Test Model"}]
    
    async def health_check(self):
        return True


async def main():
    """Test LLM conversation tracking."""
    logger.info("Starting LLM conversation tracking test")
    
    # Create LLM agent with conversation tracking
    agent = LLMAgent(
        agent_id="test-agent-1",
        name="Test Agent",
        llm_client=TestLLMClient(),
        model="test-model",
        temperature=0.5,
        enable_conversation_tracking=True
    )
    
    try:
        # Initialize agent
        await agent.initialize()
        logger.info("Agent initialized", 
                   tracking_enabled=agent.enable_conversation_tracking,
                   has_interceptor=agent.conversation_interceptor is not None,
                   has_wrapped_client=agent._wrapped_client is not None)
        
        # Execute a task
        task = {
            "workflow_id": str(uuid.uuid4()),
            "description": "Test task",
            "data": {"test": True}
        }
        
        result = await agent.execute(task)
        logger.info("Task executed", result=result)
        
        # Check if conversation was tracked
        if agent.current_conversation_id:
            logger.info("Conversation tracked!", conversation_id=agent.current_conversation_id)
            
            # Query the conversation
            if agent.conversation_store:
                from src.database.conversation_store import ConversationQuery
                query = ConversationQuery(
                    conversation_id=agent.current_conversation_id
                )
                conversations = await agent.conversation_store.query_conversations(query)
                
                if conversations:
                    conv = conversations[0]
                    logger.info("Conversation found", 
                               workflow_id=conv.workflow_id,
                               status=conv.status.value)
                    
                    # Get conversation view
                    conv_view = await agent.conversation_store.get_conversation_view(
                        agent.current_conversation_id
                    )
                    
                    if conv_view:
                        logger.info("Conversation messages", 
                                   total_messages=len(conv_view.messages))
                        for msg in conv_view.messages:
                            logger.info(f"  Message: {msg.message_type.value} - {msg.direction.value if msg.direction else 'N/A'}")
                else:
                    logger.warning("No conversation found in store")
        else:
            logger.warning("No conversation ID set")
            
    finally:
        await agent.cleanup()
        logger.info("Test completed")


if __name__ == "__main__":
    asyncio.run(main())