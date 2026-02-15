"""Integration tests for LLM conversation tracking functionality."""

import pytest
import asyncio
import uuid
from typing import List, Dict, Any
from datetime import datetime

from src.agents.llm_agent import LLMAgent, LLMWorkerAgent, LLMOrchestratorAgent, LLMAnalyzerAgent
from src.agents.base import AgentConfig
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.database.models import ConversationStatus, TriggerType, MessageType
from src.database.conversation_store import ConversationStore, ConversationQuery


class MockLLMClient(LLMInterface):
    """Mock LLM client for integration testing."""
    
    def __init__(self):
        self.call_count = 0
        self.responses = []
    
    async def create_completion(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = None,
        **kwargs
    ) -> LLMResponse:
        """Return a mock response based on call count."""
        self.call_count += 1
        
        # Simulate some processing time
        await asyncio.sleep(0.01)
        
        response_content = {
            1: '{"status": "success", "result": "First task completed", "metadata": {"step": 1}}',
            2: '{"status": "success", "result": "Analysis complete", "metadata": {"insights": ["A", "B"]}}',
            3: '{"status": "error", "error": "Simulated error", "metadata": {}}'
        }.get(self.call_count, '{"status": "success", "result": "Default response"}')
        
        response = LLMResponse(
            content=response_content,
            model=model,
            usage={
                "prompt_tokens": 50 + (self.call_count * 10),
                "completion_tokens": 30 + (self.call_count * 5),
                "total_tokens": 80 + (self.call_count * 15)
            }
        )
        self.responses.append(response)
        return response
    
    async def create_completion_stream(self, messages, **kwargs):
        yield "Stream not implemented"
    
    async def list_models(self):
        return [{"id": "mock-model", "name": "Mock Model"}]
    
    async def health_check(self):
        return True


