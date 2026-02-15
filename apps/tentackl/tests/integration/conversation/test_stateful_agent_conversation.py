"""Integration test for StatefulAgent with conversation tracking."""

import pytest
import uuid
import asyncio
from typing import Dict, Any

from src.agents.stateful_agent import StatefulAgent, StatefulAgentConfig
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.database.models import ConversationStatus, TriggerType
from src.database.conversation_store import ConversationQuery
from src.core.config import settings


class TestStatefulAgent(StatefulAgent):
    """Test implementation of StatefulAgent."""
    
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """Simple execution logic for testing."""
        operation = task.get("operation", "test")
        
        if operation == "success":
            await self.update_state({"status": "processing", "operation": operation})
            await asyncio.sleep(0.1)  # Simulate work
            return {"result": "success", "data": task.get("data", {})}
        
        elif operation == "error":
            await self.update_state({"status": "error", "operation": operation})
            raise ValueError("Test error occurred")
        
        else:
            return {"result": "unknown", "operation": operation}


@pytest.mark.integration
@pytest.mark.conversation
class TestStatefulAgentConversation:
    """Test StatefulAgent with conversation tracking integration."""
    
    @pytest.mark.asyncio
    async def test_stateful_agent_conversation_tracking(self, test_db):
        """Test that StatefulAgent automatically tracks conversations."""
        # Create agent with conversation tracking enabled
        config = StatefulAgentConfig(
            name="test_stateful_agent",
            agent_type="test",
            state_store=RedisStateStore(
                redis_url=settings.REDIS_URL.replace('/0', '/13'),
                db=13
            ),
            enable_conversation_tracking=True  # Enabled by default
        )
        
        agent = TestStatefulAgent(config)
        # Don't override agent_id - it's set automatically from self.id
        
        try:
            # Initialize agent
            await agent.initialize()
            
            # Verify conversation tracking is enabled
            assert agent.enable_conversation_tracking is True
            assert agent.conversation_store is not None
            assert agent.conversation_interceptor is not None
            
            # Execute a task
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "operation": "success",
                "data": {"test": "value"}
            }
            
            result = await agent.execute(task)
            
            # Verify result
            assert result["result"] == "success"
            
            # Verify conversation was created and ended
            assert agent.current_conversation_id is not None
            
            # Query the conversation
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await agent.conversation_store.search_conversations(query)
            
            assert len(conversations) == 1
            conversation = conversations[0]
            
            assert conversation.workflow_id == uuid.UUID(workflow_id)
            assert conversation.root_agent_id == agent.agent_id
            assert conversation.status == ConversationStatus.COMPLETED
            assert conversation.trigger_type == TriggerType.API_CALL
            
            # Get conversation with messages
            conv_view = await agent.conversation_store.get_conversation(
                str(conversation.id),
                include_messages=True
            )
            
            # Should have messages logged (state updates, etc.)
            assert len(conv_view.messages) > 0
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_stateful_agent_conversation_on_error(self, test_db):
        """Test conversation tracking when agent execution fails."""
        config = StatefulAgentConfig(
            name="test_error_agent",
            agent_type="test",
            state_store=RedisStateStore(
                redis_url=settings.REDIS_URL.replace('/0', '/13'),
                db=13
            )
        )
        
        agent = TestStatefulAgent(config)
        
        try:
            await agent.initialize()
            
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "operation": "error"
            }
            
            # Execute should raise error
            with pytest.raises(ValueError, match="Test error occurred"):
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
            
            # Find error message
            error_messages = [
                msg for msg in conv_view.messages
                if msg.message_type.value == "error"
            ]
            
            assert len(error_messages) >= 1
            assert "Test error occurred" in error_messages[0].content_text
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_disable_conversation_tracking(self, test_db):
        """Test that conversation tracking can be disabled."""
        config = StatefulAgentConfig(
            name="test_no_tracking",
            agent_type="test",
            enable_conversation_tracking=False  # Explicitly disable
        )
        
        agent = TestStatefulAgent(config)
        
        try:
            await agent.initialize()
            
            # Verify conversation tracking is disabled
            assert agent.enable_conversation_tracking is False
            assert agent.conversation_store is None
            assert agent.conversation_interceptor is None
            
            # Execute should work without conversation tracking
            result = await agent.execute({
                "operation": "success",
                "data": {"test": "value"}
            })
            
            assert result["result"] == "success"
            assert agent.current_conversation_id is None
            
        finally:
            await agent.shutdown()
    
    @pytest.mark.asyncio
    async def test_inter_agent_conversation(self, test_db):
        """Test conversation tracking for inter-agent communication."""
        # Create parent agent
        parent_config = StatefulAgentConfig(
            name="parent_agent",
            agent_type="test"
        )
        parent_agent = TestStatefulAgent(parent_config)
        
        # Create child agent
        child_config = StatefulAgentConfig(
            name="child_agent",
            agent_type="test"
        )
        child_agent = TestStatefulAgent(child_config)
        
        try:
            await parent_agent.initialize()
            await child_agent.initialize()
            
            # Parent executes task
            workflow_id = str(uuid.uuid4())
            parent_task = {
                "workflow_id": workflow_id,
                "operation": "success"
            }
            
            parent_result = await parent_agent.execute(parent_task)
            parent_conv_id = parent_agent.current_conversation_id
            
            # Child executes task triggered by parent
            child_task = {
                "workflow_id": workflow_id,
                "operation": "success",
                "parent_agent_id": parent_agent.agent_id,
                "parent_conversation_id": parent_conv_id,
                "trigger_type": "INTER_AGENT"
            }
            
            child_result = await child_agent.execute(child_task)
            
            # Query conversations
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await parent_agent.conversation_store.search_conversations(query)
            
            # Should have 2 conversations (parent and child)
            assert len(conversations) == 2
            
            # Find parent and child conversations
            parent_conv = next(c for c in conversations if c.root_agent_id == parent_agent.agent_id)
            child_conv = next(c for c in conversations if c.root_agent_id == child_agent.agent_id)
            
            # Verify relationship
            assert child_conv.parent_conversation_id == parent_conv.id
            assert child_conv.trigger_type == TriggerType.INTER_AGENT
            
        finally:
            await parent_agent.shutdown()
            await child_agent.shutdown()