# REVIEW: Conversation and Message models store large JSON/text blobs with no
# REVIEW: size constraints or redaction controls, and many nullable fields without
# REVIEW: validation. Consider constraints and data-retention policies.
"""SQLAlchemy models for conversation storage."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Float, Integer, Boolean,
    ForeignKey, Index, Enum as SQLEnum, DECIMAL, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from src.interfaces.database import Base


class ConversationStatus(str, enum.Enum):
    """Conversation status enum."""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(str, enum.Enum):
    """Conversation trigger type enum."""
    EVENT = "event"
    API_CALL = "api_call"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK = "webhook"
    INTER_AGENT = "inter_agent"


class MessageType(str, enum.Enum):
    """Message type enum."""
    LLM_PROMPT = "llm_prompt"
    LLM_RESPONSE = "llm_response"
    INTER_AGENT = "inter_agent"
    TOOL_CALL = "tool_call"
    TOOL_RESPONSE = "tool_response"
    STATE_UPDATE = "state_update"
    ERROR = "error"


class MessageDirection(str, enum.Enum):
    """Message direction enum."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class ReadStatus(str, enum.Enum):
    """Inbox read status enum."""
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class InboxPriority(str, enum.Enum):
    """Inbox priority enum."""
    NORMAL = "normal"
    ATTENTION = "attention"


class Conversation(Base):
    """Conversation model for storing agent conversations."""
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    parent_conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    root_agent_id = Column(String(255), nullable=False)
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(SQLEnum(ConversationStatus), nullable=False, default=ConversationStatus.ACTIVE)
    trigger_type = Column(SQLEnum(TriggerType), nullable=False)
    trigger_source = Column(Text, nullable=True)
    trigger_details = Column(JSON, nullable=True)
    extra_metadata = Column(JSON, nullable=True)
    tags = Column(ARRAY(Text), nullable=True)
    source = Column(String(50), nullable=False, default="workflow", server_default="workflow")
    read_status = Column(SQLEnum(ReadStatus, values_callable=lambda x: [e.value for e in x]), nullable=True, default=None, index=True)
    priority = Column(SQLEnum(InboxPriority, values_callable=lambda x: [e.value for e in x]), nullable=True, default=None)
    user_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    child_conversations = relationship("Conversation", backref="parent_conversation", remote_side=[id])
    
    # Indexes
    __table_args__ = (
        Index("idx_workflow", "workflow_id"),
        Index("idx_time_range", "start_time", "end_time"),
        Index("idx_status", "status"),
        Index("idx_tags", "tags", postgresql_using="gin"),
        Index("idx_conversation_source", "source"),
        Index("idx_conversation_inbox", "user_id", "read_status"),
    )


class Message(Base):
    """Message model for storing individual messages in conversations."""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    agent_id = Column(String(255), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    message_type = Column(SQLEnum(MessageType), nullable=False)
    direction = Column(SQLEnum(MessageDirection), nullable=False)
    role = Column(String(20), nullable=True)  # system, user, assistant, tool
    content_text = Column(Text, nullable=True)
    content_data = Column(JSON, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    masked_fields = Column(ARRAY(Text), nullable=True)
    model = Column(String(100), nullable=True)
    temperature = Column(Float, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    cost_amount = Column(DECIMAL(10, 6), nullable=True)
    cost_currency = Column(String(3), nullable=True, default="USD")
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    extra_metadata = Column(JSON, nullable=True)
    parent_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    child_messages = relationship("Message", backref="parent_message", remote_side=[id])
    
    # Indexes
    __table_args__ = (
        Index("idx_conversation_timestamp", "conversation_id", "timestamp"),
        Index("idx_agent_timestamp", "agent_id", "timestamp"),
        Index("idx_message_type", "message_type"),
        Index("idx_timestamp", "timestamp"),
    )


class ConversationMetrics(Base):
    """Aggregated metrics for conversations."""
    __tablename__ = "conversation_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), unique=True, nullable=False)
    total_messages = Column(Integer, default=0)
    total_llm_calls = Column(Integer, default=0)
    total_tool_calls = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(DECIMAL(10, 6), default=0)
    average_latency_ms = Column(Float, default=0)
    max_latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index("idx_metrics_conversation", "conversation_id"),
    )
