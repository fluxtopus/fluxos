# REVIEW: Task and preference models store many JSON fields with mutable defaults
# REVIEW: and string status fields (not enums), which can drift from runtime
# REVIEW: models. Consider stricter enums and safer defaults.
"""
SQLAlchemy models for task execution system.

This module defines the database tables for:
- Task: Persistent task documents (natural language goals + execution plans)
- UserPreference: Learned approval preferences
- CheckpointApproval: Approval history for checkpoints
- TaskEvent: Audit trail of task events
- ObserverReport: Reports from the observer agent
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Integer, Boolean, Float,
    ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from src.interfaces.database import Base


class TaskStatus(str, enum.Enum):
    """Status of a task."""
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    PAUSED = "paused"
    CHECKPOINT = "checkpoint"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckpointApprovalStatus(str, enum.Enum):
    """Status of a checkpoint approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


class Task(Base):
    """
    Persistent task document.

    This is the source of truth for autonomous task execution.
    The task persists across orchestrator invocations, avoiding
    context window accumulation.

    A task represents a natural language goal that is broken down
    into executable steps and executed by AI agents.
    """
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    organization_id = Column(String(255), nullable=True, index=True)

    # Task content
    goal = Column(Text, nullable=False)
    constraints = Column(JSON, nullable=True, default={})
    success_criteria = Column(JSON, nullable=True, default=[])
    steps = Column(JSON, nullable=False, default=[])  # List[TaskStep] as JSON
    accumulated_findings = Column(JSON, nullable=True, default=[])

    # Execution state
    current_step_index = Column(Integer, nullable=False, default=0)
    status = Column(
        String(50),
        nullable=False,
        default="planning"
    )

    # Linking
    tree_id = Column(String(255), nullable=True)  # Links to execution tree
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False, default=1)

    # Metadata
    extra_metadata = Column('metadata', JSON, nullable=True, default={})
    source = Column(String(50), nullable=True, default="api")  # api, ui, schedule

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    parent_task = relationship("Task", remote_side=[id], foreign_keys=[parent_task_id])
    conversation = relationship("Conversation", foreign_keys=[conversation_id])
    checkpoint_approvals = relationship("CheckpointApproval", back_populates="task", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_task_user", "user_id"),
        Index("idx_task_org", "organization_id"),
        Index("idx_task_status", "status"),
        Index("idx_task_tree", "tree_id"),
        Index("idx_task_created", "created_at"),
        Index("idx_task_parent", "parent_task_id"),
        Index("idx_task_user_status", "user_id", "status"),
        Index("idx_task_conversation", "conversation_id"),
    )


class PreferenceScope(str, enum.Enum):
    """Scope of preference application."""
    GLOBAL = "global"
    AGENT_TYPE = "agent_type"
    TASK_TYPE = "task_type"
    TASK = "task"


class PreferenceType(str, enum.Enum):
    """Type of preference."""
    AUTO_APPROVAL = "auto_approval"
    INSTRUCTION = "instruction"


class UserPreference(Base):
    """
    User preference for auto-approval and prompt injection.

    Preferences can be:
    1. Auto-approval: Learned from decisions, used to auto-approve similar checkpoints
    2. Instruction: Human-readable guidance injected into agent prompts

    Preferences are scoped to different levels:
    - GLOBAL: Applies to all agents and tasks
    - AGENT_TYPE: Applies to specific agent type (e.g., "notify", "compose")
    - TASK_TYPE: Applies to specific task type (e.g., "email_digest", "meal_planning")
    - TASK: Applies to specific task ID only
    """
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    organization_id = Column(String(255), nullable=True, index=True)

    # Preference identification
    preference_key = Column(String(255), nullable=False)  # e.g., "email_digest_send"

    # Scoping (NEW)
    scope = Column(String(50), nullable=False, default="global")
    scope_value = Column(String(255), nullable=True)  # Value for scope (e.g., "notify")

    # Preference type and content (NEW)
    preference_type = Column(String(50), nullable=False, default="auto_approval")
    instruction = Column(Text, nullable=True)  # Human-readable for prompt injection

    # Pattern matching (for auto_approval type)
    pattern = Column(JSON, nullable=False, default={})  # Generalizable pattern

    # Decision (for auto_approval type)
    decision = Column(String(50), nullable=True)  # "approved" or "rejected"
    confidence = Column(Float, nullable=False, default=1.0)

    # Usage tracking
    usage_count = Column(Integer, nullable=False, default=1)
    last_used = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Source tracking (NEW)
    source = Column(String(50), nullable=False, default="learned")  # learned, manual, imported

    # Metadata
    extra_metadata = Column('metadata', JSON, nullable=True, default={})

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_pref_user", "user_id"),
        Index("idx_pref_user_key", "user_id", "preference_key"),
        Index("idx_pref_org", "organization_id"),
        Index("idx_pref_confidence", "confidence"),
        Index("idx_pref_last_used", "last_used"),
        Index("idx_pref_decision", "decision"),
        Index("idx_pref_scope", "scope"),
        Index("idx_pref_user_scope", "user_id", "scope"),
        Index("idx_pref_user_scope_value", "user_id", "scope", "scope_value"),
        Index("idx_pref_type", "preference_type"),
    )


