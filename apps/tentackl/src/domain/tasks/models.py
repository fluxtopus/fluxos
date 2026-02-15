"""
Task Interface and Data Models

This module defines the core interfaces for the autonomous task execution system,
following the Persistent Task Document pattern to avoid context window degradation.

Key concepts:
- Task: External source of truth that persists across agent invocations
- TaskStep: Individual step in a task with status and checkpoint config
- CheckpointConfig: Configuration for human approval checkpoints
- TaskInterface: Abstract interface for task operations

Trigger Schema (stored in Task.metadata["trigger"]):
------------------------------------------------------
Tasks can be configured to execute automatically when matching events arrive.
The trigger configuration is stored in the task's metadata field.

Schema:
{
    "trigger": {
        "type": "event",                           # event | schedule | manual
        "event_pattern": "external.integration.*", # Event pattern to match (glob-style)
        "source_filter": "integration:xxx",        # Optional: filter by source prefix
        "condition": {                             # Optional: JSONLogic condition
            "==": [{"var": "data.command"}, "joke"]
        },
        "enabled": true                            # Whether trigger is active
    }
}

When a task has a trigger:
1. TaskTriggerRegistry indexes it by event_pattern
2. EventTriggerWorker checks the registry for matching tasks
3. Matching tasks are cloned and executed with event data injected
4. Step inputs can reference trigger data via ${trigger_event.data.*}

Example task with trigger:
{
    "id": "task-123",
    "goal": "Tell a joke when /joke command is used",
    "metadata": {
        "trigger": {
            "type": "event",
            "event_pattern": "external.integration.webhook",
            "source_filter": "integration:discord-bot-id",
            "condition": {"==": [{"var": "data.command"}, "joke"]},
            "enabled": true
        }
    },
    "steps": [
        {
            "name": "generate_joke",
            "agent_type": "compose",
            "inputs": {"topic": "Tell a programming joke", "format": "plain_text"}
        },
        {
            "name": "send_response",
            "agent_type": "discord_followup",
            "inputs": {
                "application_id": "${trigger_event.metadata.application_id}",
                "interaction_token": "${trigger_event.metadata.interaction_token}",
                "content": "${generate_joke.output.content}"
            },
            "dependencies": ["generate_joke"]
        }
    ]
}
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid


class TaskStatus(Enum):
    """Status of a task"""
    PLANNING = "planning"           # Task is being planned
    READY = "ready"                 # Task ready to execute
    EXECUTING = "executing"         # Task is running
    PAUSED = "paused"               # Manually paused
    CHECKPOINT = "checkpoint"       # Waiting for human approval
    COMPLETED = "completed"         # Successfully completed
    FAILED = "failed"               # Failed with error
    CANCELLED = "cancelled"         # Cancelled by user
    SUPERSEDED = "superseded"       # Task was replaced by a newer version (via REPLAN)


class StepStatus(Enum):
    """Status of an individual step"""
    PENDING = "pending"             # Not yet started
    RUNNING = "running"             # Currently executing
    DONE = "done"                   # Successfully completed
    FAILED = "failed"               # Failed with error
    CHECKPOINT = "checkpoint"       # Waiting for approval
    SKIPPED = "skipped"             # Skipped (rejected or dependency failed)


class ApprovalType(Enum):
    """Type of approval for checkpoints"""
    EXPLICIT = "explicit"           # Always requires explicit approval
    TIMEOUT = "timeout"             # Auto-approve after timeout
    AUTO = "auto"                   # Auto-approve based on learned preferences


class CheckpointType(Enum):
    """
    Type of interactive checkpoint.

    Extends beyond binary approve/reject to support rich user interactions:
    - APPROVAL: Binary approve/reject (existing default behavior)
    - INPUT: Collect structured user input via JSON schema
    - MODIFY: Allow user to modify step inputs before execution
    - SELECT: Choose from predefined alternatives
    - QA: Q&A dialog to answer specific questions
    """
    APPROVAL = "approval"     # Binary approve/reject (default)
    INPUT = "input"           # Collect structured user input
    MODIFY = "modify"         # Allow modification of step inputs
    SELECT = "select"         # Choose from alternatives
    QA = "qa"                 # Q&A dialog (ask specific questions)


class ProposalType(Enum):
    """Types of actions the Observer can propose for failure recovery."""
    RETRY = "retry"           # Retry the same step (transient failure)
    FALLBACK = "fallback"     # Switch to fallback option (permanent failure)
    SKIP = "skip"             # Skip non-critical step
    ABORT = "abort"           # Abort the task (critical failure, no recovery)
    REPLAN = "replan"         # Escalate to TaskPlannerAgent for strategic replanning
    MODIFY = "modify"         # Modify step inputs and retry (content filter, validation errors)


class ParallelFailurePolicy(Enum):
    """
    Policy for handling failures in parallel step groups.

    When multiple steps run in parallel, this determines what happens
    if one or more steps fail.
    """
    ALL_OR_NOTHING = "all_or_nothing"  # Fail entire group if any step fails
    BEST_EFFORT = "best_effort"        # Continue with partial results
    FAIL_FAST = "fail_fast"            # Cancel remaining steps on first failure


@dataclass
class FallbackConfig:
    """
    Configuration for fallback options when a step fails.

    Fallbacks allow the system to recover from failures by trying
    alternative models, APIs, or strategies.
    """
    models: List[str] = field(default_factory=list)      # Alternative LLM models
    apis: List[str] = field(default_factory=list)        # Alternative API endpoints
    strategies: List[str] = field(default_factory=list)  # Alternative approaches

    def to_dict(self) -> Dict[str, Any]:
        return {
            "models": self.models,
            "apis": self.apis,
            "strategies": self.strategies,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FallbackConfig':
        return cls(
            models=data.get("models", []),
            apis=data.get("apis", []),
            strategies=data.get("strategies", []),
        )

    def has_options(self) -> bool:
        """Check if any fallback options are available."""
        return bool(self.models or self.apis or self.strategies)

    def get_first_model(self) -> Optional[str]:
        """Get the first available fallback model."""
        return self.models[0] if self.models else None

    def get_first_api(self) -> Optional[str]:
        """Get the first available fallback API."""
        return self.apis[0] if self.apis else None


@dataclass
class ReplanContext:
    """
    Context passed to TaskPlannerAgent when strategic replanning is needed.

    The Observer generates this context to help the Planner understand:
    - What went wrong and why tactical recovery isn't possible
    - Which steps are affected and need revision
    - What outputs have been completed (to preserve)
    - Any new constraints discovered during execution
    """
    diagnosis: str                                    # What went wrong and why
    affected_steps: List[str] = field(default_factory=list)  # Step IDs that need revision
    completed_outputs: Dict[str, Any] = field(default_factory=dict)  # Outputs from successful steps
    constraints: List[str] = field(default_factory=list)  # New constraints discovered
    suggested_approach: Optional[str] = None          # Observer's suggestion (optional)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnosis": self.diagnosis,
            "affected_steps": self.affected_steps,
            "completed_outputs": self.completed_outputs,
            "constraints": self.constraints,
            "suggested_approach": self.suggested_approach,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReplanContext':
        return cls(
            diagnosis=data.get("diagnosis", ""),
            affected_steps=data.get("affected_steps", []),
            completed_outputs=data.get("completed_outputs", {}),
            constraints=data.get("constraints", []),
            suggested_approach=data.get("suggested_approach"),
        )


@dataclass
class ObserverProposal:
    """
    A proposal from the Observer to handle a failure.

    The Orchestrator decides whether to apply the proposal.

    For REPLAN proposals, replan_context contains the diagnosis and context
    needed by TaskPlannerAgent to generate a revised plan.

    For MODIFY proposals, modified_inputs contains the corrected inputs
    to use when retrying the step (e.g., rewritten prompts to avoid content filters).
    """
    proposal_type: ProposalType
    step_id: str
    reason: str
    confidence: float = 0.0
    fallback_target: Optional[str] = None  # Model or API to fallback to
    replan_context: Optional[ReplanContext] = None  # Context for REPLAN proposals
    modified_inputs: Optional[Dict[str, Any]] = None  # Modified inputs for MODIFY proposals
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_type": self.proposal_type.value,
            "step_id": self.step_id,
            "reason": self.reason,
            "confidence": self.confidence,
            "fallback_target": self.fallback_target,
            "replan_context": self.replan_context.to_dict() if self.replan_context else None,
            "modified_inputs": self.modified_inputs,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ObserverProposal':
        replan_context = None
        if data.get("replan_context"):
            replan_context = ReplanContext.from_dict(data["replan_context"])

        return cls(
            proposal_type=ProposalType(data["proposal_type"]),
            step_id=data["step_id"],
            reason=data["reason"],
            confidence=data.get("confidence", 0.0),
            fallback_target=data.get("fallback_target"),
            replan_context=replan_context,
            modified_inputs=data.get("modified_inputs"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
        )


@dataclass
class CheckpointConfig:
    """
    Configuration for a checkpoint requiring human interaction.

    Checkpoints are automatically detected for risky operations:
    - External API calls to non-allowlisted domains
    - Data mutations (writes, deletes)
    - Sending notifications/emails
    - Cost thresholds exceeded
    - Access to sensitive data

    Interactive checkpoint types:
    - APPROVAL: Binary approve/reject (default)
    - INPUT: Collect structured user input via input_schema (JSON Schema)
    - MODIFY: Allow user to modify step inputs (fields in modifiable_fields)
    - SELECT: Choose from predefined alternatives
    - QA: Answer specific questions before proceeding
    """
    name: str
    description: str
    approval_type: ApprovalType = ApprovalType.EXPLICIT
    timeout_minutes: int = 60  # Auto-approve after timeout (if approval_type=TIMEOUT)
    preference_key: Optional[str] = None  # Key for learned preferences
    required_approvers: int = 1
    preview_fields: List[str] = field(default_factory=list)  # Fields to show in preview

    # Interactive checkpoint configuration (Agent Memory System)
    checkpoint_type: CheckpointType = CheckpointType.APPROVAL
    input_schema: Optional[Dict[str, Any]] = None  # JSON Schema for INPUT type
    questions: Optional[List[str]] = None  # Questions for QA type
    alternatives: Optional[List[Dict[str, Any]]] = None  # Options for SELECT type
    modifiable_fields: Optional[List[str]] = None  # Fields user can modify for MODIFY type
    context_data: Optional[Dict[str, Any]] = None  # Context to show user (e.g., last week's meals)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "name": self.name,
            "description": self.description,
            "approval_type": self.approval_type.value,
            "timeout_minutes": self.timeout_minutes,
            "preference_key": self.preference_key,
            "required_approvers": self.required_approvers,
            "preview_fields": self.preview_fields,
            "checkpoint_type": self.checkpoint_type.value,
            "input_schema": self.input_schema,
            "questions": self.questions,
            "alternatives": self.alternatives,
            "modifiable_fields": self.modifiable_fields,
            "context_data": self.context_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointConfig':
        """Create from dictionary"""
        return cls(
            name=data["name"],
            description=data["description"],
            approval_type=ApprovalType(data.get("approval_type", "explicit")),
            timeout_minutes=data.get("timeout_minutes", 60),
            preference_key=data.get("preference_key"),
            required_approvers=data.get("required_approvers", 1),
            preview_fields=data.get("preview_fields", []),
            checkpoint_type=CheckpointType(data.get("checkpoint_type", "approval")),
            input_schema=data.get("input_schema"),
            questions=data.get("questions"),
            alternatives=data.get("alternatives"),
            modifiable_fields=data.get("modifiable_fields"),
            context_data=data.get("context_data"),
        )


@dataclass
class TaskStep:
    """
    Single step in a task execution plan.

    Each step is executed by a subagent with fresh context.
    Steps can have checkpoints for human approval.

    Domain-aware: Steps can specify a domain for cross-domain orchestration.
    If domain is not specified, agent_type is used for legacy compatibility.

    Parallel execution: Steps with the same parallel_group run concurrently.
    The dependencies field still controls ordering - parallel_group only affects
    steps that have no dependencies between them.
    """
    id: str
    name: str
    description: str
    agent_type: str  # http_fetch, summarize, compose, notify, analyze, etc.
    domain: Optional[str] = None  # research, content, cms, ops, code, etc.
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # Step IDs this depends on
    status: StepStatus = StepStatus.PENDING
    # Parallel execution fields
    parallel_group: Optional[str] = None  # Steps with same group run together
    failure_policy: ParallelFailurePolicy = ParallelFailurePolicy.ALL_OR_NOTHING
    # Checkpoint configuration
    checkpoint_required: bool = False
    checkpoint_config: Optional[CheckpointConfig] = None
    fallback_config: Optional[FallbackConfig] = None  # Fallback options for recovery
    is_critical: bool = True  # If False, step can be skipped on failure
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: Optional[int] = None

    def __post_init__(self):
        """Generate ID if not provided"""
        if not self.id:
            self.id = f"step_{str(uuid.uuid4())[:8]}"

    def is_ready(self, completed_steps: List[str]) -> bool:
        """Check if this step is ready to execute (all dependencies met)"""
        if self.status != StepStatus.PENDING:
            return False
        return all(dep in completed_steps for dep in self.dependencies)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "agent_type": self.agent_type,
            "domain": self.domain,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "parallel_group": self.parallel_group,
            "failure_policy": self.failure_policy.value,
            "checkpoint_required": self.checkpoint_required,
            "checkpoint_config": self.checkpoint_config.to_dict() if self.checkpoint_config else None,
            "fallback_config": self.fallback_config.to_dict() if self.fallback_config else None,
            "is_critical": self.is_critical,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_time_ms": self.execution_time_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskStep':
        """Create from dictionary"""
        checkpoint_config = None
        if data.get("checkpoint_config"):
            checkpoint_config = CheckpointConfig.from_dict(data["checkpoint_config"])

        fallback_config = None
        if data.get("fallback_config"):
            fallback_config = FallbackConfig.from_dict(data["fallback_config"])

        # Parse failure_policy with backward compatibility
        failure_policy = ParallelFailurePolicy.ALL_OR_NOTHING
        if data.get("failure_policy"):
            failure_policy = ParallelFailurePolicy(data["failure_policy"])

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            agent_type=data["agent_type"],
            domain=data.get("domain"),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            dependencies=data.get("dependencies", []),
            status=StepStatus(data.get("status", "pending")),
            parallel_group=data.get("parallel_group"),
            failure_policy=failure_policy,
            checkpoint_required=data.get("checkpoint_required", False),
            checkpoint_config=checkpoint_config,
            fallback_config=fallback_config,
            is_critical=data.get("is_critical", True),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            execution_time_ms=data.get("execution_time_ms"),
        )


@dataclass
class Finding:
    """
    An observation or learning accumulated during task execution.

    Findings are stored in the task document and persist across
    orchestrator invocations.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = ""
    type: str = ""  # http_fetch, summarize, anomaly, error, etc.
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step_id": self.step_id,
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Finding':
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            step_id=data.get("step_id", ""),
            type=data.get("type", ""),
            content=data.get("content", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
        )


