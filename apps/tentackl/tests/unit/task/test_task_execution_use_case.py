"""Unit tests for TaskExecutionUseCase checkpoint resolution behavior."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.tasks.execute_task_use_case import TaskExecutionUseCase
from src.domain.checkpoints import CheckpointDecision, CheckpointResponse, CheckpointState


def _build_use_case() -> TaskExecutionUseCase:
    orchestrator = AsyncMock()
    plan_store = AsyncMock()
    task_store = AsyncMock()
    status_transition = AsyncMock()
    scheduler = AsyncMock()
    scheduler.schedule_ready_nodes = AsyncMock(return_value=1)
    event_bus = AsyncMock()
    conversation_port = AsyncMock()
    checkpoint_manager = AsyncMock()

    return TaskExecutionUseCase(
        orchestrator=orchestrator,
        plan_store=plan_store,
        task_store=task_store,
        status_transition=status_transition,
        scheduler=scheduler,
        event_bus=event_bus,
        conversation_port=conversation_port,
        checkpoint_manager=checkpoint_manager,
        preference_service=None,
    )


def _checkpoint_state() -> CheckpointState:
    return CheckpointState(
        plan_id="task-1",
        step_id="step-1",
        checkpoint_name="approval",
        description="Approval needed",
        decision=CheckpointDecision.APPROVED,
        preview_data={},
        created_at=datetime.utcnow(),
    )


def _plan(user_id: str = "user-1", is_replan: bool = False) -> Mock:
    plan = Mock()
    plan.user_id = user_id
    plan.tree_id = "tree-1"
    step = Mock()
    step.inputs = {"_replan_context": {"reason": "x"}} if is_replan else {}
    plan.get_step_by_id = Mock(return_value=step)
    return plan


class TestResolveCheckpointResume:
    @pytest.mark.asyncio
    async def test_approved_resolution_schedules_ready_nodes(self):
        use_case = _build_use_case()
        plan = _plan()
        use_case.task_store.get_task = AsyncMock(side_effect=[plan, plan])
        use_case.checkpoint_manager.resolve_checkpoint = AsyncMock(return_value=_checkpoint_state())
        response = CheckpointResponse(decision=CheckpointDecision.APPROVED)

        await use_case.resolve_checkpoint(
            plan_id="task-1",
            step_id="step-1",
            user_id="user-1",
            response=response,
            learn_preference=True,
        )

        use_case.scheduler.schedule_ready_nodes.assert_awaited_once_with("task-1")
        use_case.conversation_port.add_checkpoint_resolution_message.assert_awaited_once_with(
            task_id="task-1",
            approved=True,
        )
        use_case.orchestrator.execute_cycle.assert_not_called()
        use_case.orchestrator.execute_replan.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_resolution_falls_back_to_orchestrator_when_scheduler_fails(self):
        use_case = _build_use_case()
        plan = _plan()
        use_case.task_store.get_task = AsyncMock(side_effect=[plan, plan])
        use_case.checkpoint_manager.resolve_checkpoint = AsyncMock(return_value=_checkpoint_state())
        use_case.scheduler.schedule_ready_nodes.side_effect = RuntimeError("boom")
        response = CheckpointResponse(decision=CheckpointDecision.APPROVED)

        await use_case.resolve_checkpoint(
            plan_id="task-1",
            step_id="step-1",
            user_id="user-1",
            response=response,
            learn_preference=True,
        )

        use_case.orchestrator.execute_cycle.assert_awaited_once_with("task-1")

    @pytest.mark.asyncio
    async def test_rejected_resolution_adds_rejection_message(self):
        use_case = _build_use_case()
        plan = _plan()
        use_case.task_store.get_task = AsyncMock(return_value=plan)
        use_case.checkpoint_manager.resolve_checkpoint = AsyncMock(return_value=_checkpoint_state())
        response = CheckpointResponse(
            decision=CheckpointDecision.REJECTED,
            feedback="Need changes",
        )

        await use_case.resolve_checkpoint(
            plan_id="task-1",
            step_id="step-1",
            user_id="user-1",
            response=response,
            learn_preference=True,
        )

        use_case.scheduler.schedule_ready_nodes.assert_not_called()
        use_case.conversation_port.add_checkpoint_resolution_message.assert_awaited_once_with(
            task_id="task-1",
            approved=False,
            reason="Need changes",
        )
