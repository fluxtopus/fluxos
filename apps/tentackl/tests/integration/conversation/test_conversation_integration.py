"""Integration tests for conversation storage system."""

import pytest
import uuid
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from src.database.conversation_store import (
    ConversationStore, ConversationTrigger, MessageData, MessageContent,
    MessageMetadata, Cost, ConversationQuery
)
from src.database.conversation_interceptor import ConversationInterceptor
from src.database.models import TriggerType, MessageType, MessageDirection, ConversationStatus
from src.agents.base import Agent, AgentConfig
from src.agents.stateful_agent import StatefulAgent


@pytest.mark.integration
@pytest.mark.conversation
class TestConversationIntegration:
    """Integration tests for conversation storage."""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, test_db):
        """Test a complete conversation flow with multiple messages."""
        store = ConversationStore(test_db)
        interceptor = ConversationInterceptor(store)
        
        # Start a weather monitoring conversation
        workflow_id = str(uuid.uuid4())
        trigger = ConversationTrigger(
            type=TriggerType.WEBHOOK,
            source="weather_service",
            details={
                "endpoint": "/api/webhooks/weather",
                "precipitation_probability": 75,
                "location": "Porto"
            },
            conversation_source="workflow"
        )
        
        conversation = await store.start_conversation(
            workflow_id=workflow_id,
            root_agent_id="weather_monitor",
            trigger=trigger
        )
        
        # Set context for interceptor
        interceptor.set_context(str(conversation.id), "weather_monitor")
        
        # 1. Weather monitor receives webhook
        webhook_message = MessageData(
            agent_id="weather_monitor",
            message_type=MessageType.TOOL_RESPONSE,
            direction=MessageDirection.INBOUND,
            content=MessageContent(
                role="tool",
                text="Weather webhook received",
                data={
                    "precipitation_probability": 75,
                    "time_window": "14:00-17:00",
                    "location": "Porto"
                }
            ),
            metadata=MessageMetadata(latency_ms=50)
        )
        await store.add_message(str(conversation.id), webhook_message)
        
        # 2. Weather monitor analyzes data
        await interceptor.intercept_llm_call(
            agent_id="weather_monitor",
            prompt="Analyze weather data: 75% rain probability from 14:00-17:00 in Porto",
            model="gpt-4o-mini",
            temperature=0.3
        )
        
        await interceptor.intercept_llm_response(
            agent_id="weather_monitor",
            response={
                "content": "High rain probability detected. Action required: notify affected bookings and offer rescheduling.",
                "model": "gpt-4o-mini",
                "usage": {"prompt": 30, "completion": 25, "total": 55},
                "cost": 0.0002
            },
            latency_ms=800
        )
        
        # 3. Weather monitor spawns field scheduler
        spawn_message = MessageData(
            agent_id="weather_monitor",
            message_type=MessageType.INTER_AGENT,
            direction=MessageDirection.OUTBOUND,
            content=MessageContent(
                role="agent",
                text="Spawning field scheduler",
                data={
                    "target_agent": "field_scheduler",
                    "task": "find_affected_bookings",
                    "parameters": {
                        "time_window": "14:00-17:00",
                        "location": "Porto"
                    }
                }
            ),
            metadata=MessageMetadata()
        )
        await store.add_message(str(conversation.id), spawn_message)
        
        # 4. Field scheduler queries bookings
        interceptor.set_context(str(conversation.id), "field_scheduler")
        
        await interceptor.intercept_tool_call(
            agent_id="field_scheduler",
            tool_name="booking_api",
            parameters={
                "action": "query",
                "time_start": "14:00",
                "time_end": "17:00",
                "location": "Porto"
            }
        )
        
        await interceptor.intercept_tool_response(
            agent_id="field_scheduler",
            tool_name="booking_api",
            response={
                "bookings": [
                    {"id": "B001", "time": "14:00", "customer_id": "C001"},
                    {"id": "B002", "time": "15:30", "customer_id": "C002"},
                    {"id": "B003", "time": "16:00", "customer_id": "C003"}
                ]
            },
            latency_ms=200
        )
        
        # 5. Communication coordinator sends notifications
        interceptor.set_context(str(conversation.id), "communication_coordinator")
        
        for booking in ["B001", "B002", "B003"]:
            await interceptor.intercept_llm_call(
                agent_id="communication_coordinator",
                prompt=f"Generate weather notification for booking {booking}",
                model="gpt-3.5-turbo",
                temperature=0.7
            )
            
            await interceptor.intercept_llm_response(
                agent_id="communication_coordinator",
                response={
                    "content": f"Dear customer, due to expected rain (75% probability) during your booking at...",
                    "model": "gpt-3.5-turbo",
                    "usage": {"prompt": 40, "completion": 60, "total": 100},
                    "cost": 0.00015
                },
                latency_ms=600
            )
        
        # 6. End conversation
        await store.end_conversation(str(conversation.id), ConversationStatus.COMPLETED)
        
        # Verify conversation details
        conv_view = await store.get_conversation(str(conversation.id), include_messages=True)
        
        assert conv_view.conversation.status == ConversationStatus.COMPLETED
        assert len(conv_view.messages) >= 10  # All the messages we added
        
        # Verify costs
        costs = await store.get_conversation_costs(str(conversation.id))
        
        assert costs.total_cost > 0
        assert "weather_monitor" in costs.cost_by_agent
        assert "communication_coordinator" in costs.cost_by_agent
        assert costs.cost_by_model.get("gpt-4o-mini", 0) > 0
        assert costs.cost_by_model.get("gpt-3.5-turbo", 0) > 0
        assert costs.token_usage["total_tokens"] > 0
    
    @pytest.mark.asyncio
    async def test_conversation_with_errors(self, test_db):
        """Test conversation handling with errors."""
        store = ConversationStore(test_db)
        interceptor = ConversationInterceptor(store)
        
        # Start conversation
        trigger = ConversationTrigger(
            type=TriggerType.API_CALL,
            source="test_api",
            details={"endpoint": "/test"},
            conversation_source="workflow"
        )
        
        conversation = await store.start_conversation(
            workflow_id=str(uuid.uuid4()),
            root_agent_id="error_test_agent",
            trigger=trigger
        )
        
        interceptor.set_context(str(conversation.id), "error_test_agent")
        
        # Add successful message
        await interceptor.intercept_llm_call(
            agent_id="error_test_agent",
            prompt="Process data",
            model="gpt-4"
        )
        
        # Add error
        error = ValueError("Invalid data format")
        await interceptor.intercept_error(
            agent_id="error_test_agent",
            error=error,
            context={"input": "malformed_data"}
        )
        
        # End with failed status
        await store.end_conversation(str(conversation.id), ConversationStatus.FAILED)
        
        # Verify
        conv_view = await store.get_conversation(str(conversation.id), include_messages=True)
        
        assert conv_view.conversation.status == ConversationStatus.FAILED
        
        # Find error message
        error_messages = [
            msg for msg in conv_view.messages 
            if msg.message_type == MessageType.ERROR
        ]
        
        assert len(error_messages) == 1
        assert "ValueError" in error_messages[0].content_text
        assert "Invalid data format" in error_messages[0].content_text
    
    @pytest.mark.asyncio
    async def test_parallel_conversations(self, test_db):
        """Test handling multiple parallel conversations."""
        store = ConversationStore(test_db)
        
        workflow_id = str(uuid.uuid4())
        conversations = []
        
        # Start multiple conversations in parallel
        async def start_conv(index):
            trigger = ConversationTrigger(
                type=TriggerType.API_CALL,
                source=f"source_{index}",
                details={"index": index},
                conversation_source="workflow"
            )
            
            conv = await store.start_conversation(
                workflow_id=workflow_id,
                root_agent_id=f"agent_{index}",
                trigger=trigger
            )
            
            # Add some messages
            for j in range(3):
                message = MessageData(
                    agent_id=f"agent_{index}",
                    message_type=MessageType.LLM_RESPONSE,
                    direction=MessageDirection.INBOUND,
                    content=MessageContent(
                        role="assistant",
                        text=f"Response {j} from agent {index}"
                    ),
                    metadata=MessageMetadata(
                        tokens={"prompt": 10, "completion": 20, "total": 30}
                    )
                )
                await store.add_message(str(conv.id), message)
            
            return conv
        
        # Create 5 parallel conversations
        conversations = await asyncio.gather(*[
            start_conv(i) for i in range(5)
        ])
        
        # Verify all conversations exist
        query = ConversationQuery(workflow_id=workflow_id)
        results = await store.search_conversations(query)
        
        assert len(results) == 5
        
        # Verify each conversation has messages
        for conv in conversations:
            conv_view = await store.get_conversation(str(conv.id), include_messages=True)
            assert len(conv_view.messages) == 3
    
    @pytest.mark.asyncio
    async def test_conversation_hierarchy(self, test_db):
        """Test parent-child conversation relationships."""
        store = ConversationStore(test_db)
        
        workflow_id = str(uuid.uuid4())
        
        # Create parent conversation
        parent_trigger = ConversationTrigger(
            type=TriggerType.API_CALL,
            source="orchestrator",
            details={"task": "complex_workflow"},
            conversation_source="workflow"
        )
        
        parent_conv = await store.start_conversation(
            workflow_id=workflow_id,
            root_agent_id="orchestrator",
            trigger=parent_trigger
        )
        
        # Create child conversations
        child_convs = []
        for i in range(3):
            child_trigger = ConversationTrigger(
                type=TriggerType.INTER_AGENT,
                source="orchestrator",
                details={"subtask": f"task_{i}"},
                conversation_source="workflow"
            )
            
            child = await store.start_conversation(
                workflow_id=workflow_id,
                root_agent_id=f"worker_{i}",
                trigger=child_trigger,
                parent_conversation_id=str(parent_conv.id)
            )
            child_convs.append(child)
        
        # Add messages to child conversations
        for i, child in enumerate(child_convs):
            message = MessageData(
                agent_id=f"worker_{i}",
                message_type=MessageType.STATE_UPDATE,
                direction=MessageDirection.INTERNAL,
                content=MessageContent(
                    role="system",
                    text=f"Task {i} completed",
                    data={"status": "completed", "result": f"result_{i}"}
                ),
                metadata=MessageMetadata()
            )
            await store.add_message(str(child.id), message)
            
            # End child conversation
            await store.end_conversation(str(child.id), ConversationStatus.COMPLETED)
        
        # End parent conversation
        await store.end_conversation(str(parent_conv.id), ConversationStatus.COMPLETED)
        
        # Verify hierarchy
        parent_view = await store.get_conversation(str(parent_conv.id))
        assert parent_view.conversation.status == ConversationStatus.COMPLETED
        
        # Verify children
        for child in child_convs:
            child_view = await store.get_conversation(str(child.id))
            assert child_view.conversation.parent_conversation_id == parent_conv.id
            assert child_view.conversation.status == ConversationStatus.COMPLETED


