"""Unit tests for the task output retrieval plugin handler.

Tests:
- task_output_retrieval_handler: validates required fields, access control,
  retrieves all or specific step outputs, handles errors
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from src.infrastructure.execution_runtime.execution_context import ExecutionContext
from src.plugins.task_output_retrieval_plugin import (
    task_output_retrieval_handler,
    _truncate_outputs,
    MAX_OUTPUT_STRING_SIZE,
    PLUGIN_HANDLERS,
)


# --- Helpers ---


class MockStepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class MockTaskStatus(Enum):
    COMPLETED = "completed"
    EXECUTING = "executing"
    PLANNING = "planning"


@dataclass
class MockStep:
    id: str
    name: str
    agent_type: str
    status: MockStepStatus = MockStepStatus.DONE
    outputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockTask:
    id: str
    organization_id: str
    goal: str
    status: MockTaskStatus = MockTaskStatus.COMPLETED
    steps: List[MockStep] = field(default_factory=list)


def make_context(org_id="org-123", user_id="user-456"):
    """Create an ExecutionContext for testing."""
    return ExecutionContext(
        organization_id=org_id,
        user_id=user_id,
        step_id="step-test",
        task_id="task-test",
    )


def make_task(
    task_id="target-task-123",
    org_id="org-123",
    goal="Generate a PDF report",
    status=MockTaskStatus.COMPLETED,
    steps=None,
):
    """Create a MockTask for testing."""
    if steps is None:
        steps = [
            MockStep(
                id="step_1",
                name="research",
                agent_type="web_search",
                status=MockStepStatus.DONE,
                outputs={"summary": "Research findings here"},
            ),
            MockStep(
                id="step_2",
                name="generate_pdf",
                agent_type="pdf_composer",
                status=MockStepStatus.DONE,
                outputs={
                    "file_path": "/tmp/output.pdf",
                    "pdf_base64": "base64content",
                },
            ),
        ]
    return MockTask(
        id=task_id,
        organization_id=org_id,
        goal=goal,
        status=status,
        steps=steps,
    )


# --- Tests ---


class TestPluginExports:
    """Tests for PLUGIN_HANDLERS dictionary."""

    def test_exports_task_output_retrieval(self):
        assert "task_output_retrieval" in PLUGIN_HANDLERS
        assert PLUGIN_HANDLERS["task_output_retrieval"] is task_output_retrieval_handler


class TestTruncateOutputs:
    """Tests for the _truncate_outputs helper."""

    def test_no_truncation_for_small_values(self):
        outputs = {"key": "small value"}
        result = _truncate_outputs(outputs)
        assert result == outputs

    def test_truncates_large_string_values(self):
        large = "x" * (MAX_OUTPUT_STRING_SIZE + 100)
        outputs = {"big": large, "small": "ok"}
        result = _truncate_outputs(outputs)
        assert len(result["big"]) < len(large)
        assert result["big"].endswith("... [truncated]")
        assert result["small"] == "ok"

    def test_handles_none_outputs(self):
        assert _truncate_outputs(None) == {}

    def test_handles_empty_outputs(self):
        assert _truncate_outputs({}) == {}

    def test_preserves_non_string_values(self):
        outputs = {"count": 42, "items": [1, 2, 3]}
        result = _truncate_outputs(outputs)
        assert result == outputs


class TestMissingContextAndInputs:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_missing_context_returns_error(self):
        """Missing context should return an error."""
        result = await task_output_retrieval_handler({"task_id": "some-id"})
        assert result["status"] == "error"
        assert "ExecutionContext" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_task_id_returns_error(self):
        """Missing task_id should return an error."""
        ctx = make_context()
        result = await task_output_retrieval_handler({}, context=ctx)
        assert result["status"] == "error"
        assert "task_id" in result["error"]


class TestTaskNotFound:
    """Tests for task not found scenario."""

    @pytest.mark.asyncio
    async def test_task_not_found_returns_error(self):
        """Non-existent task should return an error."""
        ctx = make_context()
        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=None)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "nonexistent-id"}, context=ctx
            )

        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestAccessControl:
    """Tests for organization-based access control."""

    @pytest.mark.asyncio
    async def test_different_org_returns_access_denied(self):
        """Accessing a task from a different org should be denied."""
        ctx = make_context(org_id="org-123")
        task = make_task(org_id="org-OTHER")

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123"}, context=ctx
            )

        assert result["status"] == "error"
        assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_same_org_returns_data(self):
        """Accessing a task from the same org should succeed."""
        ctx = make_context(org_id="org-123")
        task = make_task(org_id="org-123")

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123"}, context=ctx
            )

        assert "status" not in result or result.get("status") != "error"
        assert result["task_id"] == "target-task-123"


class TestAllStepsRetrieval:
    """Tests for retrieving all steps."""

    @pytest.mark.asyncio
    async def test_returns_all_steps_with_outputs(self):
        """Should return all steps with their outputs."""
        ctx = make_context()
        task = make_task()

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123"}, context=ctx
            )

        assert result["task_id"] == "target-task-123"
        assert result["task_status"] == "completed"
        assert result["task_goal"] == "Generate a PDF report"
        assert result["step_count"] == 2
        assert len(result["steps"]) == 2

        # Verify step data
        step_1 = result["steps"][0]
        assert step_1["step_id"] == "step_1"
        assert step_1["step_name"] == "research"
        assert step_1["agent_type"] == "web_search"
        assert step_1["status"] == "done"
        assert step_1["outputs"]["summary"] == "Research findings here"

        step_2 = result["steps"][1]
        assert step_2["step_id"] == "step_2"
        assert step_2["step_name"] == "generate_pdf"
        assert step_2["outputs"]["file_path"] == "/tmp/output.pdf"

    @pytest.mark.asyncio
    async def test_task_still_executing_returns_partial(self):
        """Should return partial outputs when task is still executing."""
        ctx = make_context()
        steps = [
            MockStep(
                id="step_1",
                name="research",
                agent_type="web_search",
                status=MockStepStatus.DONE,
                outputs={"summary": "Done"},
            ),
            MockStep(
                id="step_2",
                name="generate_pdf",
                agent_type="pdf_composer",
                status=MockStepStatus.RUNNING,
                outputs={},
            ),
        ]
        task = make_task(status=MockTaskStatus.EXECUTING, steps=steps)

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123"}, context=ctx
            )

        assert result["task_status"] == "executing"
        assert result["step_count"] == 2
        # First step done with outputs
        assert result["steps"][0]["status"] == "done"
        assert result["steps"][0]["outputs"]["summary"] == "Done"
        # Second step still running with empty outputs
        assert result["steps"][1]["status"] == "running"
        assert result["steps"][1]["outputs"] == {}


class TestSpecificStepRetrieval:
    """Tests for retrieving a specific step."""

    @pytest.mark.asyncio
    async def test_retrieve_by_step_id(self):
        """Should return specific step when step_id provided."""
        ctx = make_context()
        task = make_task()

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123", "step_id": "step_2"}, context=ctx
            )

        assert result["task_id"] == "target-task-123"
        assert result["step_id"] == "step_2"
        assert result["step_name"] == "generate_pdf"
        assert result["agent_type"] == "pdf_composer"
        assert result["status"] == "done"
        assert result["outputs"]["file_path"] == "/tmp/output.pdf"

    @pytest.mark.asyncio
    async def test_retrieve_by_step_name(self):
        """Should return specific step when step_name provided."""
        ctx = make_context()
        task = make_task()

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123", "step_name": "generate_pdf"},
                context=ctx,
            )

        assert result["step_id"] == "step_2"
        assert result["step_name"] == "generate_pdf"
        assert result["outputs"]["file_path"] == "/tmp/output.pdf"

    @pytest.mark.asyncio
    async def test_step_not_found_by_id_returns_error(self):
        """Should return error when step_id not found."""
        ctx = make_context()
        task = make_task()

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123", "step_id": "nonexistent"},
                context=ctx,
            )

        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_step_not_found_by_name_returns_error(self):
        """Should return error when step_name not found."""
        ctx = make_context()
        task = make_task()

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123", "step_name": "nonexistent"},
                context=ctx,
            )

        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestLargeOutputTruncation:
    """Tests for large output truncation in the handler."""

    @pytest.mark.asyncio
    async def test_large_output_is_truncated(self):
        """Should truncate large string values in step outputs."""
        ctx = make_context()
        large_base64 = "A" * (MAX_OUTPUT_STRING_SIZE + 1000)
        steps = [
            MockStep(
                id="step_1",
                name="generate_pdf",
                agent_type="pdf_composer",
                status=MockStepStatus.DONE,
                outputs={"pdf_base64": large_base64, "file_path": "/tmp/out.pdf"},
            ),
        ]
        task = make_task(steps=steps)

        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(return_value=task)

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123", "step_id": "step_1"}, context=ctx
            )

        assert result["outputs"]["pdf_base64"].endswith("... [truncated]")
        assert len(result["outputs"]["pdf_base64"]) < len(large_base64)
        # Non-large values are preserved
        assert result["outputs"]["file_path"] == "/tmp/out.pdf"


class TestDatabaseError:
    """Tests for database error handling."""

    @pytest.mark.asyncio
    async def test_db_exception_returns_error(self):
        """Should handle database exceptions gracefully."""
        ctx = make_context()
        mock_store = MagicMock()
        mock_store.get_task = AsyncMock(side_effect=Exception("DB connection lost"))

        with patch(
            "src.plugins.task_output_retrieval_plugin._get_task_use_cases",
            new=AsyncMock(return_value=mock_store),
        ):
            result = await task_output_retrieval_handler(
                {"task_id": "target-task-123"}, context=ctx
            )

        assert result["status"] == "error"
        assert "DB connection lost" in result["error"]
