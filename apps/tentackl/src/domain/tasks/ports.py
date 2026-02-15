"""Domain ports for task operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, AsyncGenerator, Tuple

from src.domain.tasks.models import (
    ObserverProposal,
    ReplanContext,
    Task,
    TaskStatus,
    TaskStep,
)
from src.domain.tasks.planning_models import (
    PlanningIntent,
    ScheduleSpec,
    DataQuery,
    FastPathResult,
)


class TaskOperationsPort(Protocol):
    """Port for task lifecycle operations."""

    async def create_task(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
    ) -> Task:
        ...

    async def create_task_with_steps(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        steps: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        ...

    async def get_task(self, task_id: str) -> Optional[Task]:
        ...

    async def list_tasks(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        ...

    async def execute_task(
        self,
        task_id: str,
        user_id: str,
        run_to_completion: bool = False,
    ) -> Any:
        ...

    async def start_task(self, task_id: str, user_id: str) -> Any:
        ...

    async def pause_task(self, task_id: str, user_id: str) -> Task:
        ...

    async def cancel_task(self, task_id: str, user_id: str) -> Task:
        ...

    async def observe_execution(
        self,
        task_id: str,
        user_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        ...

    async def link_conversation(self, task_id: str, conversation_id: str) -> None:
        ...

    async def set_parent_task(self, task_id: str, parent_task_id: str) -> None:
        ...

    async def clone_task_for_trigger(
        self,
        template_task_id: str,
        trigger_event: Dict[str, Any],
    ) -> Task:
        ...

    async def clone_and_execute_from_automation(
        self,
        automation_id: str,
        template_task_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> Task:
        ...

    async def update_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        ...


class TaskOrchestratorPort(Protocol):
    """Port for orchestrator operations used during task execution."""

    async def initialize(self) -> None:
        ...

    async def cleanup(self) -> None:
        ...

    async def start_conversation(
        self,
        workflow_id: str,
        trigger_type: Any,
        trigger_source: str,
        trigger_details: Dict[str, Any],
    ) -> Optional[str]:
        ...

    async def end_conversation(self, status: Any) -> bool:
        ...

    async def execute_cycle(self, plan_id: str) -> Dict[str, Any]:
        ...

    async def execute_replan(self, plan_id: str, step_id: str) -> Dict[str, Any]:
        ...


class TaskPlanStorePort(Protocol):
    """Port for task plan storage operations."""

    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def create_task(self, task: Task) -> str:
        ...

    async def get_task(self, task_id: str) -> Optional[Task]:
        ...

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        ...

    async def update_step(self, plan_id: str, step_id: str, updates: Dict[str, Any]) -> bool:
        ...

    async def add_finding(self, plan_id: str, finding: Any) -> bool:
        ...


class TaskObserverPort(Protocol):
    """Port for task observer operations."""

    async def initialize(self) -> None:
        ...

    async def cleanup(self) -> None:
        ...

    async def observe(
        self,
        plan_id: str,
        execution_state: Optional[Dict[str, Any]] = None,
        recent_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        ...

    async def analyze_failure(self, plan: Task, failed_step: TaskStep) -> ObserverProposal:
        ...

    async def analyze_blocked_dependencies(
        self,
        plan: Task,
        blocked_steps: List[TaskStep],
        failed_steps: List[TaskStep],
    ) -> Optional[ObserverProposal]:
        ...


class TaskPlannerPort(Protocol):
    """Port for task planning operations."""

    async def initialize(self) -> None:
        ...

    async def cleanup(self) -> None:
        ...

    async def start_conversation(
        self,
        workflow_id: str,
        trigger_type: Any,
        trigger_source: str,
        trigger_details: Dict[str, Any],
    ) -> Optional[str]:
        ...

    async def end_conversation(self, status: Any) -> bool:
        ...

    async def generate_delegation_steps(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        skip_validation: bool = False,
    ) -> List[Any]:
        ...

    async def replan(
        self,
        original_plan: Task,
        failed_step: TaskStep,
        replan_context: ReplanContext,
    ) -> Task:
        ...


class PlanningIntentPort(Protocol):
    """Port for extracting planning intent."""

    async def extract_intent(self, goal: str) -> Optional[PlanningIntent]:
        ...


class FastPathPlannerPort(Protocol):
    """Port for fast-path planning and data retrieval."""

    async def try_fast_path(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: Optional[PlanningIntent],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        ...

    async def execute_query(self, organization_id: str, data_query: DataQuery) -> FastPathResult:
        ...

    async def create_fast_path_task(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: PlanningIntent,
        fast_result: FastPathResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        ...


class AutomationSchedulerPort(Protocol):
    """Port for automation creation from schedules."""

    async def create_automation_for_task(
        self,
        task_id: str,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        schedule: ScheduleSpec,
    ) -> Optional[str]:
        ...


class PlanCancellationPort(Protocol):
    """Port for planning cancellation checks."""

    async def is_cancelled(self, task_id: str) -> bool:
        ...

    async def cancel(self, task_id: str) -> None:
        ...


class PlanningEventBusPort(Protocol):
    """Port for planning lifecycle events."""

    async def planning_started(self, task_id: str, goal: str) -> str:
        ...

    async def planning_intent_detected(self, task_id: str, intent: str, detail: str) -> str:
        ...

    async def planning_fast_path(self, task_id: str, message: str) -> str:
        ...

    async def planning_llm_started(self, task_id: str) -> str:
        ...

    async def planning_llm_retry(
        self,
        task_id: str,
        attempt: int,
        max_retries: int,
        reason: str,
    ) -> str:
        ...

    async def planning_steps_generated(self, task_id: str, step_count: int, step_names: List[str]) -> str:
        ...

    async def planning_risk_detection(self, task_id: str, checkpoints_added: int) -> str:
        ...

    async def planning_completed(self, task_id: str, step_count: int, source: str) -> str:
        ...

    async def planning_failed(self, task_id: str, error: str) -> str:
        ...


class TaskPlanningStorePort(Protocol):
    """Port for task planning persistence."""

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        ...

    async def get_task(self, task_id: str) -> Optional[Task]:
        ...

    async def update_step(self, task_id: str, step_id: str, updates: Dict[str, Any]) -> None:
        ...


class TaskQueryPort(Protocol):
    """Port for task read/query patterns across hot/cold stores."""

    async def get_task(self, task_id: str) -> Optional[Task]:
        ...

    async def get_task_for_execution(self, task_id: str) -> Optional[Task]:
        ...

    async def get_tasks_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        ...

    async def get_stuck_planning_tasks(
        self,
        timeout_minutes: int = 5,
    ) -> List[Task]:
        ...


class TaskPersistencePort(Protocol):
    """Port for task persistence operations across storage layers."""

    async def create_task(self, task: Task) -> None:
        ...

    async def get_task(self, task_id: str) -> Optional[Task]:
        ...

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        ...

    async def update_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        ...

    async def set_parent_task(self, task_id: str, parent_task_id: str) -> None:
        ...


class TaskStatusTransitionPort(Protocol):
    """Port for task status transitions."""

    async def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        additional_updates: Optional[Dict[str, Any]] = None,
    ) -> Task:
        ...


class TaskExecutionTreePort(Protocol):
    """Port for task execution tree operations."""

    async def create_task_tree(self, task: Task) -> str:
        ...

    async def get_step_from_tree(self, task_id: str, step_id: str) -> Optional[TaskStep]:
        ...

    async def start_step(self, task_id: str, step_id: str) -> bool:
        ...

    async def complete_step(self, task_id: str, step_id: str, outputs: Dict[str, Any]) -> bool:
        ...

    async def fail_step(self, task_id: str, step_id: str, error: str) -> bool:
        ...

    async def pause_step(self, task_id: str, step_id: str) -> bool:
        ...

    async def reset_step(self, task_id: str, step_id: str) -> bool:
        ...

    async def is_task_complete(self, task_id: str) -> Tuple[bool, Optional[str]]:
        ...

    async def get_tree_metrics(self, task_id: str) -> Dict[str, Any]:
        ...


class TaskExecutionEventBusPort(Protocol):
    """Port for task execution event publishing."""

    async def task_started(
        self,
        task_id: str,
        goal: str,
        step_count: int,
        user_id: str,
    ) -> str:
        ...

    async def checkpoint_created(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        preview: Dict[str, Any],
    ) -> str:
        ...

    async def checkpoint_auto_approved(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
    ) -> str:
        ...

    async def inbox_message_created(
        self,
        user_id: str,
        conversation_id: str,
        message_preview: str,
        priority: str,
    ) -> str:
        ...


class TaskExecutionEventSubscription(Protocol):
    """Subscription handle for task execution events."""

    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        ...

    async def close(self) -> None:
        ...


class TaskExecutionEventStreamPort(Protocol):
    """Port for consuming task execution events."""

    async def get_recent_events(
        self,
        task_id: str,
        count: int = 100,
    ) -> List[Dict[str, Any]]:
        ...

    async def subscribe(self, task_id: str) -> TaskExecutionEventSubscription:
        ...


class TaskStepDispatchPort(Protocol):
    """Port for queue-mode step dispatch."""

    async def dispatch_step(
        self,
        task_id: str,
        step: TaskStep,
        plan: Task,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...


class TaskSchedulerPort(Protocol):
    """Port for scheduling ready task steps."""

    async def schedule_ready_nodes(self, task_id: str) -> int:
        ...


class TaskConversationPort(Protocol):
    """Port for inbox conversation helpers tied to tasks."""

    async def ensure_conversation(self, task_id: str, goal: str, user_id: str) -> None:
        ...

    async def add_checkpoint_resolution_message(
        self,
        task_id: str,
        approved: bool,
        reason: str = "",
    ) -> None:
        ...

    async def link_task_to_conversation(self, task_id: str, conversation_id: str) -> None:
        ...


class PreferenceLearningPort(Protocol):
    """Port for preference-learning side effects in execution flows."""

    async def learn_from_replan(
        self,
        user_id: str,
        step_name: str,
        old_approach: Dict[str, Any],
        new_approach: Dict[str, Any],
        reason: str,
    ) -> Any:
        ...


class TaskSummaryPort(Protocol):
    """Port for generating task completion summaries."""

    async def generate_summary_safe(
        self,
        goal: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        key_outputs: Dict[str, Any],
        findings: List[Any],
        error: Optional[str] = None,
    ) -> str:
        ...


class StepPluginExecutorPort(Protocol):
    """Port for executing a task step via plugins or LLM agents."""

    async def execute(
        self,
        step: TaskStep,
        model: str,
        task_id: Optional[str] = None,
        org_id: Optional[str] = None,
        step_id: Optional[str] = None,
        file_references: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        ...


class StepInboxMessagingPort(Protocol):
    """Port for sending inbox messages during step execution."""

    async def add_step_message(
        self,
        task_id: str,
        step_name: str,
        event_type: str,
        text: str,
        data: Dict[str, Any],
    ) -> None:
        ...

    async def add_checkpoint_message(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        description: str,
    ) -> None:
        ...

    async def add_completion_message(
        self,
        task_id: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        error: Optional[str] = None,
    ) -> None:
        ...


class StepCheckpointPort(Protocol):
    """Port for checkpoint approval checks and creation."""

    async def is_already_approved(self, task_id: str, step_id: str) -> bool:
        ...

    async def create_checkpoint(
        self,
        task_id: str,
        step: TaskStep,
        user_id: str,
    ) -> None:
        ...


class StepModelSelectorPort(Protocol):
    """Port for selecting the LLM model for a step."""

    def select_model(self, agent_type: str, explicit_model: Optional[str] = None) -> str:
        ...


class CapabilityEmbeddingPort(Protocol):
    """Port for capability embedding operations from worker tasks."""

    @property
    def is_enabled(self) -> bool:
        ...

    async def generate_and_store_embedding(self, capability_id: str) -> bool:
        ...

    async def backfill_embeddings(
        self,
        batch_size: int = 50,
        organization_id: Optional[str] = None,
    ) -> Dict[str, int]:
        ...