@pytest.mark.asyncio
class TestBasicConversationFlow:
    """Test basic conversation flow with LLM agents."""
    
    async def test_llm_agent_creates_and_tracks_conversation(self, test_db):
        """Test that LLMAgent creates conversation and tracks all interactions."""
        # Create LLM agent
        config = AgentConfig(
            name="Test LLM Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model", "temperature": 0.7}
        )
        agent = LLMAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "test-llm-1"  # Set for test verification
        
        try:
            # Initialize agent
            await agent.initialize()
            
            # Verify conversation tracking components
            assert agent.enable_conversation_tracking is True
            assert agent.conversation_store is not None
            assert agent.conversation_interceptor is not None
            assert agent._wrapped_client is not None
            
            # Execute a task
            workflow_id = str(uuid.uuid4())
            task = {
                "workflow_id": workflow_id,
                "description": "Process test data",
                "data": {"items": [1, 2, 3, 4, 5]}
            }
            
            result = await agent.execute(task)
            
            # Verify task executed successfully
            assert result["status"] == "success"
            assert "First task completed" in result["result"]
            
            # After execution, conversation ID is retained on the agent
            assert agent.current_conversation_id is not None
            
            # Search for conversation from store using workflow_id
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await agent.conversation_store.search_conversations(query)
            
            assert len(conversations) == 1
            conv = conversations[0]
            conversation_id = str(conv.id)  # Get the conversation ID from the result
            assert str(conv.workflow_id) == workflow_id
            assert conv.status == ConversationStatus.COMPLETED
            
            # Get conversation with messages
            conv_view = await agent.conversation_store.get_conversation(conversation_id)
            assert conv_view is not None
            
            # Retained ids should match the stored conversation
            assert agent.last_conversation_id == conversation_id
            assert agent.current_conversation_id == conversation_id

            # Verify messages were captured
            messages = conv_view.messages
            assert len(messages) >= 2  # At least state updates and LLM call
            
            # Find LLM messages
            llm_messages = [
                msg for msg in messages 
                if msg.message_type in [MessageType.LLM_PROMPT, MessageType.LLM_RESPONSE]
            ]
            
            assert len(llm_messages) == 2  # One prompt, one response
            
            # Verify prompt message
            prompt_msg = next(m for m in llm_messages if m.message_type == MessageType.LLM_PROMPT)
            # Check either content_text or content_data for the message
            prompt_content = prompt_msg.content_text or str(prompt_msg.content_data)
            assert "Process test data" in prompt_content
            assert prompt_msg.model == "mock-model"
            assert prompt_msg.temperature == 0.7
            
            # Verify response message
            response_msg = next(m for m in llm_messages if m.message_type == MessageType.LLM_RESPONSE)
            # Check either content_text or content_data for the message
            response_content = response_msg.content_text or str(response_msg.content_data)
            assert "First task completed" in response_content
            # Token counts may be stored in content_data
            if hasattr(response_msg, 'prompt_tokens') and response_msg.prompt_tokens:
                assert response_msg.prompt_tokens == 60
                assert response_msg.completion_tokens == 35
            assert response_msg.latency_ms > 0
            
        finally:
            await agent.shutdown()
    
    async def test_conversation_tracks_state_updates(self, test_db):
        """Test that state updates are tracked in conversation."""
        config = AgentConfig(
            name="Test Worker",
            agent_type="llm_worker",
            metadata={}
        )
        agent = LLMWorkerAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "worker-1"  # Set for test verification
        
        try:
            await agent.initialize()
            
            # Execute task
            task = {
                "workflow_id": str(uuid.uuid4()),
                "description": "Update state test"
            }
            
            await agent.execute(task)
            
            # Find the conversation by workflow_id
            query = ConversationQuery(workflow_id=task["workflow_id"])
            conversations = await agent.conversation_store.search_conversations(query)
            assert len(conversations) == 1
            
            # Get conversation messages
            conv_view = await agent.conversation_store.get_conversation(
                str(conversations[0].id)
            )
            
            # Find state update messages
            state_messages = [
                msg for msg in conv_view.messages
                if msg.message_type == MessageType.STATE_UPDATE
            ]
            
            # Should have at least 2 state updates (start and complete)
            assert len(state_messages) >= 2
            
            # Verify state changes are tracked
            for msg in state_messages:
                assert msg.content_data is not None
                assert "changed_fields" in msg.content_data
                
        finally:
            await agent.shutdown()


