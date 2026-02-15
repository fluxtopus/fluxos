# REVIEW:
# - Agent.start owns metrics, audit, error monitoring; core agent class is heavy and tightly coupled to observability.
# - Exceptions re-raised without normalization; callers must handle raw exceptions.
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from enum import Enum
from datetime import datetime
import uuid
import asyncio
from pydantic import BaseModel, Field
import structlog
from src.monitoring.metrics import MetricsCollector, agent_executions, workflow_active
from src.monitoring.error_monitor import get_error_monitor
from src.audit import get_audit_logger, AuditEventType, audit_context

logger = structlog.get_logger()


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    COMPLETED = "completed"


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    recipient_id: Optional[str] = None
    content: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: str = "default"


class AgentConfig(BaseModel):
    name: str
    agent_type: str
    timeout: int = 300
    max_retries: int = 3
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Agent(ABC):
    """Base agent class - handles execution logic only (SRP)"""
    
    def __init__(self, config: AgentConfig):
        self.id = str(uuid.uuid4())
        self.agent_id = self.id  # For compatibility with conversation tracking
        self.config = config
        self.status = AgentStatus.IDLE
        self.created_at = datetime.utcnow()
        self._task = None
        
    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Any:
        """Execute the agent's main task"""
        pass
    
    async def initialize(
        self,
        context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        execution_node_id: Optional[str] = None
    ) -> None:
        """
        Initialize the agent with context and execution tracking.
        
        Default no-op implementation. Subclasses can override to set up
        resources like LLM clients, state stores, context managers, etc.
        
        Args:
            context_id: Optional existing context ID
            tree_id: Optional execution tree ID
            execution_node_id: Optional execution node ID
        """
        # No-op by default - agents that need initialization can override
        pass
    
    async def start(self, task: Dict[str, Any]) -> Any:
        """Start agent execution"""
        if self.status != AgentStatus.IDLE:
            raise RuntimeError(f"Agent {self.id} is not idle")
        
        self.status = AgentStatus.RUNNING
        logger.info(f"Agent {self.id} starting", agent_name=self.config.name)
        
        # Get workflow ID from task if available
        workflow_id = task.get('workflow_id') or task.get('metadata', {}).get('workflow_id')
        
        # Track agent execution with metrics
        @MetricsCollector.track_agent_execution(self.config.agent_type, self.id)
        async def _execute_with_metrics():
            return await self.execute(task)
        
        # Track request in error monitor
        error_monitor = get_error_monitor()
        if error_monitor:
            error_monitor.track_request("agent")
        
        # Use audit context for automatic logging
        async with audit_context(
            event_type=AuditEventType.AGENT_STARTED,
            agent_id=self.id,
            agent_type=self.config.agent_type,
            agent_name=self.config.name,
            workflow_id=workflow_id,
            action="started",
            details={"task": task}
        ):
            try:
                self._task = asyncio.create_task(_execute_with_metrics())
                result = await self._task
                self.status = AgentStatus.COMPLETED
                
                # Log completion
                audit_logger = await get_audit_logger()
                await audit_logger.log_agent_action(
                    agent_id=self.id,
                    agent_type=self.config.agent_type,
                    agent_name=self.config.name,
                    action="completed",
                    workflow_id=workflow_id,
                    details={"result": result if isinstance(result, dict) else {"output": str(result)}}
                )
                
                return result
                
            except asyncio.CancelledError:
                self.status = AgentStatus.STOPPED
                logger.info(f"Agent {self.id} cancelled")
                agent_executions.labels(
                    agent_type=self.config.agent_type,
                    agent_id=self.id,
                    status="cancelled"
                ).inc()
                
                # Log cancellation
                audit_logger = await get_audit_logger()
                await audit_logger.log_agent_action(
                    agent_id=self.id,
                    agent_type=self.config.agent_type,
                    agent_name=self.config.name,
                    action="cancelled",
                    workflow_id=workflow_id
                )
                raise
                
            except Exception as e:
                self.status = AgentStatus.FAILED
                logger.error(f"Agent {self.id} failed", error=str(e))
                
                # Track error in error monitor
                if error_monitor:
                    error_type = type(e).__name__.lower()
                    error_monitor.track_error("agent", error_type, {
                        "agent_id": self.id,
                        "agent_type": self.config.agent_type,
                        "agent_name": self.config.name,
                        "error": str(e)
                    })
                
                raise
    
    async def stop(self) -> None:
        """Stop agent execution"""
        if self._task and not self._task.done():
            self._task.cancel()
            self.status = AgentStatus.STOPPED
            logger.info(f"Agent {self.id} stopped")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current agent state"""
        return {
            "id": self.id,
            "name": self.config.name,
            "type": self.config.agent_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat()
        }