@dataclass
class Task:
    """
    The persistent task document - source of truth for autonomous execution.

    This document persists across agent invocations, avoiding context
    window accumulation. The orchestrator reads this document fresh
    each cycle, makes one decision, updates it, and exits.

    A task represents a natural language goal that is broken down
    into executable steps and executed by AI agents.

    Key properties:
    - Immutable version history via parent_task_id
    - Steps with status tracking
    - Accumulated findings from execution
    - Checkpoint configurations for human approval
    - Parallel execution via parallel_group on steps
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    user_id: str = ""
    organization_id: Optional[str] = None
    goal: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)
    steps: List[TaskStep] = field(default_factory=list)
    accumulated_findings: List[Finding] = field(default_factory=list)
    current_step_index: int = 0
    status: TaskStatus = TaskStatus.PLANNING
    # Parallel execution settings
    max_parallel_steps: int = 5  # Maximum concurrent step executions
    # Execution tree and versioning
    tree_id: Optional[str] = None  # Links to execution tree for visualization
    parent_task_id: Optional[str] = None  # For versioned task evolution
    superseded_by: Optional[str] = None  # ID of task that replaced this one (via REPLAN)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Legacy compatibility fields used by delete/rerun/pause integration tests
    is_template: bool = False
    schedule_cron: Optional[str] = None
    schedule_enabled: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate task document"""
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.goal:
            raise ValueError("goal is required")

    def get_current_step(self) -> Optional[TaskStep]:
        """Get the current step being executed"""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def get_next_ready_step(self) -> Optional[TaskStep]:
        """Find the next step that's ready to execute"""
        completed_step_ids = [
            step.id for step in self.steps
            if step.status in (StepStatus.DONE, StepStatus.SKIPPED)
        ]
        for step in self.steps:
            if step.is_ready(completed_step_ids):
                return step
        return None

    def get_ready_steps_grouped(self) -> List[List[TaskStep]]:
        """
        Get all ready steps, grouped by parallel_group for concurrent execution.

        Returns a list of groups. Each group contains steps that can run together.
        Steps without a parallel_group are returned as single-step groups.
        """
        completed_step_ids = [
            step.id for step in self.steps
            if step.status in (StepStatus.DONE, StepStatus.SKIPPED)
        ]

        ready_steps = [
            step for step in self.steps
            if step.is_ready(completed_step_ids)
        ]

        if not ready_steps:
            return []

        groups: Dict[Optional[str], List[TaskStep]] = {}
        for step in ready_steps:
            group_key = step.parallel_group
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(step)

        result = []
        for group_key, steps in groups.items():
            if group_key is None:
                for step in steps:
                    result.append([step])
            else:
                result.append(steps)

        step_positions = {step.id: i for i, step in enumerate(self.steps)}
        result.sort(key=lambda group: step_positions.get(group[0].id, 0))

        return result

    def get_step_by_id(self, step_id: str) -> Optional[TaskStep]:
        """Get a step by its ID"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to the accumulated findings"""
        self.accumulated_findings.append(finding)
        self.updated_at = datetime.utcnow()

    def get_progress_percentage(self) -> float:
        """Calculate completion percentage"""
        if not self.steps:
            return 0.0
        completed = sum(1 for step in self.steps if step.status == StepStatus.DONE)
        return (completed / len(self.steps)) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "version": self.version,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "goal": self.goal,
            "constraints": self.constraints,
            "success_criteria": self.success_criteria,
            "steps": [step.to_dict() for step in self.steps],
            "accumulated_findings": [f.to_dict() for f in self.accumulated_findings],
            "current_step_index": self.current_step_index,
            "status": self.status.value,
            "max_parallel_steps": self.max_parallel_steps,
            "tree_id": self.tree_id,
            "parent_task_id": self.parent_task_id,
            "superseded_by": self.superseded_by,
            "metadata": self.metadata,
            "is_template": self.is_template,
            "schedule_cron": self.schedule_cron,
            "schedule_enabled": self.schedule_enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create from dictionary"""
        return cls(
            id=data["id"],
            version=data.get("version", 1),
            user_id=data["user_id"],
            organization_id=data.get("organization_id"),
            goal=data["goal"],
            constraints=data.get("constraints", {}),
            success_criteria=data.get("success_criteria", []),
            steps=[TaskStep.from_dict(s) for s in data.get("steps", [])],
            accumulated_findings=[Finding.from_dict(f) for f in data.get("accumulated_findings", [])],
            current_step_index=data.get("current_step_index", 0),
            status=TaskStatus(data.get("status", "planning")),
            max_parallel_steps=data.get("max_parallel_steps", 5),
            tree_id=data.get("tree_id"),
            parent_task_id=data.get("parent_task_id"),
            superseded_by=data.get("superseded_by"),
            metadata=data.get("metadata", {}),
            is_template=data.get("is_template", False),
            schedule_cron=data.get("schedule_cron"),
            schedule_enabled=data.get("schedule_enabled", False),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )

    def to_xml(self) -> str:
        """Convert to XML format for LLM prompts."""
        def step_attrs(step: TaskStep) -> str:
            attrs = f'id="{step.id}" status="{step.status.value}"'
            if step.domain:
                attrs += f' domain="{step.domain}"'
            if step.parallel_group:
                attrs += f' parallel_group="{step.parallel_group}"'
            return attrs

        steps_xml = "\n".join([
            f"""    <step {step_attrs(step)}>
      <name>{step.name}</name>
      <description>{step.description}</description>
      <agent_type>{step.agent_type}</agent_type>
      <checkpoint_required>{step.checkpoint_required}</checkpoint_required>
    </step>"""
            for step in self.steps
        ])

        return f"""<task id="{self.id}" version="{self.version}">
  <goal>{self.goal}</goal>
  <status>{self.status.value}</status>
  <progress_pct>{self.get_progress_percentage():.1f}</progress_pct>
  <max_parallel_steps>{self.max_parallel_steps}</max_parallel_steps>
  <steps>
{steps_xml}
  </steps>
