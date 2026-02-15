"""Application runtime composing task use cases and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional
import asyncio
import structlog

from src.infrastructure.tasks.task_observer import ObservationReport
from src.domain.tasks.models import Task, TaskStatus
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.domain.checkpoints import CheckpointResponse, CheckpointState
from src.domain.tasks.risk_detector import RiskDetectorService
from src.llm.openrouter_client import OpenRouterClient
from src.domain.memory import MemoryOperationsPort
from src.domain.tasks.ports import (
    TaskObserverPort,
    TaskOrchestratorPort,
    TaskPlannerPort,
    PlanningIntentPort,
    FastPathPlannerPort,
    AutomationSchedulerPort,
    PlanCancellationPort,
    PlanningEventBusPort,
    TaskPlanningStorePort,
    TaskQueryPort,
    TaskPersistencePort,
    TaskPlanStorePort,
    TaskStatusTransitionPort,
    TaskExecutionTreePort,
    TaskExecutionEventBusPort,
    TaskExecutionEventStreamPort,
    TaskSchedulerPort,
    TaskConversationPort,
    PreferenceLearningPort,
)
from src.domain.tasks.planning_models import PlanningIntent, ScheduleSpec, DataQuery, FastPathResult
from src.application.tasks.plan_task_use_case import PlanTaskUseCase
from src.application.tasks.execute_task_use_case import TaskExecutionUseCase
from src.application.tasks.task_setup_use_cases import (
    CreateTaskWithStepsUseCase,
    CloneTaskForTriggerUseCase,
)
from src.application.tasks.lifecycle_task_use_case import TaskLifecycleUseCase
from src.infrastructure.memory import build_memory_use_cases
from src.infrastructure.tasks.task_orchestrator_adapter import TaskOrchestratorAdapter
from src.infrastructure.tasks.task_observer_adapter import TaskObserverAdapter
from src.infrastructure.tasks.task_planner_adapter import TaskPlannerAdapter
from src.infrastructure.tasks.planning_intent_adapter import PlanningIntentAdapter
from src.infrastructure.tasks.fast_path_planner_adapter import FastPathPlannerAdapter
from src.infrastructure.tasks.automation_scheduler_adapter import AutomationSchedulerAdapter
from src.infrastructure.tasks.plan_cancellation_adapter import PlanCancellationAdapter
from src.infrastructure.tasks.planning_event_bus_adapter import PlanningEventBusAdapter
from src.infrastructure.tasks.task_planning_store_adapter import TaskPlanningStoreAdapter
from src.infrastructure.tasks.task_status_transition_adapter import TaskStatusTransitionAdapter
from src.infrastructure.tasks.task_plan_store_adapter import TaskPlanStoreAdapter
from src.infrastructure.tasks.task_execution_event_bus_adapter import TaskExecutionEventBusAdapter
from src.infrastructure.tasks.task_execution_event_stream_adapter import (
    TaskExecutionEventStreamAdapter,
)
from src.infrastructure.tasks.task_scheduler_adapter import TaskSchedulerAdapter
from src.infrastructure.tasks.task_conversation_adapter import TaskConversationAdapter
from src.infrastructure.tasks.task_persistence_adapter import TaskPersistenceAdapter
from src.infrastructure.tasks.task_query_adapter import TaskQueryAdapter
from src.infrastructure.tasks.runtime_components import (
    CheckpointManager,
    TaskStateMachine,
    build_runtime_components,
    ensure_runtime_stores,
)
from src.infrastructure.tasks.event_publisher import TaskEventType
from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter


logger = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    """Execution result payload for API compatibility."""

    plan_id: str
    status: str
    steps_completed: int
    steps_total: int
    findings: List[Dict[str, Any]]
    checkpoint: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskRuntime:
    """Composes task application use cases and runtime adapters."""

    def __init__(
        self,
        redis_store: Optional[RedisTaskStore] = None,
        pg_store: Optional[PostgresTaskStore] = None,
        state_machine: Optional[TaskStateMachine] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        preference_service: Optional[PreferenceLearningPort] = None,
        risk_detector: Optional[RiskDetectorService] = None,
        orchestrator: Optional[TaskOrchestratorPort] = None,
        observer: Optional[TaskObserverPort] = None,
        workflow_planner: Optional[TaskPlannerPort] = None,
        tree_adapter: Optional[TaskExecutionTreeAdapter] = None,
        memory_service: Optional[MemoryOperationsPort] = None,
        register_trigger: Optional[Callable[[Task], Awaitable[None]]] = None,
        unregister_trigger: Optional[Callable[[str], Awaitable[None]]] = None,
        trigger_registry: Optional[Any] = None,
        inline_fast_path_precheck: bool = False,
    ) -> None:
        if trigger_registry is not None:
            if register_trigger is None:
                async def _register_with_registry(task: Task) -> None:
                    trigger_config = task.metadata.get("trigger") if task.metadata else None
                    if not trigger_config or not task.organization_id:
                        return
                    await trigger_registry.register_trigger(
                        task_id=task.id,
                        organization_id=task.organization_id,
                        trigger_config=trigger_config,
                    )

                register_trigger = _register_with_registry

            if unregister_trigger is None:
                async def _unregister_with_registry(task_id: str) -> None:
                    await trigger_registry.unregister_trigger(task_id)

                unregister_trigger = _unregister_with_registry

        self._redis_store = redis_store
        self._pg_store = pg_store
        self._state_machine = state_machine
        self._checkpoint_manager = checkpoint_manager
        self._preference_service = preference_service
        self._risk_detector = risk_detector
        self._orchestrator = orchestrator
        self._observer = observer
        self._workflow_planner = workflow_planner
        self._tree_adapter = tree_adapter
        self._memory_service = memory_service
        self._register_trigger = register_trigger
        self._unregister_trigger = unregister_trigger
        self._inline_fast_path_precheck = inline_fast_path_precheck

        self._planning_use_case: Optional[PlanTaskUseCase] = None
        self._execution_use_case: Optional[TaskExecutionUseCase] = None
        self._planning_intent_port: Optional[PlanningIntentPort] = None
        self._fast_path_planner_port: Optional[FastPathPlannerPort] = None
        self._automation_scheduler_port: Optional[AutomationSchedulerPort] = None
        self._plan_cancellation_port: Optional[PlanCancellationPort] = None
        self._planning_event_bus: Optional[PlanningEventBusPort] = None
        self._planning_store: Optional[TaskPlanningStorePort] = None
        self._task_query_port: Optional[TaskQueryPort] = None
        self._task_persistence_port: Optional[TaskPersistencePort] = None
        self._status_transition_port: Optional[TaskStatusTransitionPort] = None
        self._execution_tree_port: Optional[TaskExecutionTreePort] = None
        self._plan_store_port: Optional[TaskPlanStorePort] = None
        self._execution_event_bus: Optional[TaskExecutionEventBusPort] = None
        self._execution_event_stream: Optional[TaskExecutionEventStreamPort] = None
        self._scheduler_port: Optional[TaskSchedulerPort] = None
        self._conversation_port: Optional[TaskConversationPort] = None
        self._lifecycle_use_case: Optional[TaskLifecycleUseCase] = None
        self._create_task_with_steps_use_case: Optional[CreateTaskWithStepsUseCase] = None
        self._clone_task_for_trigger_use_case: Optional[CloneTaskForTriggerUseCase] = None

        self._active_executions: Dict[str, asyncio.Task] = {}
        self._active_planning: Dict[str, asyncio.Task] = {}
        self._initialized = False

    async def _register_task_trigger(self, task: Task) -> None:
        """Compatibility hook for registering triggers from setup use cases."""
        if not self._register_trigger:
            return
        try:
            await self._register_trigger(task)
        except Exception as exc:
            logger.warning("Failed to register task trigger", task_id=task.id, error=str(exc))

    async def _unregister_task_trigger(self, task_id: str) -> None:
        """Compatibility hook for unregistering triggers on cancellation."""
        if not self._unregister_trigger:
            return
        try:
            await self._unregister_trigger(task_id)
        except Exception as exc:
            logger.warning("Failed to unregister task trigger", task_id=task_id, error=str(exc))

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def initialize(self) -> None:
        """Initialize runtime dependencies and compose use cases."""
        if self._initialized:
            return

        stores = await ensure_runtime_stores(
            pg_store=self._pg_store,
            redis_store=self._redis_store,
        )
        self._pg_store = stores.pg_store
        self._redis_store = stores.redis_store

        if (
            not self._state_machine
            or not self._checkpoint_manager
            or not self._preference_service
            or not self._risk_detector
        ):
            components = build_runtime_components(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
            if not self._state_machine:
                self._state_machine = components.state_machine
                if self._state_machine:
                    logger.info("TaskStateMachine initialized (PG primary, Redis cache)")
            if not self._checkpoint_manager:
                self._checkpoint_manager = components.checkpoint_manager
            if not self._preference_service:
                self._preference_service = components.preference_service
            if not self._risk_detector:
                self._risk_detector = components.risk_detector

        if not self._memory_service:
            try:
                memory_database = self._pg_store.db if self._pg_store else None
                self._memory_service = build_memory_use_cases(memory_database)
                logger.info("MemoryUseCases initialized for prompt injection")
            except Exception as exc:
                logger.warning("Failed to initialize MemoryUseCases", error=str(exc))
                self._memory_service = None

        if not self._observer:
            observer_llm = OpenRouterClient()
            self._observer = TaskObserverAdapter(
                redis_store=self._redis_store,
                llm_client=observer_llm,
            )
            await self._observer.initialize()

        if not self._workflow_planner:
            self._workflow_planner = TaskPlannerAdapter()
            await self._workflow_planner.initialize()

        if not self._orchestrator:
            self._orchestrator = TaskOrchestratorAdapter(
                redis_store=self._redis_store,
                execution_mode="queue",
                memory_service=self._memory_service,
                observer=self._observer,
                planner=self._workflow_planner,
            )
            await self._orchestrator.initialize()

        if not self._tree_adapter:
            self._tree_adapter = TaskExecutionTreeAdapter()
            logger.info("TaskExecutionTreeAdapter initialized for durable execution")

        if not self._planning_intent_port:
            self._planning_intent_port = PlanningIntentAdapter()

        self._ensure_task_query_port()
        self._ensure_task_persistence_port()

        if not self._fast_path_planner_port:
            self._fast_path_planner_port = FastPathPlannerAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                persistence_port=self._task_persistence_port,
            )

        if not self._automation_scheduler_port:
            self._automation_scheduler_port = AutomationSchedulerAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )

        if not self._plan_cancellation_port:
            self._plan_cancellation_port = PlanCancellationAdapter()

        if not self._planning_event_bus:
            self._planning_event_bus = PlanningEventBusAdapter()

        if not self._planning_store:
            self._planning_store = TaskPlanningStoreAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                query_port=self._task_query_port,
                persistence_port=self._task_persistence_port,
            )

        if not self._status_transition_port:
            self._status_transition_port = TaskStatusTransitionAdapter(
                state_machine=self._state_machine,
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )

        if not self._execution_tree_port:
            self._execution_tree_port = self._tree_adapter

        self._ensure_planning_use_case()
        self._ensure_execution_use_case()
        self._ensure_task_setup_use_cases()
        self._ensure_lifecycle_use_case()

        self._initialized = True
        asyncio.create_task(self._recover_stuck_planning_tasks())

    async def _recover_stuck_planning_tasks(self) -> None:
        await asyncio.sleep(10)
        self._ensure_task_query_port()
        get_stuck_tasks = getattr(self._task_query_port, "get_stuck_planning_tasks", None)
        if not get_stuck_tasks:
            return
        try:
            stuck_tasks = await get_stuck_tasks(
                timeout_minutes=5
            )
            if stuck_tasks:
                logger.info("Found stuck planning tasks to recover", count=len(stuck_tasks))
            for task in stuck_tasks:
                try:
                    await self._status_transition_port.transition(task.id, TaskStatus.FAILED)
                    await self._planning_event_bus.planning_failed(
                        task.id, "Planning was interrupted. Please try again."
                    )
                except Exception as exc:
                    logger.warning("Failed to recover stuck task", task_id=task.id, error=str(exc))
        except Exception as exc:
            logger.warning("Failed to check for stuck planning tasks", error=str(exc))

    def _ensure_planning_use_case(self) -> None:
        if self._planning_use_case and self._planning_use_case.planner == self._workflow_planner:
            return

        if not self._redis_store:
            self._redis_store = RedisTaskStore()
        self._ensure_task_query_port()
        self._ensure_task_persistence_port()
        if not self._tree_adapter:
            self._tree_adapter = TaskExecutionTreeAdapter()
        if not self._planning_intent_port:
            self._planning_intent_port = PlanningIntentAdapter()
        if not self._fast_path_planner_port:
            self._fast_path_planner_port = FastPathPlannerAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                persistence_port=self._task_persistence_port,
            )
        if not self._automation_scheduler_port:
            self._automation_scheduler_port = AutomationSchedulerAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
        if not self._plan_cancellation_port:
            self._plan_cancellation_port = PlanCancellationAdapter()
        if not self._planning_event_bus:
            self._planning_event_bus = PlanningEventBusAdapter()
        if not self._planning_store:
            self._planning_store = TaskPlanningStoreAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                query_port=self._task_query_port,
                persistence_port=self._task_persistence_port,
            )
        if not self._status_transition_port:
            self._status_transition_port = TaskStatusTransitionAdapter(
                state_machine=self._state_machine,
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
        if not self._execution_tree_port:
            self._execution_tree_port = self._tree_adapter

        self._planning_use_case = PlanTaskUseCase(
            intent_port=self._planning_intent_port,
            fast_path_planner=self._fast_path_planner_port,
            automation_scheduler=self._automation_scheduler_port,
            cancellation_port=self._plan_cancellation_port,
            event_bus=self._planning_event_bus,
            task_store=self._planning_store,
            status_transition=self._status_transition_port,
            tree_port=self._execution_tree_port,
            planner=self._workflow_planner,
            risk_detector=self._risk_detector,
        )

    def _ensure_execution_use_case(self) -> None:
        if self._execution_use_case:
            return

        if not self._redis_store:
            self._redis_store = RedisTaskStore()
        if not self._plan_store_port:
            self._plan_store_port = TaskPlanStoreAdapter(self._redis_store)
        if not self._planning_store:
            self._ensure_task_query_port()
            self._ensure_task_persistence_port()
            self._planning_store = TaskPlanningStoreAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                query_port=self._task_query_port,
                persistence_port=self._task_persistence_port,
            )
        if not self._status_transition_port:
            self._status_transition_port = TaskStatusTransitionAdapter(
                state_machine=self._state_machine,
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
        if not self._execution_event_bus:
            self._execution_event_bus = TaskExecutionEventBusAdapter()
        if not self._scheduler_port:
            self._scheduler_port = TaskSchedulerAdapter()
        if not self._conversation_port and self._pg_store:
            self._conversation_port = TaskConversationAdapter(
                pg_store=self._pg_store,
                redis_store=self._redis_store,
                event_bus=self._execution_event_bus,
            )
        if not self._conversation_port:
            raise RuntimeError("TaskConversationPort is required for execution flows")

        self._execution_use_case = TaskExecutionUseCase(
            orchestrator=self._orchestrator,
            plan_store=self._plan_store_port,
            task_store=self._planning_store,
            status_transition=self._status_transition_port,
            scheduler=self._scheduler_port,
            event_bus=self._execution_event_bus,
            conversation_port=self._conversation_port,
            checkpoint_manager=self._checkpoint_manager,
            preference_service=self._preference_service,
        )

    def _ensure_task_query_port(self) -> None:
        if self._task_query_port:
            return
        if not self._redis_store:
            self._redis_store = RedisTaskStore()
        self._task_query_port = TaskQueryAdapter(
            pg_store=self._pg_store,
            redis_store=self._redis_store,
        )

    def _ensure_task_persistence_port(self) -> None:
        if self._task_persistence_port:
            return
        if not self._redis_store:
            self._redis_store = RedisTaskStore()
        self._task_persistence_port = TaskPersistenceAdapter(
            pg_store=self._pg_store,
            redis_store=self._redis_store,
        )

    def _ensure_task_setup_use_cases(self) -> None:
        if self._create_task_with_steps_use_case and self._clone_task_for_trigger_use_case:
            return
        self._ensure_task_persistence_port()
        if not self._execution_tree_port:
            if not self._tree_adapter:
                self._tree_adapter = TaskExecutionTreeAdapter()
            self._execution_tree_port = self._tree_adapter
        if not self._create_task_with_steps_use_case:
            self._create_task_with_steps_use_case = CreateTaskWithStepsUseCase(
                task_store=self._task_persistence_port,
                tree_port=self._execution_tree_port,
                risk_detector=self._risk_detector,
                register_trigger=self._register_task_trigger,
            )
        if not self._clone_task_for_trigger_use_case:
            self._clone_task_for_trigger_use_case = CloneTaskForTriggerUseCase(
                task_store=self._task_persistence_port,
                tree_port=self._execution_tree_port,
            )

    def _ensure_lifecycle_use_case(self) -> None:
        if self._lifecycle_use_case:
            return
        self._ensure_task_query_port()
        if not self._status_transition_port:
            self._status_transition_port = TaskStatusTransitionAdapter(
                state_machine=self._state_machine,
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
        if not self._plan_cancellation_port:
            self._plan_cancellation_port = PlanCancellationAdapter()
        self._lifecycle_use_case = TaskLifecycleUseCase(
            query_port=self._task_query_port,
            status_transition=self._status_transition_port,
            cancellation_port=self._plan_cancellation_port,
        )

    async def create_task(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_spec_matching: bool = False,
        auto_start: bool = True,
        prefer_fast_path: Optional[bool] = None,
    ) -> Task:
        await self._ensure_initialized()
        self._ensure_task_persistence_port()
        should_try_fast_path = (
            self._inline_fast_path_precheck
            if prefer_fast_path is None
            else prefer_fast_path
        )

        if should_try_fast_path and organization_id:
            try:
                intent_info = await self.detect_scheduling_intent(goal)
                fast_path_task = await self.try_fast_path(
                    user_id=user_id,
                    organization_id=organization_id,
                    goal=goal,
                    intent_info=intent_info,
                    metadata=metadata,
                )
                if fast_path_task:
                    return fast_path_task
            except Exception as exc:
                logger.warning("Fast path pre-check failed; falling back to planning", error=str(exc))

        plan = Task(
            goal=goal,
            user_id=user_id,
            organization_id=organization_id,
            steps=[],
            constraints=constraints or {},
            metadata=metadata.copy() if metadata else {},
        )

        await self._task_persistence_port.create_task(plan)

        bg_task = asyncio.create_task(
            self._plan_task_async(
                task_id=plan.id,
                user_id=user_id,
                organization_id=organization_id or "",
                goal=goal,
                constraints=constraints,
                metadata=metadata,
                skip_spec_matching=skip_spec_matching,
                auto_start=auto_start,
            )
        )
        self._active_planning[plan.id] = bg_task
        bg_task.add_done_callback(lambda _: self._active_planning.pop(plan.id, None))
        return plan

    async def _plan_task_async(
        self,
        task_id: str,
        user_id: str,
        organization_id: str,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_spec_matching: bool = False,
        auto_start: bool = True,
    ) -> None:
        self._ensure_planning_use_case()
        status = await self._planning_use_case.plan_task(
            task_id=task_id,
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            constraints=constraints,
            metadata=metadata,
            skip_spec_matching=skip_spec_matching,
        )
        if auto_start and status == TaskStatus.READY:
            await self._auto_start_task(task_id, user_id)

    async def _auto_start_task(self, task_id: str, user_id: str) -> None:
        """Auto-start task execution after planning completes."""
        try:
            result = await self.start_task(task_id, user_id)
            if result.get("status") in ("started", "checkpoint"):
                logger.info("Plan auto-started", plan_id=task_id)
            elif result.get("error"):
                logger.warning("Auto-start failed", plan_id=task_id, error=result.get("error"))
        except Exception as exc:
            logger.warning("Auto-start exception", plan_id=task_id, error=str(exc))

    async def check_planning_cancelled(self, task_id: str) -> bool:
        self._ensure_planning_use_case()
        return await self._plan_cancellation_port.is_cancelled(task_id)

    async def detect_scheduling_intent(self, goal: str) -> Optional[Dict[str, Any]]:
        self._ensure_planning_use_case()
        intent = await self._planning_intent_port.extract_intent(goal)
        return intent.to_dict() if intent else None

    async def try_fast_path(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: Optional[Dict[str, Any] | PlanningIntent],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        self._ensure_planning_use_case()
        parsed_intent = (
            intent_info
            if isinstance(intent_info, PlanningIntent)
            else PlanningIntent.from_intent_dict(intent_info)
        )
        return await self._fast_path_planner_port.try_fast_path(
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            intent_info=parsed_intent,
            metadata=metadata,
        )

    async def execute_fast_path_query(
        self,
        organization_id: str,
        data_query: DataQuery,
    ) -> FastPathResult:
        self._ensure_planning_use_case()
        return await self._fast_path_planner_port.execute_query(
            organization_id=organization_id,
            data_query=data_query,
        )

    async def create_fast_path_task(
        self,
        user_id: str,
        organization_id: str,
        goal: str,
        intent_info: Dict[str, Any] | PlanningIntent,
        fast_result: FastPathResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        self._ensure_planning_use_case()
        parsed_intent = (
            intent_info
            if isinstance(intent_info, PlanningIntent)
            else PlanningIntent.from_intent_dict(intent_info)
        )
        if parsed_intent is None:
            raise ValueError("intent_info is required for fast path task creation")
        return await self._fast_path_planner_port.create_fast_path_task(
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            intent_info=parsed_intent,
            fast_result=fast_result,
            metadata=metadata,
        )

    async def create_automation_for_task(
        self,
        task_id: str,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        cron: Optional[str] = None,
        timezone: str = "UTC",
        execute_at: Optional[datetime] = None,
    ) -> None:
        self._ensure_planning_use_case()
        schedule = ScheduleSpec(
            cron=cron,
            timezone=timezone,
            execute_at=execute_at,
        )
        await self._automation_scheduler_port.create_automation_for_task(
            task_id=task_id,
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            schedule=schedule,
        )

    async def create_task_with_steps(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        steps: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        await self._ensure_initialized()
        self._ensure_task_setup_use_cases()
        return await self._create_task_with_steps_use_case.execute(
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            steps=steps,
            constraints=constraints,
            metadata=metadata,
        )

    async def clone_task_for_trigger(
        self,
        template_task_id: str,
        trigger_event: Dict[str, Any],
    ) -> Task:
        await self._ensure_initialized()
        self._ensure_task_setup_use_cases()
        return await self._clone_task_for_trigger_use_case.execute(
            template_task_id=template_task_id,
            trigger_event=trigger_event,
        )

    async def get_task(self, task_id: str) -> Optional[Task]:
        await self._ensure_initialized()
        self._ensure_task_query_port()
        return await self._task_query_port.get_task(task_id)

    async def list_tasks(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        await self._ensure_initialized()
        self._ensure_task_query_port()
        return await self._task_query_port.get_tasks_by_user(
            user_id=user_id,
            status=status,
            limit=limit,
        )

    async def execute_task(
        self,
        task_id: str,
        user_id: str,
        run_to_completion: bool = False,
    ) -> ExecutionResult:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        payload = await self._execution_use_case.execute_plan(
            plan_id=task_id,
            user_id=user_id,
            run_to_completion=run_to_completion,
        )
        return ExecutionResult(
            plan_id=payload["plan_id"],
            status=payload["status"],
            steps_completed=payload["steps_completed"],
            steps_total=payload["steps_total"],
            findings=payload.get("findings", []),
            checkpoint=payload.get("checkpoint"),
            error=payload.get("error"),
        )

    async def approve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> CheckpointState:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.approve_checkpoint(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            feedback=feedback,
            learn_preference=learn_preference,
        )

    async def reject_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str,
        learn_preference: bool = True,
    ) -> CheckpointState:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.reject_checkpoint(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
            learn_preference=learn_preference,
        )

    async def approve_replan(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.approve_replan(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            feedback=feedback,
        )

    async def reject_replan(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.reject_replan(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
        )

    async def transition_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        additional_updates: Optional[Dict[str, Any]] = None,
    ) -> Task:
        await self._ensure_initialized()
        if not self._status_transition_port:
            self._status_transition_port = TaskStatusTransitionAdapter(
                state_machine=self._state_machine,
                pg_store=self._pg_store,
                redis_store=self._redis_store,
            )
        return await self._status_transition_port.transition(
            task_id=task_id,
            new_status=new_status,
            additional_updates=additional_updates,
        )

    async def get_task_for_execution(self, task_id: str) -> Optional[Task]:
        await self._ensure_initialized()
        self._ensure_task_query_port()
        return await self._task_query_port.get_task_for_execution(task_id)

    async def start_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.start_plan_async(
            plan_id=task_id,
            user_id=user_id,
        )

    async def pause_task(self, task_id: str, user_id: str) -> Task:
        await self._ensure_initialized()
        self._ensure_lifecycle_use_case()
        task = await self._lifecycle_use_case.pause_plan(task_id, user_id)
        if task_id in self._active_executions:
            self._active_executions[task_id].cancel()
            del self._active_executions[task_id]
        return task

    async def cancel_task(self, task_id: str, user_id: str) -> Task:
        await self._ensure_initialized()
        self._ensure_lifecycle_use_case()
        decision = await self._lifecycle_use_case.cancel_plan(task_id, user_id)

        if decision.cancelled_while_planning and task_id in self._active_planning:
            self._active_planning[task_id].cancel()
            del self._active_planning[task_id]

        if task_id in self._active_executions:
            self._active_executions[task_id].cancel()
            del self._active_executions[task_id]

        await self._unregister_task_trigger(task_id)
        return decision.task

    # ------------------------------------------------------------------
    # Compatibility aliases used by legacy tests and integration helpers
    # ------------------------------------------------------------------

    _check_planning_cancelled = check_planning_cancelled
    _detect_scheduling_intent = detect_scheduling_intent
    _try_fast_path = try_fast_path
    _execute_fast_path_query = execute_fast_path_query
    _create_fast_path_task = create_fast_path_task
    _create_automation_for_task = create_automation_for_task
    _transition_status = transition_status
    _get_task_for_execution = get_task_for_execution

    async def execute_plan(
        self,
        plan_id: str,
        user_id: str,
        run_to_completion: bool = False,
    ) -> ExecutionResult:
        return await self.execute_task(
            task_id=plan_id,
            user_id=user_id,
            run_to_completion=run_to_completion,
        )

    async def get_user_plans(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        return await self.list_tasks(user_id=user_id, status=status, limit=limit)

    async def pause_plan(self, plan_id: str, user_id: str) -> Task:
        return await self.pause_task(plan_id, user_id)

    async def cancel_plan(self, plan_id: str, user_id: str) -> Task:
        return await self.cancel_task(plan_id, user_id)

    async def start_plan_async(self, plan_id: str, user_id: str) -> Dict[str, Any]:
        return await self.start_task(plan_id, user_id)

    async def observe_plan(self, plan_id: str) -> ObservationReport:
        await self._ensure_initialized()
        return await self._observer.observe(plan_id)

    async def link_task_to_conversation(self, task_id: str, conversation_id: str) -> None:
        await self.link_conversation(task_id, conversation_id)

    async def get_pending_checkpoints(self, user_id: str) -> List[CheckpointState]:
        return await self.list_pending_checkpoints(user_id)

    async def get_pending_checkpoints_for_task(self, plan_id: str) -> List[CheckpointState]:
        return await self.list_pending_checkpoints_for_task(plan_id)

    async def observe_execution(
        self,
        task_id: str,
        user_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_initialized()
        self._ensure_task_query_port()
        terminal_events = {
            TaskEventType.TASK_COMPLETED.value,
            TaskEventType.TASK_FAILED.value,
            TaskEventType.TASK_CANCELLED.value,
        }

        plan = await self._task_query_port.get_task_for_execution(task_id)
        if not plan:
            yield {"type": "error", "error": "Plan not found"}
            return
        if plan.user_id != user_id:
            yield {"type": "error", "error": "Access denied"}
            return

        yield {
            "type": "connected",
            "plan_id": task_id,
            "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
            "steps_total": len(plan.steps) if plan.steps else 0,
            "steps_completed": sum(
                1
                for step in plan.steps
                if hasattr(step.status, "value") and step.status.value == "done"
            )
            if plan.steps
            else 0,
        }

        try:
            if not self._execution_event_stream:
                self._execution_event_stream = TaskExecutionEventStreamAdapter()
            recent_events = await self._execution_event_stream.get_recent_events(task_id, count=100)
            for event in recent_events:
                yield event
        except Exception as exc:
            logger.warning("Failed to replay events from stream", task_id=task_id, error=str(exc))

        if plan.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED):
            yield {
                "type": "already_terminal",
                "plan_id": task_id,
                "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
            }
            return

        if not self._execution_event_stream:
            self._execution_event_stream = TaskExecutionEventStreamAdapter()
        subscription = await self._execution_event_stream.subscribe(task_id)

        try:
            heartbeat_interval = 30
            last_heartbeat = asyncio.get_event_loop().time()
            while True:
                event = await subscription.get_message(timeout=1.0)
                if event:
                    yield event
                    if event.get("type", "") in terminal_events:
                        return
                    continue

                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield {"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()}
                    last_heartbeat = now

                plan = await self._task_query_port.get_task_for_execution(task_id)
                if plan and plan.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    yield {
                        "type": "plan_status_update",
                        "plan_id": task_id,
                        "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
                    }
                    return
        finally:
            await subscription.close()

    async def link_conversation(self, task_id: str, conversation_id: str) -> None:
        await self._ensure_initialized()
        await self._conversation_port.link_task_to_conversation(
            task_id=task_id,
            conversation_id=conversation_id,
        )

    async def set_parent_task(self, task_id: str, parent_task_id: str) -> None:
        await self._ensure_initialized()
        self._ensure_task_persistence_port()
        await self._task_persistence_port.set_parent_task(task_id, parent_task_id)

    async def clone_and_execute_from_automation(
        self,
        automation_id: str,
        template_task_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> Task:
        await self._ensure_initialized()
        self._ensure_task_persistence_port()
        template = await self.get_task(template_task_id)
        if not template:
            raise ValueError(f"Template task {template_task_id} not found")
        if not template.steps:
            raise ValueError(f"Template task {template_task_id} has no steps")

        cloned_steps: List[Dict[str, Any]] = []
        for step in template.steps:
            cloned_steps.append(
                {
                    "id": step.id,
                    "name": step.name,
                    "description": step.description or "",
                    "agent_type": step.agent_type,
                    "domain": step.domain,
                    "inputs": dict(step.inputs) if step.inputs else {},
                    "dependencies": list(step.dependencies) if step.dependencies else [],
                    "checkpoint_required": step.checkpoint_required,
                }
            )

        new_task = await self.create_task_with_steps(
            user_id=user_id,
            organization_id=organization_id or template.organization_id or "",
            goal=template.goal,
            steps=cloned_steps,
            constraints=template.constraints,
        )

        await self._task_persistence_port.update_task(
            new_task.id,
            {
                "metadata": {
                    "automation_id": automation_id,
                    "template_task_id": template_task_id,
                    "source": "schedule",
                },
                "source": "schedule",
            },
        )

        await self.start_task(new_task.id, user_id)
        return new_task

    async def update_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        await self._ensure_initialized()
        self._ensure_task_persistence_port()
        await self._task_persistence_port.update_task_metadata(task_id, metadata)

    async def list_pending_checkpoints(self, user_id: str) -> List[CheckpointState]:
        await self._ensure_initialized()
        return await self._checkpoint_manager.get_pending_checkpoints(user_id=user_id)

    async def list_pending_checkpoints_for_task(self, task_id: str) -> List[CheckpointState]:
        await self._ensure_initialized()
        return await self._checkpoint_manager.get_pending_checkpoints(plan_id=task_id)

    async def get_checkpoint(self, task_id: str, step_id: str) -> Optional[CheckpointState]:
        await self._ensure_initialized()
        pg_store = self._checkpoint_manager._get_pg_checkpoint_store()
        return await pg_store.get_checkpoint(task_id, step_id)

    async def resolve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        response: CheckpointResponse,
        learn_preference: bool = True,
    ) -> CheckpointState:
        await self._ensure_initialized()
        self._ensure_execution_use_case()
        return await self._execution_use_case.resolve_checkpoint(
            plan_id=task_id,
            step_id=step_id,
            user_id=user_id,
            response=response,
            learn_preference=learn_preference,
        )

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        await self._ensure_initialized()
        return await self._preference_service.get_preference_stats(user_id)

    async def _get_preference_store(self) -> Any:
        """Get the preference store from the configured learning service."""
        await self._ensure_initialized()
        return await self._preference_service._get_store()

    async def list_preferences(self, user_id: str) -> List[Any]:
        """List learned user preferences."""
        store = await self._get_preference_store()
        return await store.get_user_preferences(user_id)

    async def get_preference(self, preference_id: str) -> Optional[Any]:
        """Get one learned preference by ID."""
        store = await self._get_preference_store()
        return await store.get_preference(preference_id)

    async def delete_preference(self, preference_id: str) -> None:
        """Delete one learned preference by ID."""
        store = await self._get_preference_store()
        await store.delete_preference(preference_id)

    async def cleanup(self) -> None:
        for task in self._active_executions.values():
            task.cancel()
        self._active_executions.clear()

        for task in self._active_planning.values():
            task.cancel()
        self._active_planning.clear()

        if self._orchestrator:
            await self._orchestrator.cleanup()
        if self._observer:
            await self._observer.cleanup()
        if self._checkpoint_manager:
            await self._checkpoint_manager.cleanup()
        if self._preference_service:
            await self._preference_service.cleanup()
        if self._redis_store:
            await self._redis_store._disconnect()

        self._initialized = False