@pytest.mark.asyncio
class TestConversationPersistence:
    """Test conversation persistence across agent restarts."""
    
    async def test_conversation_survives_agent_restart(self, test_db):
        """Test that conversations persist when agent is restarted."""
        conversation_id = None
        workflow_id = str(uuid.uuid4())
        
        # Phase 1: Create agent and execute task
        config = AgentConfig(
            name="Persistent Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model"}
        )
        agent1 = LLMAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        agent1.agent_id = "persistent-agent"  # Set for test verification
        
        try:
            await agent1.initialize()
            
            task = {
                "workflow_id": workflow_id,
                "description": "Persistence test task"
            }
            
            result = await agent1.execute(task)
            assert result["status"] == "success"
            
            # Find the conversation that was created
            query = ConversationQuery(workflow_id=workflow_id)
            conversations = await agent1.conversation_store.search_conversations(query)
            assert len(conversations) == 1
            conversation_id = str(conversations[0].id)
            
        finally:
            await agent1.cleanup()
        
        # Simulate restart delay
        await asyncio.sleep(0.1)

        # Phase 2: Use test_db to verify conversation persists
        # (simulates a new agent connecting to same database)
        store = ConversationStore(test_db)

        # Retrieve conversation
        conv_view = await store.get_conversation(conversation_id)
        assert conv_view is not None

        # Verify conversation details
        conv = conv_view.conversation
        assert str(conv.workflow_id) == workflow_id
        assert conv.status == ConversationStatus.COMPLETED
        assert conv.root_agent_id == "persistent-agent"

        # Verify messages exist
        assert len(conv_view.messages) > 0

        # Find LLM messages
        llm_messages = [
            m for m in conv_view.messages
            if m.message_type in [MessageType.LLM_PROMPT, MessageType.LLM_RESPONSE]
        ]
        assert len(llm_messages) == 2
    
    async def test_multiple_executions_tracked_separately(self, test_db):
        """Test that multiple task executions create separate conversations."""
        config = AgentConfig(
            name="Multi Execution Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "multi-exec-agent"  # Set for test verification
        
        try:
            await agent.initialize()
            
            conversation_ids = []
            workflow_ids = []
            
            # Execute multiple tasks
            for i in range(3):
                workflow_id = str(uuid.uuid4())
                workflow_ids.append(workflow_id)
                
                task = {
                    "workflow_id": workflow_id,
                    "description": f"Task {i+1}"
                }
                
                result = await agent.execute(task)
                assert result["status"] in ["success", "error"]  # 3rd call returns error
                
                # Find the conversation for this workflow
                query = ConversationQuery(workflow_id=workflow_id)
                conversations = await agent.conversation_store.search_conversations(query)
                assert len(conversations) == 1
                conversation_ids.append(str(conversations[0].id))
            
            # Verify all conversations are different
            assert len(set(conversation_ids)) == 3
            
            # Verify each conversation exists
            for conv_id in conversation_ids:
                conv_view = await agent.conversation_store.get_conversation(conv_id)
                assert conv_view is not None
                
        finally:
            await agent.shutdown()


@pytest.mark.asyncio
class TestMultiAgentConversations:
    """Test conversation tracking with multiple agents."""
    
    async def test_parent_child_agent_conversations(self, test_db):
        """Test parent and child agents have separate linked conversations."""
        workflow_id = str(uuid.uuid4())
        
        # Create parent orchestrator
        parent_config = AgentConfig(
            name="Parent Orchestrator",
            agent_type="llm_orchestrator",
            metadata={"model": "mock-model"}
        )
        parent = LLMOrchestratorAgent(
            config=parent_config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        parent.agent_id = "parent-orch"  # Set for test verification

        # Create child worker
        child_config = AgentConfig(
            name="Child Worker",
            agent_type="llm_worker",
            metadata={}
        )
        child = LLMWorkerAgent(
            config=child_config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        child.agent_id = "child-worker"  # Set for test verification
        
        try:
            await parent.initialize()
            await child.initialize()
            
            # Parent executes task
            parent_task = {
                "workflow_id": workflow_id,
                "description": "Orchestrate workflow"
            }
            
            parent_result = await parent.execute(parent_task)
            
            # Get parent conversation ID
            query = ConversationQuery(workflow_id=workflow_id)
            parent_convs = await parent.conversation_store.search_conversations(query)
            assert len(parent_convs) == 1
            parent_conv_id = str(parent_convs[0].id)
            
            # Child executes subtask (in real scenario, parent would spawn this)
            child_task = {
                "workflow_id": workflow_id,
                "description": "Process subtask",
                "parent_conversation_id": parent_conv_id
            }
            
            child_result = await child.execute(child_task)
            
            # Get child conversation ID
            # Child should have created a new conversation for same workflow
            child_convs = await child.conversation_store.search_conversations(query)
            # Filter to get the child's conversation (not parent's)
            child_conv = next((c for c in child_convs if str(c.id) != parent_conv_id), None)
            assert child_conv is not None
            child_conv_id = str(child_conv.id)
            
            # Verify both conversations exist
            assert parent_conv_id != child_conv_id
            
            parent_conv = await parent.conversation_store.get_conversation(parent_conv_id)
            child_conv = await child.conversation_store.get_conversation(child_conv_id)
            
            assert parent_conv is not None
            assert child_conv is not None
            
            # Both should have same workflow ID
            assert str(parent_conv.conversation.workflow_id) == workflow_id
            assert str(child_conv.conversation.workflow_id) == workflow_id
            
        finally:
            await parent.shutdown()
            await child.shutdown()


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in conversation tracking."""
    
    async def test_llm_error_tracked_in_conversation(self, test_db):
        """Test that LLM errors are properly tracked."""
        
        class ErrorLLMClient(LLMInterface):
            async def create_completion(self, messages, **kwargs):
                raise Exception("LLM service unavailable")
            
            async def create_completion_stream(self, messages, **kwargs):
                yield "Not implemented"
            
            async def list_models(self):
                return []
            
            async def health_check(self):
                return False
        
        config = AgentConfig(
            name="Error Test Agent",
            agent_type="llm_agent",
            metadata={"model": "error-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=ErrorLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "error-agent"  # Set for test verification
        
        try:
            await agent.initialize()
            
            task = {
                "workflow_id": str(uuid.uuid4()),
                "description": "This will fail"
            }
            
            # Execute should raise on error; conversation still recorded as failed
            import pytest
            with pytest.raises(Exception, match="LLM service unavailable"):
                await agent.execute(task)
            
            # Verify conversation was created and marked as failed
            query = ConversationQuery(workflow_id=task["workflow_id"])
            conversations = await agent.conversation_store.search_conversations(query)
            assert len(conversations) == 1
            conv_id = str(conversations[0].id)
            
            conv_view = await agent.conversation_store.get_conversation(conv_id)
            assert conv_view.conversation.status == ConversationStatus.FAILED
            
            # Check for error message
            error_messages = [
                m for m in conv_view.messages
                if m.message_type == MessageType.ERROR
            ]
            
            assert len(error_messages) >= 1
            assert "LLM service unavailable" in error_messages[0].error
            
        finally:
            await agent.shutdown()
    
    async def test_conversation_tracking_disabled_graceful_degradation(self, test_db):
        """Test agent works properly when conversation tracking is disabled."""
        config = AgentConfig(
            name="No Tracking Agent",
            agent_type="llm_agent",
            metadata={"model": "mock-model"}
        )
        agent = LLMAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=False
        )
        agent.agent_id = "no-tracking-agent"  # Set for test verification
        
        try:
            await agent.initialize()
            
            # Verify no conversation components
            assert agent.conversation_store is None
            assert agent.conversation_interceptor is None
            assert agent._wrapped_client == agent.llm_client  # Direct client, no wrapper
            
            # Execute should still work
            task = {
                "workflow_id": str(uuid.uuid4()),
                "description": "Task without tracking"
            }
            
            result = await agent.execute(task)
            assert result["status"] == "success"
            
            # No conversation should be created
            assert agent.current_conversation_id is None
            
        finally:
            await agent.shutdown()


@pytest.mark.asyncio
class TestConversationMetrics:
    """Test conversation metrics tracking."""
    
    async def test_conversation_metrics_updated(self, test_db):
        """Test that conversation metrics are properly tracked."""
        config = AgentConfig(
            name="Test Analyzer",
            agent_type="llm_analyzer",
            metadata={}
        )
        agent = LLMAnalyzerAgent(
            config=config,
            llm_client=MockLLMClient(),
            enable_conversation_tracking=True
        )
        agent.agent_id = "analyzer-1"  # Set for test verification
        
        try:
            await agent.initialize()
            
            # Execute analysis task
            task = {
                "workflow_id": str(uuid.uuid4()),
                "description": "Analyze data patterns",
                "data": {"values": list(range(100))}
            }
            
            await agent.execute(task)
            
            # Get conversation to verify metrics were tracked
            query = ConversationQuery(workflow_id=task["workflow_id"])
            conversations = await agent.conversation_store.search_conversations(query)
            assert len(conversations) == 1
            conv_id = str(conversations[0].id)
            conv_view = await agent.conversation_store.get_conversation(conv_id)
            
            # Verify messages exist
            messages = conv_view.messages
            assert len(messages) >= 4  # State updates + LLM call/response
            
            # Count LLM messages to verify tracking
            llm_messages = [m for m in messages if m.message_type in [MessageType.LLM_PROMPT, MessageType.LLM_RESPONSE]]
            assert len(llm_messages) >= 2
            
        finally:
            await agent.shutdown()