</task>"""


class TaskInterface(ABC):
    """Abstract interface for task document operations."""

    @abstractmethod
    async def create_task(self, task: Task) -> str:
        """Create a new task."""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        pass

    @abstractmethod
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update a task with partial updates."""
        pass

    @abstractmethod
    async def update_step(self, task_id: str, step_id: str, updates: Dict[str, Any]) -> bool:
        """Update a specific step in a task."""
        pass

    @abstractmethod
    async def add_finding(self, task_id: str, finding: Finding) -> bool:
        """Add a finding to the task's accumulated findings."""
        pass

    @abstractmethod
    async def get_tasks_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """Get tasks for a user, optionally filtered by status."""
        pass

    @abstractmethod
    async def get_task_history(self, task_id: str, limit: int = 10) -> List[Task]:
        """Get version history for a task."""
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the task store is healthy."""
        pass


# Exceptions

class TaskException(Exception):
    """Base exception for task operations"""
    pass


class TaskNotFoundError(TaskException):
    """Raised when requested task is not found"""
    pass


class TaskValidationError(TaskException):
    """Raised when task data is invalid"""
    pass


class StepNotFoundError(TaskException):
    """Raised when requested step is not found"""
    pass


class CheckpointRequiredError(TaskException):
    """Raised when a step requires checkpoint approval"""
    def __init__(self, step_id: str, checkpoint_config: CheckpointConfig):
        self.step_id = step_id
        self.checkpoint_config = checkpoint_config
        super().__init__(f"Step {step_id} requires checkpoint approval: {checkpoint_config.name}")

