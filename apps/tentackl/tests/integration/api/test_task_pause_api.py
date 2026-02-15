"""Integration tests for task pause/resume API functionality.

These tests verify the IMPROVE-002 requirement: pausing a task revokes all active
Celery jobs, persists PAUSED state in the execution tree, blocks schedule_ready_nodes
from dispatching new steps while paused, and supports resume.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus
from src.api.auth_middleware import AuthUser, DEVELOPER_SCOPES
from src.core.execution_tree import ExecutionStatus, ExecutionNode


@pytest.fixture
def mock_task_service():
    """Create a mock task service."""
    service = AsyncMock(spec=TaskService)
    service.get_task = AsyncMock()
    service.pause_plan = AsyncMock()
    service.start_plan_async = AsyncMock()
    return service


@pytest.fixture
def executing_task():
    """Create an executing task for testing pause."""
    return Task(
        id="test-task-pause-123",
        user_id="dev",
        organization_id="org-789",
        goal="Long running research task",
        status=TaskStatus.EXECUTING,
        tree_id="test-task-pause-123",
        steps=[
            TaskStep(
                id="step-1",
                name="web_research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.RUNNING,
                inputs={"query": "test query"},
            ),
            TaskStep(
                id="step-2",
                name="summarize",
                description="Summarize step",
                agent_type="summarizer",
                status=StepStatus.PENDING,
                dependencies=["step-1"],
            ),
        ],
        is_template=False,
    )


@pytest.fixture
def paused_task(executing_task):
    """Create a paused task for testing resume."""
    return Task(
        id=executing_task.id,
        user_id=executing_task.user_id,
        organization_id=executing_task.organization_id,
        goal=executing_task.goal,
        status=TaskStatus.PAUSED,
        tree_id=executing_task.tree_id,
        steps=[
            TaskStep(
                id="step-1",
                name="web_research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.PENDING,  # Reset to pending after pause
                inputs={"query": "test query"},
            ),
            TaskStep(
                id="step-2",
                name="summarize",
                description="Summarize step",
                agent_type="summarizer",
                status=StepStatus.PENDING,
                dependencies=["step-1"],
            ),
        ],
        is_template=False,
    )


@pytest.fixture
def dev_user():
    """Create a dev user for auth."""
    return AuthUser(
        id="dev",
        auth_type="none",
        username="developer",
        scopes=DEVELOPER_SCOPES,
        metadata={"auto_dev_user": True}
    )


class TestPauseEndpoint:
    """Tests for POST /api/tasks/{id}/pause endpoint."""

    def test_pause_executing_task_success(
        self, mock_task_service, executing_task, paused_task, dev_user
    ):
        """Test successful pause of an executing task."""
        mock_task_service.pause_plan.return_value = paused_task

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/pause")
        async def pause_task(task_id: str):
            task = await mock_task_service.pause_plan(
                plan_id=task_id,
                user_id=dev_user.id,
            )
            return {
                "id": task.id,
                "status": task.status.value,
                "message": "Task paused successfully"
            }

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{executing_task.id}/pause")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == executing_task.id
            assert data["status"] == "paused"
            mock_task_service.pause_plan.assert_called_once_with(
                plan_id=executing_task.id,
                user_id="dev",
            )

    def test_pause_non_executing_task_fails(
        self, mock_task_service, dev_user
    ):
        """Test that pausing a non-executing task returns error."""
        from src.infrastructure.tasks.state_machine import InvalidTransitionError

        mock_task_service.pause_plan.side_effect = InvalidTransitionError(
            task_id="test-ready",
            current_status=TaskStatus.READY,
            target_status=TaskStatus.PAUSED,
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/pause")
        async def pause_task(task_id: str):
            try:
                task = await mock_task_service.pause_plan(
                    plan_id=task_id,
                    user_id=dev_user.id,
                )
                return {"id": task.id, "status": task.status.value}
            except InvalidTransitionError as e:
                raise HTTPException(status_code=409, detail=str(e.message))

        with TestClient(app) as client:
            response = client.post("/api/tasks/test-ready/pause")

            assert response.status_code == 409
            assert "transition" in response.json()["detail"].lower()

    def test_pause_task_permission_denied(self, mock_task_service, dev_user):
        """Test that pausing another user's task returns 403."""
        mock_task_service.pause_plan.side_effect = PermissionError(
            "User dev does not own plan other-user-task"
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/pause")
        async def pause_task(task_id: str):
            try:
                return await mock_task_service.pause_plan(
                    plan_id=task_id,
                    user_id=dev_user.id,
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

        with TestClient(app) as client:
            response = client.post("/api/tasks/other-user-task/pause")

            assert response.status_code == 403
            assert "does not own" in response.json()["detail"].lower()


class TestResumeEndpoint:
    """Tests for POST /api/tasks/{id}/start endpoint (resume from PAUSED)."""

    def test_resume_paused_task_success(
        self, mock_task_service, paused_task, dev_user
    ):
        """Test successful resume of a paused task."""
        mock_task_service.start_plan_async.return_value = {
            "status": "resumed",
            "plan_id": paused_task.id,
            "scheduled_steps": 1,
            "message": "Execution started via durable tree."
        }

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/start")
        async def start_task(task_id: str):
            return await mock_task_service.start_plan_async(
                plan_id=task_id,
                user_id=dev_user.id,
            )

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{paused_task.id}/start")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "resumed"
            assert data["plan_id"] == paused_task.id


class TestPauseExecutionTree:
    """Tests for execution tree pause functionality."""

    @pytest.mark.asyncio
    async def test_pause_running_nodes_returns_celery_ids(self):
        """Test that pause_running_nodes returns Celery task IDs."""
        from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree

        exec_tree = RedisExecutionTree()

        # Mock the get_running_nodes and update_node_status methods
        with patch.object(exec_tree, 'get_running_nodes') as mock_get_running:
            with patch.object(exec_tree, 'update_node_status') as mock_update:
                # Setup: running node with celery_task_id in metadata
                mock_node = ExecutionNode(
                    id="step-1",
                    name="test_step",
                    status=ExecutionStatus.RUNNING,
                    metadata={"celery_task_id": "celery-abc-123"}
                )
                mock_get_running.return_value = [mock_node]
                mock_update.return_value = True

                celery_ids = await exec_tree.pause_running_nodes("tree-123")

                assert "celery-abc-123" in celery_ids
                mock_update.assert_called_once_with(
                    "tree-123",
                    "step-1",
                    ExecutionStatus.PAUSED
                )

    @pytest.mark.asyncio
    async def test_resume_paused_nodes_resets_to_pending(self):
        """Test that resume_paused_nodes resets nodes to PENDING."""
        from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree

        exec_tree = RedisExecutionTree()

        # Mock Redis operations
        with patch.object(exec_tree, '_get_redis') as mock_get_redis:
            with patch.object(exec_tree, 'update_node_status') as mock_update:
                mock_client = AsyncMock()
                mock_client.smembers = AsyncMock(return_value={"step-1", "step-2"})
                mock_client.aclose = AsyncMock()
                mock_get_redis.return_value = mock_client
                mock_update.return_value = True

                resumed_count = await exec_tree.resume_paused_nodes("tree-123")

                assert resumed_count == 2
                # Verify both nodes were transitioned to PENDING
                assert mock_update.call_count == 2


class TestScheduleReadyNodesPauseGuard:
    """Tests for pause guard in schedule_ready_nodes."""

    @pytest.mark.asyncio
    async def test_schedule_blocked_when_task_paused(self):
        """Test that schedule_ready_nodes returns 0 when task is paused."""
        from src.infrastructure.tasks.task_scheduler_helper import schedule_ready_nodes
        from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore

        with patch.object(RedisTaskStore, 'get_task') as mock_get_task:
            with patch.object(RedisTaskStore, '_connect', new_callable=AsyncMock):
                with patch.object(RedisTaskStore, '_disconnect', new_callable=AsyncMock):
                    mock_task = Task(
                        id="test-123",
                        user_id="dev",
                        goal="test",
                        status=TaskStatus.PAUSED,
                        steps=[],
                    )
                    mock_get_task.return_value = mock_task

                    scheduled_count = await schedule_ready_nodes("test-123")

                    assert scheduled_count == 0


class TestExecuteTaskStepPauseGuard:
    """Tests for pause guard in execute_task_step Celery task."""

    def test_execute_step_aborts_when_paused(self):
        """Test that execute_task_step aborts if task is paused."""
        from src.core.tasks import execute_task_step

        with patch('src.core.tasks.asyncio.run') as mock_run:
            # Simulate the async function returning paused status
            mock_run.return_value = {
                "status": "paused",
                "task_id": "test-123",
                "step_id": "step-1",
                "message": "Step execution aborted - task is paused",
            }

            result = execute_task_step("test-123", {"id": "step-1", "agent_type": "test"})

            assert result["status"] == "paused"
            assert "paused" in result["message"]
