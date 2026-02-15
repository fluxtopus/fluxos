"""Test conversation persistence across agent restarts."""

import asyncio
import uuid
from src.agents.llm_agent import LLMAgent
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.database.conversation_store import ConversationStore
from src.database.models import ConversationStatus
from src.interfaces.database import Database
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
        return LLMResponse(
            content='{"status": "success", "result": "Persisted response", "metadata": {"persisted": true}}',
            model=model,
            usage={"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40}
        )
    
    async def create_completion_stream(self, messages, **kwargs):
        yield "Test stream"
    
    async def list_models(self):
        return [{"id": "test-model", "name": "Test Model"}]
    
    async def health_check(self):
        return True


async def phase1_create_conversation():
    """Phase 1: Create a conversation and return its ID."""
    logger.info("=== Phase 1: Creating conversation ===")
    
    agent = LLMAgent(
        agent_id="persist-agent-1",
        name="Persistence Test Agent",
        llm_client=TestLLMClient(),
        model="test-model",
        temperature=0.7,
        enable_conversation_tracking=True
    )
    
    try:
        await agent.initialize()
        
        # Execute a task to create conversation
        task = {
            "workflow_id": str(uuid.uuid4()),
            "description": "Create persistent conversation",
            "data": {"phase": 1}
        }
        
        result = await agent.execute(task)
        logger.info("Task executed", result=result)
        
        conversation_id = agent.current_conversation_id
        logger.info("Conversation created", conversation_id=conversation_id)
        
        return conversation_id
        
    finally:
        await agent.cleanup()


async def phase2_retrieve_conversation(conversation_id: str):
    """Phase 2: Retrieve the conversation created in phase 1."""
    logger.info("=== Phase 2: Retrieving conversation ===", conversation_id=conversation_id)
    
    # Create a new database connection to query the conversation
    db = Database()
    try:
        await db.connect()
        store = ConversationStore(db)
        
        # Get conversation
        conv_view = await store.get_conversation(conversation_id)
        
        if conv_view:
            conversation = conv_view.conversation
            logger.info("Conversation retrieved successfully!")
            logger.info(f"Workflow ID: {conversation.workflow_id}")
            logger.info(f"Status: {conversation.status.value}")
            logger.info(f"Start time: {conversation.start_time}")
            logger.info(f"End time: {conversation.end_time}")
            
            # Messages are included in conv_view
            messages = conv_view.messages
            logger.info(f"Total messages: {len(messages)}")
            
            # Show messages
            for msg in messages:
                if msg.message_type.value in ['LLM_PROMPT', 'LLM_RESPONSE']:
                    logger.info(f"  {msg.message_type.value}: {msg.content_text[:50]}...")
            
            # Count LLM messages
            llm_messages = [m for m in messages if m.message_type.value.startswith('LLM')]
            logger.info(f"Total LLM messages: {len(llm_messages)}")
            
            return True
        else:
            logger.error("Conversation not found!")
            return False
            
    finally:
        await db.disconnect()


async def main():
    """Test conversation persistence."""
    try:
        # Phase 1: Create conversation
        conversation_id = await phase1_create_conversation()
        
        if conversation_id:
            # Simulate agent restart with a delay
            logger.info("Simulating agent restart...")
            await asyncio.sleep(1)
            
            # Phase 2: Retrieve conversation
            success = await phase2_retrieve_conversation(conversation_id)
            
            if success:
                logger.info("✅ Conversation persistence test PASSED!")
            else:
                logger.error("❌ Conversation persistence test FAILED!")
        else:
            logger.error("Failed to create conversation in phase 1")
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())