"""Unit tests for ConversationStore."""

import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from src.database.conversation_store import (
    ConversationStore, ConversationTrigger, MessageData, MessageContent,
    MessageMetadata, Cost, ConversationQuery, ConversationCosts, DataMasker
)
from src.database.models import (
    ConversationStatus, TriggerType, MessageType, MessageDirection,
    Conversation, Message
)


@pytest.mark.conversation
class TestConversationStore:
    """Test ConversationStore functionality."""
    
    @pytest.mark.asyncio
    async def test_start_conversation(self, test_db, sample_conversation_data):
        """Test starting a new conversation."""
        store = ConversationStore(test_db)
        
        trigger = ConversationTrigger(
            type=TriggerType.WEBHOOK,
            source=sample_conversation_data["trigger"]["source"],
            details=sample_conversation_data["trigger"]["details"],
            conversation_source="workflow"
        )
        
        conversation = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id=sample_conversation_data["root_agent_id"],
            trigger=trigger
        )
        
        assert conversation is not None
        assert conversation.workflow_id == uuid.UUID(sample_conversation_data["workflow_id"])
        assert conversation.root_agent_id == sample_conversation_data["root_agent_id"]
        assert conversation.trigger_type == TriggerType.WEBHOOK
        assert conversation.status == ConversationStatus.ACTIVE
        assert conversation.start_time is not None
        assert conversation.end_time is None
    
    @pytest.mark.asyncio
    async def test_start_child_conversation(self, test_db, sample_conversation_data):
        """Test starting a child conversation."""
        store = ConversationStore(test_db)
        
        # Create parent conversation
        trigger = ConversationTrigger(
            type=TriggerType.API_CALL,
            source="parent_agent",
            details={"task": "parent_task"},
            conversation_source="workflow"
        )
        
        parent = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id="parent_agent",
            trigger=trigger
        )
        
        # Create child conversation
        child_trigger = ConversationTrigger(
            type=TriggerType.INTER_AGENT,
            source="parent_agent",
            details={"task": "child_task"},
            conversation_source="workflow"
        )
        
        child = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id="child_agent",
            trigger=child_trigger,
            parent_conversation_id=str(parent.id)
        )
        
        assert child.parent_conversation_id == parent.id
    
    @pytest.mark.asyncio
    async def test_add_message(self, test_db, sample_conversation_data, sample_message_data):
        """Test adding messages to a conversation."""
        store = ConversationStore(test_db)
        
        # Start conversation
        trigger = ConversationTrigger(
            type=TriggerType.API_CALL,
            source="test",
            details={},
            conversation_source="workflow"
        )
        
        conversation = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id=sample_conversation_data["root_agent_id"],
            trigger=trigger
        )
        
        # Create message data
        message_data = MessageData(
            agent_id=sample_message_data["agent_id"],
            message_type=MessageType.LLM_PROMPT,
            direction=MessageDirection.OUTBOUND,
            content=MessageContent(
                role=sample_message_data["content"]["role"],
                text=sample_message_data["content"]["text"],
                data=sample_message_data["content"]["data"]
            ),
            metadata=MessageMetadata(
                model=sample_message_data["metadata"]["model"],
                temperature=sample_message_data["metadata"]["temperature"],
                tokens=sample_message_data["metadata"]["tokens"],
                latency_ms=sample_message_data["metadata"]["latency_ms"]
            ),
            cost=Cost(
                amount=sample_message_data["cost"]["amount"],
                currency=sample_message_data["cost"]["currency"]
            )
        )
        
        # Add message
        success = await store.add_message(str(conversation.id), message_data)
        
        assert success is True
        
        # Verify message was stored
        conv_view = await store.get_conversation(str(conversation.id), include_messages=True)
        assert conv_view is not None
        assert len(conv_view.messages) == 1
        
        message = conv_view.messages[0]
        assert message.agent_id == sample_message_data["agent_id"]
        assert message.message_type == MessageType.LLM_PROMPT
        assert message.content_text == sample_message_data["content"]["text"]
        assert message.model == sample_message_data["metadata"]["model"]
        assert message.total_tokens == sample_message_data["metadata"]["tokens"]["total"]
        assert float(message.cost_amount) == sample_message_data["cost"]["amount"]
    
    @pytest.mark.asyncio
    async def test_message_preserves_content(self, test_db, sample_conversation_data):
        """Test that message content is preserved as-is (masking disabled)."""
        store = ConversationStore(test_db)

        # Start conversation
        trigger = ConversationTrigger(type=TriggerType.MANUAL, source="test", details={}, conversation_source="workflow")
        conversation = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id="test_agent",
            trigger=trigger
        )

        # Create message with data that was previously masked
        text = "My API key is sk-1234567890abcdef and email is test@example.com"

        message_data = MessageData(
            agent_id="test_agent",
            message_type=MessageType.LLM_PROMPT,
            direction=MessageDirection.OUTBOUND,
            content=MessageContent(
                role="user",
                text=text
            ),
            metadata=MessageMetadata()
        )

        # Add message
        await store.add_message(str(conversation.id), message_data)

        # Verify content is preserved without masking
        conv_view = await store.get_conversation(str(conversation.id), include_messages=True)
        message = conv_view.messages[0]

        assert "sk-1234567890abcdef" in message.content_text
        assert "test@example.com" in message.content_text
        assert "[API_KEY_MASKED]" not in message.content_text
        assert "[EMAIL_MASKED]" not in message.content_text
    
    @pytest.mark.asyncio
    async def test_end_conversation(self, test_db, sample_conversation_data):
        """Test ending a conversation."""
        store = ConversationStore(test_db)
        
        # Start conversation
        trigger = ConversationTrigger(type=TriggerType.API_CALL, source="test", details={}, conversation_source="workflow")
        conversation = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id="test_agent",
            trigger=trigger
        )
        
        # End conversation
        success = await store.end_conversation(
            str(conversation.id),
            ConversationStatus.COMPLETED
        )
        
        assert success is True
        
        # Verify status
        conv_view = await store.get_conversation(str(conversation.id))
        assert conv_view.conversation.status == ConversationStatus.COMPLETED
        assert conv_view.conversation.end_time is not None
    
    @pytest.mark.asyncio
    async def test_search_conversations(self, test_db):
        """Test searching conversations."""
        store = ConversationStore(test_db)
        
        # Create multiple conversations
        workflow_id = str(uuid.uuid4())
        
        # Active conversation
        trigger1 = ConversationTrigger(type=TriggerType.WEBHOOK, source="weather", details={}, conversation_source="workflow")
        conv1 = await store.start_conversation(
            workflow_id=workflow_id,
            root_agent_id="agent1",
            trigger=trigger1
        )
        
        # Completed conversation
        trigger2 = ConversationTrigger(type=TriggerType.API_CALL, source="api", details={}, conversation_source="workflow")
        conv2 = await store.start_conversation(
            workflow_id=workflow_id,
            root_agent_id="agent2",
            trigger=trigger2
        )
        await store.end_conversation(str(conv2.id), ConversationStatus.COMPLETED)
        
        # Different workflow
        trigger3 = ConversationTrigger(type=TriggerType.MANUAL, source="user", details={}, conversation_source="workflow")
        conv3 = await store.start_conversation(
            workflow_id=str(uuid.uuid4()),
            root_agent_id="agent3",
            trigger=trigger3
        )
        
        # Search by workflow_id
        query = ConversationQuery(workflow_id=workflow_id)
        results = await store.search_conversations(query)
        
        assert len(results) == 2
        assert all(conv.workflow_id == uuid.UUID(workflow_id) for conv in results)
        
        # Search by status — filter by our workflow too for isolation
        query = ConversationQuery(workflow_id=workflow_id, status=ConversationStatus.COMPLETED)
        results = await store.search_conversations(query)

        assert len(results) == 1
        assert results[0].id == conv2.id
        
        # Search by time range — scope to our workflows for isolation
        all_workflow_ids = {workflow_id, str(conv3.workflow_id)}
        query = ConversationQuery(
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow() + timedelta(hours=1)
        )
        results = await store.search_conversations(query)
        # Filter to our test conversations only
        results = [r for r in results if str(r.workflow_id) in all_workflow_ids]

        assert len(results) == 3  # All our test conversations
    
    @pytest.mark.asyncio
    async def test_conversation_costs(self, test_db, sample_conversation_data):
        """Test calculating conversation costs."""
        store = ConversationStore(test_db)
        
        # Start conversation
        trigger = ConversationTrigger(type=TriggerType.API_CALL, source="test", details={}, conversation_source="workflow")
        conversation = await store.start_conversation(
            workflow_id=sample_conversation_data["workflow_id"],
            root_agent_id="orchestrator",
            trigger=trigger
        )
        
        # Add messages from different agents with costs
        agents = ["agent1", "agent2", "agent1"]
        models = ["gpt-4", "gpt-3.5-turbo", "gpt-4"]
        costs = [0.05, 0.002, 0.03]
        tokens = [1000, 500, 800]
        
        for i, (agent, model, cost, token_count) in enumerate(zip(agents, models, costs, tokens)):
            message_data = MessageData(
                agent_id=agent,
                message_type=MessageType.LLM_RESPONSE,
                direction=MessageDirection.INBOUND,
                content=MessageContent(role="assistant", text=f"Response {i}"),
                metadata=MessageMetadata(
                    model=model,
                    tokens={"prompt": token_count // 2, "completion": token_count // 2, "total": token_count}
                ),
                cost=Cost(amount=cost)
            )
            await store.add_message(str(conversation.id), message_data)
        
        # Get costs
        costs = await store.get_conversation_costs(str(conversation.id))
        
        assert costs.total_cost == 0.082  # 0.05 + 0.002 + 0.03
        assert costs.cost_by_agent["agent1"] == 0.08  # 0.05 + 0.03
        assert costs.cost_by_agent["agent2"] == 0.002
        assert costs.cost_by_model["gpt-4"] == 0.08
        assert costs.cost_by_model["gpt-3.5-turbo"] == 0.002
        assert costs.token_usage["total_tokens"] == 2300  # 1000 + 500 + 800
        assert costs.token_usage["prompt_tokens"] == 1150
        assert costs.token_usage["completion_tokens"] == 1150


@pytest.mark.masking
class TestDataMasker:
    """Test DataMasker functionality."""
    
    def test_mask_api_key(self):
        """Test masking API keys."""
        masker = DataMasker()
        text = "My API key is sk-1234567890abcdef"
        masked, fields = masker.mask(text)
        
        assert "[API_KEY_MASKED]" in masked
        assert "sk-1234567890abcdef" not in masked
        assert "api_key" in fields
    
    def test_mask_email(self):
        """Test masking emails."""
        masker = DataMasker()
        text = "Contact me at john.doe@example.com for details"
        masked, fields = masker.mask(text)
        
        assert "[EMAIL_MASKED]" in masked
        assert "john.doe@example.com" not in masked
        assert "email" in fields
    
    def test_mask_phone(self):
        """Test masking phone numbers."""
        masker = DataMasker()
        text = "Call me at +1234567890"
        masked, fields = masker.mask(text)
        
        assert "[PHONE_MASKED]" in masked
        assert "+1234567890" not in masked
        assert "phone" in fields
    
    def test_mask_credit_card(self):
        """Test masking credit card numbers."""
        masker = DataMasker()
        text = "Payment with 1234-5678-9012-3456"
        masked, fields = masker.mask(text)
        
        assert "[CREDIT_CARD_MASKED]" in masked
        assert "1234-5678-9012-3456" not in masked
        assert "credit_card" in fields
    
    def test_mask_multiple_sensitive_data(self):
        """Test masking multiple types of sensitive data."""
        masker = DataMasker()
        text = "API: sk-test123, email: test@example.com, phone: +1234567890"
        masked, fields = masker.mask(text)
        
        assert "[API_KEY_MASKED]" in masked
        assert "[EMAIL_MASKED]" in masked
        assert "[PHONE_MASKED]" in masked
        assert "sk-test123" not in masked
        assert "test@example.com" not in masked
        assert "+1234567890" not in masked
        assert set(fields) == {"api_key", "email", "phone"}
    
    def test_no_sensitive_data(self):
        """Test text without sensitive data."""
        masker = DataMasker()
        text = "This is a normal message without any sensitive information"
        masked, fields = masker.mask(text)
        
        assert masked == text
        assert len(fields) == 0