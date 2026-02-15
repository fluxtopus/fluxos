"""Unit tests for task checkpoint router endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.api.auth_middleware import AuthUser
from src.api.routers.tasks import (
    ApproveCheckpointRequest,
    RejectCheckpointRequest,
    approve_checkpoint,
    reject_checkpoint,
)
from src.domain.checkpoints import CheckpointDecision, CheckpointState


@pytest.fixture
def mock_user() -> AuthUser:
    return AuthUser(
        id="user-123",
        auth_type="bearer",
        username="test-user",
        metadata={"organization_id": "org-1"},
    )


def _approved_checkpoint() -> CheckpointState:
    return CheckpointState(
        plan_id="task-1",
        step_id="step-1",
        checkpoint_name="approval",
        description="Approve",
        decision=CheckpointDecision.APPROVED,
        preview_data={},
        created_at=datetime.utcnow(),
    )


class TestTaskCheckpointRoutes:
    @pytest.mark.asyncio
    async def test_approve_endpoint_uses_approve_checkpoint_use_case(self, mock_user: AuthUser):
        use_cases = MagicMock()
        use_cases.approve_checkpoint = AsyncMock(return_value=_approved_checkpoint())
        use_cases.resolve_checkpoint = AsyncMock()

        response = await approve_checkpoint(
            task_id="task-1",
            step_id="step-1",
            request=ApproveCheckpointRequest(feedback="looks good", learn_preference=True),
            user=mock_user,
            use_cases=use_cases,
        )

        assert response.task_id == "task-1"
        assert response.step_id == "step-1"
        use_cases.approve_checkpoint.assert_awaited_once_with(
            task_id="task-1",
            step_id="step-1",
            user_id="user-123",
            feedback="looks good",
            learn_preference=True,
        )
        use_cases.resolve_checkpoint.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_endpoint_uses_reject_checkpoint_use_case(self, mock_user: AuthUser):
        use_cases = MagicMock()
        use_cases.reject_checkpoint = AsyncMock(return_value=_approved_checkpoint())
        use_cases.resolve_checkpoint = AsyncMock()

        response = await reject_checkpoint(
            task_id="task-1",
            step_id="step-1",
            request=RejectCheckpointRequest(reason="Needs edits", learn_preference=False),
            user=mock_user,
            use_cases=use_cases,
        )

        assert response.task_id == "task-1"
        assert response.step_id == "step-1"
        use_cases.reject_checkpoint.assert_awaited_once_with(
            task_id="task-1",
            step_id="step-1",
            user_id="user-123",
            reason="Needs edits",
            learn_preference=False,
        )
        use_cases.resolve_checkpoint.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_endpoint_maps_permission_error_to_403(self, mock_user: AuthUser):
        use_cases = MagicMock()
        use_cases.approve_checkpoint = AsyncMock(side_effect=PermissionError("forbidden"))

        with pytest.raises(HTTPException) as exc:
            await approve_checkpoint(
                task_id="task-1",
                step_id="step-1",
                request=ApproveCheckpointRequest(),
                user=mock_user,
                use_cases=use_cases,
            )

        assert exc.value.status_code == 403
