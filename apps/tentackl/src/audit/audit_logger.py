"""
Audit logging system for Tentackl.

Tracks all agent actions, workflow events, and system operations.
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
import uuid
import structlog
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
from sqlalchemy import Column, String, DateTime, JSON, Text, Index, BigInteger, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_, or_, func

from src.core.config import settings

logger = structlog.get_logger()

Base = declarative_base()


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Agent events
    AGENT_CREATED = "agent.created"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_CANCELLED = "agent.cancelled"
    AGENT_STATE_CHANGE = "agent.state_change"
    
    # Workflow events
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_RESUMED = "workflow.resumed"
    
    # Event bus events
    EVENT_PUBLISHED = "event.published"
    EVENT_RECEIVED = "event.received"
    EVENT_PROCESSED = "event.processed"
    EVENT_FAILED = "event.failed"
    
    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_CONFIG_CHANGE = "system.config_change"
    
    # Data events
    STATE_SAVED = "state.saved"
    STATE_LOADED = "state.loaded"
    CONTEXT_CREATED = "context.created"
    CONTEXT_UPDATED = "context.updated"
    
    # External events
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    API_CALL_MADE = "api.call_made"
    API_CALL_FAILED = "api.call_failed"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents an audit event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: AuditEventType = AuditEventType.AGENT_STARTED
    severity: AuditSeverity = AuditSeverity.INFO
    
    # Context
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_name: Optional[str] = None
    
    # Event details
    action: str = ""
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Performance metrics
    duration_ms: Optional[int] = None
    
    # Error information
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AuditLogEntry(Base):
    """Database model for audit log entries."""
    __tablename__ = 'audit_logs'
    
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)
    
    # Context
    workflow_id = Column(String, index=True)
    agent_id = Column(String, index=True)
    agent_type = Column(String, index=True)
    agent_name = Column(String)
    
    # Event details
    action = Column(String, nullable=False)
    description = Column(Text)
    details = Column(JSON)
    
    # Performance
    duration_ms = Column(BigInteger)
    
    # Error info
    error_type = Column(String)
    error_message = Column(Text)
    error_traceback = Column(Text)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_workflow_timestamp', 'workflow_id', 'timestamp'),
        Index('idx_agent_timestamp', 'agent_id', 'timestamp'),
        Index('idx_event_severity', 'event_type', 'severity'),
    )


class AuditLogger:
    """Centralized audit logging system."""
    
    def __init__(self, 
                 database_url: Optional[str] = None,
                 redis_url: Optional[str] = None,
                 buffer_size: int = 1000,
                 flush_interval: int = 5):
        """
        Initialize audit logger.
        
        Args:
            database_url: PostgreSQL connection URL
            redis_url: Redis connection URL for buffering
            buffer_size: Max events to buffer before flushing
            flush_interval: Seconds between automatic flushes
        """
        self.database_url = database_url or getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")
        self.redis_url = redis_url or getattr(settings, "REDIS_URL", "redis://redis:6379")
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._redis_client: Optional[redis_async.Redis] = None
        self._buffer: List[AuditEvent] = []
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize database and Redis connections."""
        # Initialize database
        if self.database_url:
            # Ensure asyncpg driver for async engine
            async_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")
            # Force override internal URL to avoid psycopg2
            self.database_url = async_url
            print(f"[AuditLogger] Using DB URL: {async_url}")
            logger.info("Audit logger using async DB URL", url=async_url)
            self._engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=5,
                max_overflow=10
            )
            
            self._session_factory = sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create table first, then idempotent indexes
            async with self._engine.begin() as conn:
                # Create table idempotently via raw SQL to avoid duplicate index issues
                await conn.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id VARCHAR PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL,
                        event_type VARCHAR NOT NULL,
                        severity VARCHAR NOT NULL,
                        workflow_id VARCHAR,
                        agent_id VARCHAR,
                        agent_type VARCHAR,
                        agent_name VARCHAR,
                        action VARCHAR NOT NULL,
                        description TEXT,
                        details JSON,
                        duration_ms BIGINT,
                        error_type VARCHAR,
                        error_message TEXT,
                        error_traceback TEXT
                    )
                    """
                ))
                
                # Ensure indexes exist (idempotent)
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workflow_timestamp ON audit_logs (workflow_id, timestamp)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_timestamp ON audit_logs (agent_id, timestamp)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_event_severity ON audit_logs (event_type, severity)"))
                
            logger.info("Audit logger database initialized")
        
        # Initialize Redis for buffering
        self._redis_client = await redis_async.from_url(
            self.redis_url,
            decode_responses=True
        )
        
        # Start flush task
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        
        logger.info("Audit logger initialized")
        
    async def shutdown(self):
        """Shutdown audit logger."""
        self._running = False
        
        # Flush remaining events
        await self._flush_buffer()
        
        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
                
        # Close connections
        if self._redis_client:
            await self._redis_client.aclose()
            
        if self._engine:
            await self._engine.dispose()
            
        logger.info("Audit logger shutdown")
        
    async def log(self, event: AuditEvent):
        """Log an audit event."""
        try:
            # Add to buffer
            self._buffer.append(event)
            
            # Also push to Redis for real-time streaming
            if self._redis_client:
                await self._redis_client.xadd(
                    "audit:stream",
                    {
                        "event": json.dumps(event.to_dict()),
                        "type": event.event_type,
                        "severity": event.severity
                    },
                    maxlen=10000  # Keep last 10k events in stream
                )
                
                # Publish for real-time subscribers
                await self._redis_client.publish(
                    f"audit:events:{event.event_type}",
                    json.dumps(event.to_dict())
                )
            
            # Flush if buffer is full
            if len(self._buffer) >= self.buffer_size:
                await self._flush_buffer()
                
        except Exception as e:
            logger.error("Failed to log audit event", error=str(e), event_id=event.id)
            
    async def log_agent_action(self,
                              agent_id: str,
                              agent_type: str,
                              agent_name: str,
                              action: str,
                              workflow_id: Optional[str] = None,
                              details: Optional[Dict[str, Any]] = None,
                              duration_ms: Optional[int] = None,
                              error: Optional[Exception] = None):
        """Convenience method to log agent actions."""
        event_type = AuditEventType.AGENT_STARTED
        severity = AuditSeverity.INFO
        
        if error:
            event_type = AuditEventType.AGENT_FAILED
            severity = AuditSeverity.ERROR
        elif action == "completed":
            event_type = AuditEventType.AGENT_COMPLETED
        elif action == "cancelled":
            event_type = AuditEventType.AGENT_CANCELLED
            severity = AuditSeverity.WARNING
            
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            workflow_id=workflow_id,
            agent_id=agent_id,
            agent_type=agent_type,
            agent_name=agent_name,
            action=action,
            description=f"Agent {agent_name} ({agent_type}) {action}",
            details=details or {},
            duration_ms=duration_ms,
            error_type=type(error).__name__ if error else None,
            error_message=str(error) if error else None
        )
        
        await self.log(event)
        
    async def log_workflow_event(self,
                               workflow_id: str,
                               event_type: AuditEventType,
                               description: str,
                               details: Optional[Dict[str, Any]] = None,
                               severity: AuditSeverity = AuditSeverity.INFO):
        """Log a workflow-level event."""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            workflow_id=workflow_id,
            action=event_type.split('.')[-1],
            description=description,
            details=details or {}
        )
        
        await self.log(event)
        
    async def _flush_loop(self):
        """Periodically flush buffer to database."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_buffer()
            except Exception as e:
                logger.error("Error in flush loop", error=str(e))
                
    async def _flush_buffer(self):
        """Flush buffered events to database."""
        if not self._buffer or not self._session_factory:
            return
            
        # Get events to flush
        events_to_flush = self._buffer[:self.buffer_size]
        self._buffer = self._buffer[self.buffer_size:]
        
        try:
            async with self._session_factory() as session:
                # Convert to database models
                entries = []
                for event in events_to_flush:
                    entry = AuditLogEntry(
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
                        error_message=event.error_message,
                        error_traceback=event.error_traceback
                    )
                    entries.append(entry)
                
                # Bulk insert
                session.add_all(entries)
                await session.commit()
                
                logger.debug(f"Flushed {len(entries)} audit events to database")
                
        except Exception as e:
            logger.error("Failed to flush audit events", error=str(e))
            # Put events back in buffer for retry
            self._buffer = events_to_flush + self._buffer
            
    async def query(self,
                   workflow_id: Optional[str] = None,
                   agent_id: Optional[str] = None,
                   agent_type: Optional[str] = None,
                   event_types: Optional[List[AuditEventType]] = None,
                   severity: Optional[AuditSeverity] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: int = 1000,
                   offset: int = 0) -> List[AuditEvent]:
        """Query audit logs."""
        if not self._session_factory:
            return []
            
        async with self._session_factory() as session:
            query = select(AuditLogEntry)
            
            # Build filters
            filters = []
            
            if workflow_id:
                filters.append(AuditLogEntry.workflow_id == workflow_id)
            if agent_id:
                filters.append(AuditLogEntry.agent_id == agent_id)
            if agent_type:
                filters.append(AuditLogEntry.agent_type == agent_type)
            if event_types:
                filters.append(AuditLogEntry.event_type.in_(event_types))
            if severity:
                filters.append(AuditLogEntry.severity == severity)
            if start_time:
                filters.append(AuditLogEntry.timestamp >= start_time)
            if end_time:
                filters.append(AuditLogEntry.timestamp <= end_time)
                
            if filters:
                query = query.where(and_(*filters))
                
            # Order by timestamp descending
            query = query.order_by(AuditLogEntry.timestamp.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            entries = result.scalars().all()
            
            # Convert to AuditEvent objects
            events = []
            for entry in entries:
                event = AuditEvent(
                    id=entry.id,
                    timestamp=entry.timestamp,
                    event_type=entry.event_type,
                    severity=entry.severity,
                    workflow_id=entry.workflow_id,
                    agent_id=entry.agent_id,
                    agent_type=entry.agent_type,
                    agent_name=entry.agent_name,
                    action=entry.action,
                    description=entry.description,
                    details=entry.details or {},
                    duration_ms=entry.duration_ms,
                    error_type=entry.error_type,
                    error_message=entry.error_message,
                    error_traceback=entry.error_traceback
                )
                events.append(event)
                
            return events
            
    async def get_agent_history(self, agent_id: str, limit: int = 100) -> List[AuditEvent]:
        """Get audit history for a specific agent."""
        return await self.query(agent_id=agent_id, limit=limit)
        
    async def get_workflow_timeline(self, workflow_id: str) -> List[AuditEvent]:
        """Get complete timeline of events for a workflow."""
        return await self.query(workflow_id=workflow_id, limit=10000)
        
    async def get_recent_errors(self, 
                               hours: int = 24,
                               min_severity: AuditSeverity = AuditSeverity.ERROR) -> List[AuditEvent]:
        """Get recent error events."""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Get all severities at or above min_severity
        severity_order = [AuditSeverity.DEBUG, AuditSeverity.INFO, 
                         AuditSeverity.WARNING, AuditSeverity.ERROR, 
                         AuditSeverity.CRITICAL]
        min_idx = severity_order.index(min_severity)
        severities = severity_order[min_idx:]
        
        events = []
        for severity in severities:
            events.extend(await self.query(
                severity=severity,
                start_time=start_time,
                limit=1000
            ))
            
        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events
        
    async def stream_events(self, 
                           event_types: Optional[List[AuditEventType]] = None,
                           callback: Optional[callable] = None):
        """Stream audit events in real-time."""
        if not self._redis_client:
            return
            
        pubsub = self._redis_client.pubsub()
        
        # Subscribe to relevant channels
        channels = []
        if event_types:
            for event_type in event_types:
                channels.append(f"audit:events:{event_type}")
        else:
            channels.append("audit:events:*")
            
        await pubsub.psubscribe(*channels)
        
        try:
            async for message in pubsub.listen():
                if message['type'] in ('message', 'pmessage'):
                    try:
                        event_data = json.loads(message['data'])
                        event = AuditEvent(**event_data)
                        
                        if callback:
                            await callback(event)
                            
                    except Exception as e:
                        logger.error("Error processing audit stream event", error=str(e))
                        
        finally:
            await pubsub.close()


# Global instance
_audit_logger: Optional[AuditLogger] = None


async def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
        await _audit_logger.initialize()
    return _audit_logger


async def stop_audit_logger():
    """Stop the global audit logger."""
    global _audit_logger
    if _audit_logger:
        await _audit_logger.shutdown()
        _audit_logger = None


# Context manager for audit logging
@asynccontextmanager
async def audit_context(event_type: AuditEventType,
                       agent_id: Optional[str] = None,
                       agent_type: Optional[str] = None,
                       agent_name: Optional[str] = None,
                       workflow_id: Optional[str] = None,
                       action: str = "",
                       details: Optional[Dict[str, Any]] = None):
    """Context manager for automatic audit logging with timing."""
    logger = await get_audit_logger()
    start_time = datetime.utcnow()
    error = None
    
    try:
        yield logger
    except Exception as e:
        error = e
        raise
    finally:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        if agent_id:
            await logger.log_agent_action(
                agent_id=agent_id,
                agent_type=agent_type or "unknown",
                agent_name=agent_name or agent_id,
                action=action or event_type.split('.')[-1],
                workflow_id=workflow_id,
                details=details,
                duration_ms=duration_ms,
                error=error
            )
        else:
            event = AuditEvent(
                event_type=event_type,
                severity=AuditSeverity.ERROR if error else AuditSeverity.INFO,
                workflow_id=workflow_id,
                action=action,
                details=details or {},
                duration_ms=duration_ms,
                error_type=type(error).__name__ if error else None,
                error_message=str(error) if error else None
            )
            await logger.log(event)
