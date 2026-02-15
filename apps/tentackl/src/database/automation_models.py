# REVIEW: Model does not validate cron syntax or timezone at the DB level, and
# REVIEW: uses string IDs for owner/org while tasks use UUIDs. Consider normalizing
# REVIEW: ID types and adding validation constraints where possible.
"""
SQLAlchemy model for the automations table.

An Automation references a completed task as a template. When a schedule fires,
the template task's steps are cloned and executed immediately — no LLM
re-planning required.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Boolean, Index,
    ForeignKey, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
import uuid

from src.interfaces.database import Base


class Automation(Base):
    """
    A recurring automation that clones and executes a template task on a cron schedule.
    """
    __tablename__ = "automations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id = Column(String(255), nullable=False)
    organization_id = Column(String(255), nullable=True)

    # Schedule (at least one of cron / execute_at must be set)
    cron = Column(String(255), nullable=True)
    execute_at = Column(DateTime, nullable=True)
    timezone = Column(String(50), nullable=False, server_default="UTC")
    enabled = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_automation_owner", "owner_id"),
        Index("idx_automation_org", "organization_id"),
        Index("idx_automation_task", "task_id"),
        Index("idx_automation_poll", "enabled", "next_run_at"),
        CheckConstraint(
            "cron IS NOT NULL OR execute_at IS NOT NULL",
            name="ck_automations_schedule_method",
        ),
    )
