# REVIEW:
# - Query response uses len(page) as total; no total count query, so pagination metadata is misleading.
"""
API endpoints for audit log access and querying.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from src.audit import (
    get_audit_logger,
    AuditEvent,
    AuditEventType,
    AuditSeverity
)
from src.api.auth_middleware import auth_middleware, AuthUser

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"]
)


class AuditEventResponse(BaseModel):
    """Audit event response model."""
    id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_name: Optional[str] = None
    action: str
    description: str
    details: dict
    duration_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class AuditQueryResponse(BaseModel):
    """Response for audit queries."""
    events: List[AuditEventResponse]
    total: int
    offset: int
    limit: int


class AgentTimelineEntry(BaseModel):
    """Timeline entry for agent actions."""
    timestamp: datetime
    action: str
    description: str
    duration_ms: Optional[int] = None
    status: str  # success, failed, cancelled


class WorkflowTimelineEntry(BaseModel):
    """Timeline entry for workflow events."""
    timestamp: datetime
    event_type: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    description: str
    details: dict = Field(default_factory=dict)


@router.get("/events", response_model=AuditQueryResponse)
async def query_audit_events(
    workflow_id: Optional[str] = Query(None, description="Filter by workflow ID"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    event_type: Optional[AuditEventType] = Query(None, description="Filter by event type"),
    severity: Optional[AuditSeverity] = Query(None, description="Filter by severity"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history to query"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: AuthUser = Depends(auth_middleware.require_permission("audit", "view"))
):
    """Query audit events with filters."""
    audit_logger = await get_audit_logger()
    
    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    # Build event type filter
    event_types = [event_type] if event_type else None
    
    # Query events
    events = await audit_logger.query(
        workflow_id=workflow_id,
        agent_id=agent_id,
        agent_type=agent_type,
        event_types=event_types,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset
    )
    
    # Convert to response format
    event_responses = [
        AuditEventResponse(
            id=event.id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            severity=event.severity,
            workflow_id=event.workflow_id,
            agent_id=event.agent_id,
            agent_type=event.agent_type,
            agent_name=event.agent_name,
            action=event.action,
            description=event.description,
            details=event.details,
            duration_ms=event.duration_ms,
            error_type=event.error_type,
            error_message=event.error_message
        )
        for event in events
    ]
    
    return AuditQueryResponse(
        events=event_responses,
        total=len(event_responses),  # TODO: Add proper count query
        offset=offset,
        limit=limit
    )


@router.get("/agents/{agent_id}/history", response_model=List[AgentTimelineEntry])
async def get_agent_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return"),
    current_user: AuthUser = Depends(auth_middleware.require_permission("agents", "view"))
):
    """Get action history for a specific agent."""
    audit_logger = await get_audit_logger()
    
    events = await audit_logger.get_agent_history(agent_id=agent_id, limit=limit)
    
    # Convert to timeline format
    timeline = []
    for event in events:
        status = "success"
        if event.error_type:
            status = "failed"
        elif event.action == "cancelled":
            status = "cancelled"
            
        timeline.append(AgentTimelineEntry(
            timestamp=event.timestamp,
            action=event.action,
            description=event.description,
            duration_ms=event.duration_ms,
            status=status
        ))
    
    return timeline


@router.get("/workflows/{workflow_id}/timeline", response_model=List[WorkflowTimelineEntry])
async def get_workflow_timeline(
    workflow_id: str,
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """Get complete timeline of events for a workflow."""
    audit_logger = await get_audit_logger()
    
    events = await audit_logger.get_workflow_timeline(workflow_id=workflow_id)
    
    # Convert to timeline format
    timeline = []
    for event in events:
        timeline.append(WorkflowTimelineEntry(
            timestamp=event.timestamp,
            event_type=event.event_type,
            agent_id=event.agent_id,
            agent_name=event.agent_name,
            description=event.description,
            details=event.details
        ))
    
    return timeline


@router.get("/errors", response_model=List[AuditEventResponse])
async def get_recent_errors(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to query"),
    min_severity: AuditSeverity = Query(
        AuditSeverity.ERROR,
        description="Minimum severity level"
    ),
    current_user: AuthUser = Depends(auth_middleware.require_permission("audit", "view"))
):
    """Get recent error events."""
    audit_logger = await get_audit_logger()
    
    events = await audit_logger.get_recent_errors(
        hours=hours,
        min_severity=min_severity
    )
    
    # Convert to response format
    return [
        AuditEventResponse(
            id=event.id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            severity=event.severity,
            workflow_id=event.workflow_id,
            agent_id=event.agent_id,
            agent_type=event.agent_type,
            agent_name=event.agent_name,
            action=event.action,
            description=event.description,
            details=event.details,
            duration_ms=event.duration_ms,
            error_type=event.error_type,
            error_message=event.error_message
        )
        for event in events
    ]


@router.get("/stats", response_model=dict)
async def get_audit_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to analyze"),
    current_user: AuthUser = Depends(auth_middleware.require_permission("audit", "view"))
):
    """Get audit statistics."""
    audit_logger = await get_audit_logger()
    
    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    # Get all events in time range
    events = await audit_logger.query(
        start_time=start_time,
        end_time=end_time,
        limit=10000
    )
    
    # Calculate statistics
    stats = {
        "total_events": len(events),
        "time_range": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "hours": hours
        },
        "by_type": {},
        "by_severity": {},
        "agent_actions": {},
        "workflow_events": {},
        "error_count": 0,
        "average_duration_ms": 0,
        "top_agents": [],
        "top_errors": []
    }
    
    # Count by type and severity
    total_duration = 0
    duration_count = 0
    agent_action_counts = {}
    error_counts = {}
    
    for event in events:
        # Count by type
        event_type = event.event_type
        stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
        
        # Count by severity
        severity = event.severity
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
        
        # Count errors
        if event.error_type:
            stats["error_count"] += 1
            error_key = f"{event.error_type}: {event.action}"
            error_counts[error_key] = error_counts.get(error_key, 0) + 1
        
        # Track agent actions
        if event.agent_id:
            agent_key = f"{event.agent_name or event.agent_id}"
            agent_action_counts[agent_key] = agent_action_counts.get(agent_key, 0) + 1
        
        # Calculate average duration
        if event.duration_ms:
            total_duration += event.duration_ms
            duration_count += 1
    
    # Calculate average duration
    if duration_count > 0:
        stats["average_duration_ms"] = total_duration / duration_count
    
    # Top agents by activity
    stats["top_agents"] = sorted(
        [{"agent": k, "actions": v} for k, v in agent_action_counts.items()],
        key=lambda x: x["actions"],
        reverse=True
    )[:10]
    
    # Top errors
    stats["top_errors"] = sorted(
        [{"error": k, "count": v} for k, v in error_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:10]
    
    return stats