class CheckpointType(str, enum.Enum):
    """Type of interactive checkpoint."""
    APPROVAL = "approval"     # Binary approve/reject (existing behavior)
    INPUT = "input"           # Collect structured user input
    MODIFY = "modify"         # Allow modification of step inputs
    SELECT = "select"         # Choose from alternatives
    QA = "qa"                 # Q&A dialog (ask specific questions)


class CheckpointApproval(Base):
    """
    Record of checkpoint approval requests and decisions.

    Supports interactive checkpoints beyond simple approve/reject:
    - APPROVAL: Binary approve/reject
    - INPUT: Collect structured user input via input_schema
    - MODIFY: Allow user to modify step inputs
    - SELECT: Choose from predefined alternatives
    - QA: Answer specific questions

    Used for audit trail, preference learning, and interactive workflows.
    """
    __tablename__ = "checkpoint_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False, index=True)

    # Checkpoint details
    checkpoint_name = Column(String(255), nullable=False)
    checkpoint_description = Column(Text, nullable=True)
    preference_key = Column(String(255), nullable=True)  # For learning

    # Checkpoint type (NEW)
    checkpoint_type = Column(String(50), nullable=False, default="approval")

    # Preview data
    preview_data = Column(JSON, nullable=True)  # Data shown to user for approval

    # Interactive checkpoint configuration (NEW)
    input_schema = Column(JSON, nullable=True)  # JSON Schema for INPUT type
    questions = Column(JSON, nullable=True)  # Questions for QA type
    alternatives = Column(JSON, nullable=True)  # Options for SELECT type
    modifiable_fields = Column(JSON, nullable=True)  # Fields user can modify for MODIFY type
    context_data = Column(JSON, nullable=True)  # Context to show user (e.g., last week's meals)

    # Status and decision
    status = Column(
        String(50),
        nullable=False,
        default="pending"
    )
    auto_approved = Column(Boolean, nullable=False, default=False)
    preference_id = Column(UUID(as_uuid=True), ForeignKey("user_preferences.id", ondelete="SET NULL"), nullable=True)

    # User feedback
    feedback = Column(Text, nullable=True)

    # Interactive checkpoint responses (NEW)
    response_inputs = Column(JSON, nullable=True)  # User inputs for INPUT type
    response_modified_inputs = Column(JSON, nullable=True)  # Modified step inputs for MODIFY type
    response_selected_alternative = Column(Integer, nullable=True)  # Selected option index for SELECT type
    response_answers = Column(JSON, nullable=True)  # Answers for QA type

    # Timestamps
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)  # When auto-timeout would occur

    # Relationships
    task = relationship("Task", back_populates="checkpoint_approvals")
    preference = relationship("UserPreference", foreign_keys=[preference_id])

    # Indexes
    __table_args__ = (
        Index("idx_checkpoint_task", "task_id"),
        Index("idx_checkpoint_user", "user_id"),
        Index("idx_checkpoint_status", "status"),
        Index("idx_checkpoint_requested", "requested_at"),
        Index("idx_checkpoint_pending", "status", "timeout_at"),
        Index("idx_checkpoint_task_step", "task_id", "step_id"),
        Index("idx_checkpoint_type", "checkpoint_type"),
    )


class TaskEvent(Base):
    """
    Audit trail of task events.

    Records all significant events in a task's lifecycle.
    """
    __tablename__ = "task_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Event details
    event_type = Column(String(100), nullable=False)  # task.created, step.started, checkpoint.approved, etc.
    event_data = Column(JSON, nullable=True)
    extra_metadata = Column('metadata', JSON, nullable=True)

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_task_event_task", "task_id"),
        Index("idx_task_event_type", "event_type"),
        Index("idx_task_event_created", "created_at"),
        Index("idx_task_event_task_created", "task_id", "created_at"),
    )


class ObserverReport(Base):
    """
    Reports from the task observer agent.

    The observer monitors task execution and proposes changes
    but does not act directly.
    """
    __tablename__ = "observer_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Report content
    progress_pct = Column(Float, nullable=False, default=0.0)
    anomalies = Column(JSON, nullable=True, default=[])
    proposals = Column(JSON, nullable=True, default=[])
    recommendation = Column(String(50), nullable=False, default="continue")  # continue, pause, escalate

    # Execution state snapshot
    execution_state = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_observer_task", "task_id"),
        Index("idx_observer_recommendation", "recommendation"),
        Index("idx_observer_created", "created_at"),
    )