@pytest.mark.integration
@pytest.mark.conversation
class TestConversationAwareAgent:
    """Test integration with conversation-aware agents."""
    
    @pytest.mark.asyncio
    async def test_agent_with_conversation_tracking(self, test_db):
        """Test an agent that tracks its conversations."""
        from src.database.conversation_interceptor import current_conversation_id, current_agent_id
        
        store = ConversationStore(test_db)
        interceptor = ConversationInterceptor(store)
        
        # Create a mock conversation-aware agent
        class ConversationAwareTestAgent:
            def __init__(self, agent_id: str):
                self.agent_id = agent_id
                self.store = store
                self.interceptor = interceptor
            
            async def execute(self, task: dict):
                # Start conversation
                trigger = ConversationTrigger(
                    type=TriggerType.API_CALL,
                    source="test",
                    details=task,
                    conversation_source="workflow"
                )
                
                conversation = await self.store.start_conversation(
                    workflow_id=task.get("workflow_id", str(uuid.uuid4())),
                    root_agent_id=self.agent_id,
                    trigger=trigger
                )
                
                # Set context
                self.interceptor.set_context(str(conversation.id), self.agent_id)
                
                try:
                    # Simulate LLM call
                    await self.interceptor.intercept_llm_call(
                        agent_id=self.agent_id,
                        prompt=f"Execute task: {task}",
                        model="gpt-4"
                    )
                    
                    # Simulate response
                    result = {"status": "completed", "data": "test_result"}
                    
                    await self.interceptor.intercept_llm_response(
                        agent_id=self.agent_id,
                        response={
                            "content": str(result),
                            "model": "gpt-4",
                            "usage": {"prompt": 20, "completion": 30, "total": 50}
                        },
                        latency_ms=500
                    )
                    
                    # End conversation
                    await self.store.end_conversation(
                        str(conversation.id),
                        ConversationStatus.COMPLETED
                    )
                    
                    return result
                    
                except Exception as e:
                    await self.interceptor.intercept_error(
                        agent_id=self.agent_id,
                        error=e,
                        context={"task": task}
                    )
                    
                    await self.store.end_conversation(
                        str(conversation.id),
                        ConversationStatus.FAILED
                    )
                    raise
        
        # Test the agent
        agent = ConversationAwareTestAgent("test_agent_001")
        task = {"action": "test", "data": "sample"}
        
        result = await agent.execute(task)
        
        assert result["status"] == "completed"
        
        # Verify conversation was recorded
        query = ConversationQuery()
        conversations = await store.search_conversations(query)
        
        assert len(conversations) > 0
        
        # Get the last conversation
        conv = conversations[0]
        conv_view = await store.get_conversation(str(conv.id), include_messages=True)
        
        assert conv_view.conversation.root_agent_id == "test_agent_001"
        assert conv_view.conversation.status == ConversationStatus.COMPLETED
        assert len(conv_view.messages) >= 2  # At least prompt and response