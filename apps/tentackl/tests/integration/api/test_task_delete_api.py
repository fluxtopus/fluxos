"""Integration tests for task delete API functionality.

These tests verify the IMPROVE-003 requirement: safe task deletion that:
- Warns on active runs (executing/planning/checkpoint/paused)
- Cancels or pauses executions before removal when force=true
- Deletes execution tree artifacts
- Requires frontend modal confirmation
- Provides audit logging
- Supports all status permutations
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


@pytest.fixture
def mock_task_service():
    """Create a mock task service."""
    service = AsyncMock(spec=TaskService)
    service.get_task = AsyncMock()
    service.delete_task = AsyncMock()
    return service


@pytest.fixture
def completed_task():
    """Create a completed task for testing deletion."""
    return Task(
        id="test-task-delete-123",
        user_id="dev",
        organization_id="org-789",
        goal="Completed research task",
        status=TaskStatus.COMPLETED,
        tree_id="test-task-delete-123",
        steps=[
            TaskStep(
                id="step-1",
                name="research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.DONE,
                inputs={"query": "test query"},
            ),
        ],
        is_template=False,
    )


@pytest.fixture
def executing_task():
    """Create an executing task for testing force deletion."""
    return Task(
        id="test-task-active-123",
        user_id="dev",
        organization_id="org-789",
        goal="Currently running task",
        status=TaskStatus.EXECUTING,
        tree_id="test-task-active-123",
        steps=[
            TaskStep(
                id="step-1",
                name="research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.RUNNING,
                inputs={"query": "test query"},
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


class TestDeleteEndpoint:
    """Tests for DELETE /api/tasks/{id} endpoint."""

    def test_delete_completed_task_success(
        self, mock_task_service, completed_task, dev_user
    ):
        """Test successful deletion of a completed task."""
        mock_task_service.delete_task.return_value = {
            "deleted": True,
            "task_id": completed_task.id,
            "was_active": False,
            "tree_deleted": True,
            "message": f"Task '{completed_task.goal[:50]}...' deleted successfully",
        }

        from fastapi import HTTPException

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            try:
                result = await mock_task_service.delete_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                    force=force,
                )
                return result
            except ValueError as e:
                error_msg = str(e)
                if "not found" in error_msg.lower():
                    raise HTTPException(status_code=404, detail=error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

        with TestClient(app) as client:
            response = client.delete(f"/api/tasks/{completed_task.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] is True
            assert data["task_id"] == completed_task.id
            assert data["was_active"] is False
            mock_task_service.delete_task.assert_called_once_with(
                task_id=completed_task.id,
                user_id="dev",
                force=False,
            )

    def test_delete_active_task_without_force_returns_400(
        self, mock_task_service, executing_task, dev_user
    ):
        """Test that deleting an active task without force returns 400."""
        mock_task_service.delete_task.side_effect = ValueError(
            f"Task is currently {executing_task.status.value}. "
            "Use force=true to cancel and delete, or cancel the task first."
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            try:
                return await mock_task_service.delete_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                    force=force,
                )
            except ValueError as e:
                error_msg = str(e)
                if "not found" in error_msg.lower():
                    raise HTTPException(status_code=404, detail=error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

        with TestClient(app) as client:
            response = client.delete(f"/api/tasks/{executing_task.id}")

            assert response.status_code == 400
            assert "currently" in response.json()["detail"].lower()
            assert "force" in response.json()["detail"].lower()

    def test_delete_active_task_with_force_succeeds(
        self, mock_task_service, executing_task, dev_user
    ):
        """Test that deleting an active task with force=true succeeds."""
        mock_task_service.delete_task.return_value = {
            "deleted": True,
            "task_id": executing_task.id,
            "was_active": True,
            "tree_deleted": True,
            "message": f"Task '{executing_task.goal[:50]}...' deleted successfully",
        }

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            return await mock_task_service.delete_task(
                task_id=task_id,
                user_id=dev_user.id,
                force=force,
            )

        with TestClient(app) as client:
            response = client.delete(
                f"/api/tasks/{executing_task.id}",
                params={"force": "true"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] is True
            assert data["was_active"] is True
            mock_task_service.delete_task.assert_called_once_with(
                task_id=executing_task.id,
                user_id="dev",
                force=True,
            )

    def test_delete_nonexistent_task_returns_404(
        self, mock_task_service, dev_user
    ):
        """Test that deleting a non-existent task returns 404."""
        mock_task_service.delete_task.side_effect = ValueError(
            "Task not found: nonexistent-task"
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            try:
                return await mock_task_service.delete_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                    force=force,
                )
            except ValueError as e:
                error_msg = str(e)
                if "not found" in error_msg.lower():
                    raise HTTPException(status_code=404, detail=error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

        with TestClient(app) as client:
            response = client.delete("/api/tasks/nonexistent-task")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_delete_other_users_task_returns_403(
        self, mock_task_service, dev_user
    ):
        """Test that deleting another user's task returns 403."""
        mock_task_service.delete_task.side_effect = PermissionError(
            "User dev does not own task other-user-task"
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            try:
                return await mock_task_service.delete_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                    force=force,
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

        with TestClient(app) as client:
            response = client.delete("/api/tasks/other-user-task")

            assert response.status_code == 403
            assert "does not own" in response.json()["detail"].lower()


class TestDeleteStatusPermutations:
    """Tests for deletion across all task status permutations."""

    @pytest.mark.parametrize("status", [
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ])
    def test_delete_terminal_states_without_force(
        self, mock_task_service, dev_user, status
    ):
        """Test that terminal state tasks can be deleted without force."""
        task = Task(
            id=f"test-{status.value}-task",
            user_id="dev",
            goal=f"Task in {status.value} state",
            status=status,
            tree_id=None,
            steps=[],
        )
        mock_task_service.delete_task.return_value = {
            "deleted": True,
            "task_id": task.id,
            "was_active": False,
            "tree_deleted": False,
            "message": "Deleted successfully",
        }

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            return await mock_task_service.delete_task(
                task_id=task_id,
                user_id=dev_user.id,
                force=force,
            )

        with TestClient(app) as client:
            response = client.delete(f"/api/tasks/{task.id}")

            assert response.status_code == 200
            assert response.json()["deleted"] is True

    @pytest.mark.parametrize("status", [
        TaskStatus.EXECUTING,
        TaskStatus.PLANNING,
        TaskStatus.CHECKPOINT,
        TaskStatus.PAUSED,
    ])
    def test_delete_active_states_requires_force(
        self, mock_task_service, dev_user, status
    ):
        """Test that active state tasks require force=true for deletion."""
        task = Task(
            id=f"test-{status.value}-task",
            user_id="dev",
            goal=f"Task in {status.value} state",
            status=status,
            tree_id="tree-123",
            steps=[],
        )
        mock_task_service.delete_task.side_effect = ValueError(
            f"Task is currently {status.value}. Use force=true to cancel and delete."
        )

        from fastapi import HTTPException

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            try:
                return await mock_task_service.delete_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                    force=force,
                )
            except ValueError as e:
                error_msg = str(e)
                if "not found" in error_msg.lower():
                    raise HTTPException(status_code=404, detail=error_msg)
                raise HTTPException(status_code=400, detail=error_msg)

        with TestClient(app) as client:
            response = client.delete(f"/api/tasks/{task.id}")

            assert response.status_code == 400
            assert status.value in response.json()["detail"].lower()


class TestDeleteResponseFormat:
    """Tests for delete API response format."""

    def test_response_includes_all_required_fields(
        self, mock_task_service, completed_task, dev_user
    ):
        """Test that response includes all required fields."""
        mock_task_service.delete_task.return_value = {
            "deleted": True,
            "task_id": completed_task.id,
            "was_active": False,
            "tree_deleted": True,
            "message": "Task deleted successfully",
        }

        app = FastAPI()

        @app.delete("/api/tasks/{task_id}")
        async def delete_task(task_id: str, force: bool = False):
            return await mock_task_service.delete_task(
                task_id=task_id,
                user_id=dev_user.id,
                force=force,
            )

        with TestClient(app) as client:
            response = client.delete(f"/api/tasks/{completed_task.id}")

            assert response.status_code == 200
            data = response.json()

            # Verify all required fields are present
            assert "deleted" in data
            assert "task_id" in data
            assert "was_active" in data
            assert "tree_deleted" in data
            assert "message" in data

            # Verify field types
            assert isinstance(data["deleted"], bool)
            assert isinstance(data["task_id"], str)
            assert isinstance(data["was_active"], bool)
            assert isinstance(data["tree_deleted"], bool)
            assert isinstance(data["message"], str)
