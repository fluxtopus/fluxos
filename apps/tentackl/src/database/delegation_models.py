# REVIEW: DelegationPlan duplicates task state in a separate table, which can
# REVIEW: drift from the newer Task models. Also uses mutable JSON defaults.
"""
SQLAlchemy models for delegation/task planning system.

This module defines the database tables for:
- DelegationPlan: Plans created from natural language goals for autonomous execution
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Integer, Float,
    Index
)
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid
import enum

from src.interfaces.database import Base


class DelegationPlanStatus(str, enum.Enum):
    """Status of a delegation plan."""
    PENDING = "pending"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    PAUSED = "paused"
    CHECKPOINT = "checkpoint"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DelegationPlan(Base):
    """
    Delegation plan for autonomous task execution.

    A DelegationPlan represents a natural language goal that is analyzed,
    broken down into steps, and executed by AI agents. It persists across
    orchestrator invocations to avoid context window accumulation.

    The goal_embedding enables semantic search for similar past tasks,
    supporting patterns like "do the HN thing again".
    """
    __tablename__ = "delegation_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    organization_id = Column(String(255), nullable=True, index=True)

    # Plan content
    goal = Column(Text, nullable=False)
    constraints = Column(JSON, nullable=True, default={})
    success_criteria = Column(JSON, nullable=True, default=[])
    steps = Column(JSON, nullable=False, default=[])

    # Execution state
    current_step_index = Column(Integer, nullable=False, default=0)
    status = Column(
        String(50),
        nullable=False,
        default=DelegationPlanStatus.PENDING.value
    )

    # Embedding for semantic search
    goal_embedding = Column(Vector(1536), nullable=True)
    embedding_status = Column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, ready, failed

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index('ix_delegation_plans_user_status', 'user_id', 'status'),
        Index('ix_delegation_plans_org_status', 'organization_id', 'status'),
    )

    def __repr__(self) -> str:
        return f"<DelegationPlan(id={self.id}, goal='{self.goal[:50]}...', status={self.status})>"
