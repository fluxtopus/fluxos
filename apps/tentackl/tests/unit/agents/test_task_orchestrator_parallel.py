"""
Unit tests for TaskOrchestratorAgent parallel execution.

Tests the plan-driven parallel execution functionality where steps
with the same parallel_group run concurrently.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    ParallelFailurePolicy,
)


# Test fixtures
TEST_USER_ID = "test-user-123"
TEST_ORG_ID = "test-org-123"


class TestTaskParallelGrouping:
    """Test Task.get_ready_steps_grouped() method."""

    def test_single_step_returns_single_group(self):
        """Single ready step returns as single-element group."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Only Step",
                    description="Single step for testing",
                    agent_type="http_fetch",
                    inputs={"url": "http://example.com"},
                    status=StepStatus.PENDING,
                ),
            ],
        )

        groups = plan.get_ready_steps_grouped()

        assert len(groups) == 1
        assert len(groups[0]) == 1
        assert groups[0][0].id == "step_1"

    def test_parallel_group_returns_together(self):
        """Steps with same parallel_group are grouped together."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch A",
                    description="Fetch from API A",
                    agent_type="http_fetch",
                    inputs={"url": "http://a.com"},
                    status=StepStatus.PENDING,
                    parallel_group="fetch",
                ),
                TaskStep(
                    id="step_2",
                    name="Fetch B",
                    description="Fetch from API B",
                    agent_type="http_fetch",
                    inputs={"url": "http://b.com"},
                    status=StepStatus.PENDING,
                    parallel_group="fetch",
                ),
                TaskStep(
                    id="step_3",
                    name="Process",
                    description="Process fetched data",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    dependencies=["step_1", "step_2"],
                ),
            ],
        )

        groups = plan.get_ready_steps_grouped()

        # First group should have both fetch steps
        assert len(groups) == 1
        assert len(groups[0]) == 2
        step_ids = {s.id for s in groups[0]}
        assert step_ids == {"step_1", "step_2"}

    def test_sequential_steps_return_separately(self):
        """Steps without parallel_group return as separate groups."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch",
                    description="Fetch data",
                    agent_type="http_fetch",
                    inputs={"url": "http://example.com"},
                    status=StepStatus.PENDING,
                ),
                TaskStep(
                    id="step_2",
                    name="Process",
                    description="Process data",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    # No dependencies, but no parallel_group either
                ),
            ],
        )

        groups = plan.get_ready_steps_grouped()

        # Each step is its own group (sequential)
        assert len(groups) == 2
        assert len(groups[0]) == 1
        assert len(groups[1]) == 1

    def test_dependencies_block_grouping(self):
        """Steps with unfulfilled dependencies are not in ready groups."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch",
                    description="Fetch data",
                    agent_type="http_fetch",
                    inputs={"url": "http://example.com"},
                    status=StepStatus.PENDING,
                ),
                TaskStep(
                    id="step_2",
                    name="Process",
                    description="Process data",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    dependencies=["step_1"],  # Depends on step_1
                ),
            ],
        )

        groups = plan.get_ready_steps_grouped()

        # Only step_1 is ready
        assert len(groups) == 1
        assert len(groups[0]) == 1
        assert groups[0][0].id == "step_1"

    def test_completed_dependencies_allow_grouping(self):
        """Steps become ready when dependencies are complete."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[
                TaskStep(
                    id="step_1",
                    name="Fetch A",
                    description="Fetch from A",
                    agent_type="http_fetch",
                    inputs={"url": "http://a.com"},
                    status=StepStatus.DONE,  # Already completed
                ),
                TaskStep(
                    id="step_2",
                    name="Process A",
                    description="Process A data",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    dependencies=["step_1"],
                    parallel_group="process",
                ),
                TaskStep(
                    id="step_3",
                    name="Fetch B",
                    description="Fetch from B",
                    agent_type="http_fetch",
                    inputs={"url": "http://b.com"},
                    status=StepStatus.DONE,  # Already completed
                ),
                TaskStep(
                    id="step_4",
                    name="Process B",
                    description="Process B data",
                    agent_type="llm_analysis",
                    inputs={},
                    status=StepStatus.PENDING,
                    dependencies=["step_3"],
                    parallel_group="process",
                ),
            ],
        )

        groups = plan.get_ready_steps_grouped()

        # Both process steps should be ready and grouped
        assert len(groups) == 1
        assert len(groups[0]) == 2
        step_ids = {s.id for s in groups[0]}
        assert step_ids == {"step_2", "step_4"}


class TestTaskStepFailurePolicy:
    """Test failure policy field on TaskStep."""

    def test_default_failure_policy(self):
        """Default failure policy is ALL_OR_NOTHING."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="http_fetch",
            inputs={},
        )

        assert step.failure_policy == ParallelFailurePolicy.ALL_OR_NOTHING

    def test_explicit_failure_policy(self):
        """Can set explicit failure policy."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="http_fetch",
            inputs={},
            failure_policy=ParallelFailurePolicy.BEST_EFFORT,
        )

        assert step.failure_policy == ParallelFailurePolicy.BEST_EFFORT

    def test_failure_policy_serialization(self):
        """Failure policy serializes correctly."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="http_fetch",
            inputs={},
            failure_policy=ParallelFailurePolicy.FAIL_FAST,
        )

        data = step.to_dict()
        assert data["failure_policy"] == "fail_fast"

        # Round-trip
        restored = TaskStep.from_dict(data)
        assert restored.failure_policy == ParallelFailurePolicy.FAIL_FAST


class TestTaskMaxParallelSteps:
    """Test max_parallel_steps field on Task."""

    def test_default_max_parallel_steps(self):
        """Default max_parallel_steps is 5."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[],
        )

        assert plan.max_parallel_steps == 5

    def test_explicit_max_parallel_steps(self):
        """Can set explicit max_parallel_steps."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[],
            max_parallel_steps=10,
        )

        assert plan.max_parallel_steps == 10

    def test_max_parallel_steps_serialization(self):
        """max_parallel_steps serializes correctly."""
        plan = Task(
            id="test-plan",
            goal="Test goal",
            user_id=TEST_USER_ID,
            steps=[],
            max_parallel_steps=3,
        )

        data = plan.to_dict()
        assert data["max_parallel_steps"] == 3

        # Round-trip
        restored = Task.from_dict(data)
        assert restored.max_parallel_steps == 3


class TestParallelFailurePolicyEnum:
    """Test ParallelFailurePolicy enum."""

    def test_all_policies_exist(self):
        """All expected policies exist."""
        assert hasattr(ParallelFailurePolicy, "ALL_OR_NOTHING")
        assert hasattr(ParallelFailurePolicy, "BEST_EFFORT")
        assert hasattr(ParallelFailurePolicy, "FAIL_FAST")

    def test_policy_values(self):
        """Policy values are correct strings."""
        assert ParallelFailurePolicy.ALL_OR_NOTHING.value == "all_or_nothing"
        assert ParallelFailurePolicy.BEST_EFFORT.value == "best_effort"
        assert ParallelFailurePolicy.FAIL_FAST.value == "fail_fast"
