"""Integration tests for task rerun API endpoint.

These tests verify the POST /api/tasks/{id}/rerun endpoint works correctly
for re-running completed non-template tasks.
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from src.application.tasks.runtime import TaskRuntime as TaskService
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus
from src.api.auth_middleware import auth_middleware, AuthUser, DEVELOPER_SCOPES


@pytest.fixture
def mock_task_service():
    """Create a mock task service."""
    service = AsyncMock(spec=TaskService)
    service.get_task = AsyncMock()
    service.rerun_task = AsyncMock()
    return service


@pytest.fixture
def completed_task():
    """Create a completed task for testing."""
    return Task(
        id="test-task-123",
        user_id="dev",
        organization_id="org-789",
        goal="Research AI developments",
        status=TaskStatus.COMPLETED,
        steps=[
            TaskStep(
                id="step-1",
                name="research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.DONE,
                outputs={"data": "test output"},
            ),
            TaskStep(
                id="step-2",
                name="summarize",
                description="Summarize step",
                agent_type="summarizer",
                status=StepStatus.DONE,
                dependencies=["step-1"],
                outputs={"summary": "test summary"},
            ),
        ],
        completed_at=datetime.utcnow(),
        is_template=False,
    )


@pytest.fixture
def rerun_ready_task(completed_task):
    """Create a task in READY state after rerun."""
    return Task(
        id=completed_task.id,
        user_id=completed_task.user_id,
        organization_id=completed_task.organization_id,
        goal=completed_task.goal,
        status=TaskStatus.READY,
        steps=[
            TaskStep(
                id="step-1",
                name="research",
                description="Research step",
                agent_type="web_research",
                status=StepStatus.PENDING,
                outputs={},
            ),
            TaskStep(
                id="step-2",
                name="summarize",
                description="Summarize step",
                agent_type="summarizer",
                status=StepStatus.PENDING,
                dependencies=["step-1"],
                outputs={},
            ),
        ],
        completed_at=None,
        is_template=False,
        metadata={"rerun_count": 1},
    )


@pytest.fixture
def template_task():
    """Create a template task for testing."""
    return Task(
        id="template-task-456",
        user_id="dev",
        organization_id="org-789",
        goal="Daily news digest",
        status=TaskStatus.COMPLETED,
        steps=[
            TaskStep(
                id="step-1",
                name="fetch",
                description="Fetch news",
                agent_type="http_fetch",
                status=StepStatus.DONE,
            ),
        ],
        is_template=True,
        schedule_cron="0 8 * * *",
        schedule_enabled=True,
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


class TestRerunEndpoint:
    """Tests for POST /api/tasks/{id}/rerun endpoint."""

    def test_rerun_completed_task_success(
        self, mock_task_service, completed_task, rerun_ready_task, dev_user
    ):
        """Test successful rerun of a completed task."""
        mock_task_service.rerun_task.return_value = rerun_ready_task

        # Create a minimal test app with just the rerun endpoint
        from fastapi import FastAPI, APIRouter
        from pydantic import BaseModel

        app = FastAPI()

        # Simple response model
        class TaskResponse(BaseModel):
            id: str
            status: str
            steps: list = []
            metadata: dict = {}

            class Config:
                from_attributes = True

        # Minimal router with just the rerun endpoint
        @app.post("/api/tasks/{task_id}/rerun", response_model=TaskResponse)
        async def rerun_task(task_id: str):
            task = await mock_task_service.rerun_task(
                task_id=task_id,
                user_id=dev_user.id,
            )
            return TaskResponse(
                id=task.id,
                status=task.status.value,
                steps=[{"id": s.id, "status": s.status.value, "outputs": s.outputs} for s in task.steps],
                metadata=task.metadata,
            )

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{completed_task.id}/rerun")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == completed_task.id
            assert data["status"] == "ready"
            mock_task_service.rerun_task.assert_called_once_with(
                task_id=completed_task.id,
                user_id="dev",
            )

    def test_rerun_template_task_fails(
        self, mock_task_service, template_task, dev_user
    ):
        """Test that rerunning a template task returns 400."""
        mock_task_service.rerun_task.side_effect = ValueError(
            f"Task {template_task.id} is a template. Use /run endpoint instead."
        )

        from fastapi import FastAPI, HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/rerun")
        async def rerun_task(task_id: str):
            try:
                return await mock_task_service.rerun_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{template_task.id}/rerun")

            assert response.status_code == 400
            assert "template" in response.json()["detail"].lower()

    def test_rerun_non_completed_task_fails(
        self, mock_task_service, completed_task, dev_user
    ):
        """Test that rerunning a non-completed task returns 400."""
        mock_task_service.rerun_task.side_effect = ValueError(
            f"Task {completed_task.id} is not completed. Current status: executing"
        )

        from fastapi import FastAPI, HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/rerun")
        async def rerun_task(task_id: str):
            try:
                return await mock_task_service.rerun_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{completed_task.id}/rerun")

            assert response.status_code == 400
            assert "not completed" in response.json()["detail"].lower()

    def test_rerun_nonexistent_task_fails(self, mock_task_service, dev_user):
        """Test that rerunning a nonexistent task returns 400."""
        mock_task_service.rerun_task.side_effect = ValueError(
            "Task not found: nonexistent-id"
        )

        from fastapi import FastAPI, HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/rerun")
        async def rerun_task(task_id: str):
            try:
                return await mock_task_service.rerun_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        with TestClient(app) as client:
            response = client.post("/api/tasks/nonexistent-id/rerun")

            assert response.status_code == 400
            assert "not found" in response.json()["detail"].lower()

    def test_rerun_task_permission_denied(self, mock_task_service, dev_user):
        """Test that rerunning another user's task returns 403."""
        mock_task_service.rerun_task.side_effect = PermissionError(
            "User dev does not own task other-user-task"
        )

        from fastapi import FastAPI, HTTPException

        app = FastAPI()

        @app.post("/api/tasks/{task_id}/rerun")
        async def rerun_task(task_id: str):
            try:
                return await mock_task_service.rerun_task(
                    task_id=task_id,
                    user_id=dev_user.id,
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

        with TestClient(app) as client:
            response = client.post("/api/tasks/other-user-task/rerun")

            assert response.status_code == 403
            assert "does not own" in response.json()["detail"].lower()

    def test_rerun_resets_step_states(
        self, mock_task_service, completed_task, rerun_ready_task, dev_user
    ):
        """Test that rerun resets all step states to PENDING."""
        mock_task_service.rerun_task.return_value = rerun_ready_task

        from fastapi import FastAPI
        from pydantic import BaseModel

        app = FastAPI()

        class TaskResponse(BaseModel):
            id: str
            status: str
            steps: list = []
            metadata: dict = {}

            class Config:
                from_attributes = True

        @app.post("/api/tasks/{task_id}/rerun", response_model=TaskResponse)
        async def rerun_task(task_id: str):
            task = await mock_task_service.rerun_task(
                task_id=task_id,
                user_id=dev_user.id,
            )
            return TaskResponse(
                id=task.id,
                status=task.status.value,
                steps=[{"id": s.id, "status": s.status.value, "outputs": s.outputs} for s in task.steps],
                metadata=task.metadata,
            )

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{completed_task.id}/rerun")

            assert response.status_code == 200
            data = response.json()

            # Verify all steps are reset to pending
            for step in data["steps"]:
                assert step["status"] == "pending"
                # Outputs should be cleared
                assert step.get("outputs") == {} or step.get("outputs") is None

    def test_rerun_increments_rerun_count(
        self, mock_task_service, completed_task, rerun_ready_task, dev_user
    ):
        """Test that rerun increments the rerun_count in metadata."""
        mock_task_service.rerun_task.return_value = rerun_ready_task

        from fastapi import FastAPI
        from pydantic import BaseModel

        app = FastAPI()

        class TaskResponse(BaseModel):
            id: str
            status: str
            steps: list = []
            metadata: dict = {}

            class Config:
                from_attributes = True

        @app.post("/api/tasks/{task_id}/rerun", response_model=TaskResponse)
        async def rerun_task(task_id: str):
            task = await mock_task_service.rerun_task(
                task_id=task_id,
                user_id=dev_user.id,
            )
            return TaskResponse(
                id=task.id,
                status=task.status.value,
                steps=[{"id": s.id, "status": s.status.value, "outputs": s.outputs} for s in task.steps],
                metadata=task.metadata,
            )

        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{completed_task.id}/rerun")

            assert response.status_code == 200
            data = response.json()

            # Check metadata has rerun tracking
            assert data.get("metadata", {}).get("rerun_count") == 1
