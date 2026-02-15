"""
Unit tests for Task ↔ ExecutionNode mapping functions.

Tests bidirectional conversion between Task/TaskStep models
and ExecutionNode structures.
"""

import pytest
from datetime import datetime, timedelta

from src.domain.tasks.models import (
    TaskStep, StepStatus, CheckpointConfig, FallbackConfig,
    ApprovalType, CheckpointType, ParallelFailurePolicy
)
from src.core.execution_tree import (
    ExecutionNode, ExecutionStatus, NodeType, ExecutionPriority, ExecutionMetrics
)
from src.infrastructure.tasks.task_tree_mapping import (
    task_step_to_node,
    node_to_task_step,
    step_status_to_execution_status,
    execution_status_to_step_status,
)


class TestStatusMapping:
    """Tests for status conversion between StepStatus and ExecutionStatus."""

    def test_pending_status_maps_correctly(self):
        """PENDING maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.PENDING) == ExecutionStatus.PENDING
        assert execution_status_to_step_status(ExecutionStatus.PENDING) == StepStatus.PENDING

    def test_running_status_maps_correctly(self):
        """RUNNING maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.RUNNING) == ExecutionStatus.RUNNING
        assert execution_status_to_step_status(ExecutionStatus.RUNNING) == StepStatus.RUNNING

    def test_done_completed_status_maps_correctly(self):
        """DONE ↔ COMPLETED maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.DONE) == ExecutionStatus.COMPLETED
        assert execution_status_to_step_status(ExecutionStatus.COMPLETED) == StepStatus.DONE

    def test_failed_status_maps_correctly(self):
        """FAILED maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.FAILED) == ExecutionStatus.FAILED
        assert execution_status_to_step_status(ExecutionStatus.FAILED) == StepStatus.FAILED

    def test_checkpoint_paused_status_maps_correctly(self):
        """CHECKPOINT ↔ PAUSED maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.CHECKPOINT) == ExecutionStatus.PAUSED
        assert execution_status_to_step_status(ExecutionStatus.PAUSED) == StepStatus.CHECKPOINT

    def test_skipped_cancelled_status_maps_correctly(self):
        """SKIPPED ↔ CANCELLED maps bidirectionally."""
        assert step_status_to_execution_status(StepStatus.SKIPPED) == ExecutionStatus.CANCELLED
        assert execution_status_to_step_status(ExecutionStatus.CANCELLED) == StepStatus.SKIPPED

    def test_timeout_maps_to_failed(self):
        """TIMEOUT maps to FAILED (no equivalent in StepStatus)."""
        assert execution_status_to_step_status(ExecutionStatus.TIMEOUT) == StepStatus.FAILED

    def test_waiting_maps_to_pending(self):
        """WAITING maps to PENDING (no equivalent in StepStatus)."""
        assert execution_status_to_step_status(ExecutionStatus.WAITING) == StepStatus.PENDING

    def test_expanded_maps_to_done(self):
        """EXPANDED maps to DONE (represents completed expansion)."""
        assert execution_status_to_step_status(ExecutionStatus.EXPANDED) == StepStatus.DONE


class TestTaskStepToNode:
    """Tests for task_step_to_node conversion."""

    def test_basic_step_conversion(self):
        """Basic TaskStep converts to ExecutionNode with correct fields."""
        step = TaskStep(
            id="step_1",
            name="Research Task",
            description="Gather information about topic",
            agent_type="web_research",
            inputs={"query": "AI news"},
            status=StepStatus.PENDING
        )

        node = task_step_to_node(step)

        assert node.id == "step_1"
        assert node.name == "Research Task"
        assert node.node_type == NodeType.AGENT
        assert node.status == ExecutionStatus.PENDING
        assert node.task_data == {"query": "AI news"}
        assert node.metadata["agent_type"] == "web_research"
        assert node.metadata["description"] == "Gather information about topic"

    def test_step_with_dependencies(self):
        """Step dependencies convert to node dependencies as Set."""
        step = TaskStep(
            id="step_2",
            name="Process Results",
            description="Process the research results",
            agent_type="analyzer",
            dependencies=["step_1", "step_0"]
        )

        node = task_step_to_node(step)

        assert node.dependencies == {"step_1", "step_0"}

    def test_step_without_dependencies_gets_root(self):
        """Step without dependencies depends on root by default."""
        step = TaskStep(
            id="step_1",
            name="First Step",
            description="Initial step",
            agent_type="processor"
        )

        node = task_step_to_node(step, parent_id="root")

        assert "root" in node.dependencies

    def test_step_with_domain(self):
        """Step domain is preserved in metadata."""
        step = TaskStep(
            id="step_1",
            name="Domain Step",
            description="Step with domain",
            agent_type="http_fetch",
            domain="research"
        )

        node = task_step_to_node(step)

        assert node.metadata["domain"] == "research"

    def test_step_with_checkpoint_config(self):
        """Checkpoint configuration is preserved in metadata."""
        checkpoint = CheckpointConfig(
            name="Approval Required",
            description="Needs human approval",
            approval_type=ApprovalType.EXPLICIT,
            checkpoint_type=CheckpointType.APPROVAL
        )

        step = TaskStep(
            id="step_1",
            name="Checkpoint Step",
            description="Step requiring approval",
            agent_type="notifier",
            checkpoint_required=True,
            checkpoint_config=checkpoint
        )

        node = task_step_to_node(step)

        assert node.metadata["checkpoint_required"] is True
        assert node.metadata["checkpoint_config"]["name"] == "Approval Required"
        assert node.metadata["checkpoint_config"]["approval_type"] == "explicit"

    def test_step_with_fallback_config(self):
        """Fallback configuration is preserved in metadata."""
        fallback = FallbackConfig(
            models=["gpt-4", "claude-3"],
            apis=["backup-api.com"]
        )

        step = TaskStep(
            id="step_1",
            name="Fallback Step",
            description="Step with fallback",
            agent_type="llm_call",
            fallback_config=fallback
        )

        node = task_step_to_node(step)

        assert node.metadata["fallback_config"]["models"] == ["gpt-4", "claude-3"]
        assert node.metadata["fallback_config"]["apis"] == ["backup-api.com"]

    def test_step_with_outputs(self):
        """Step outputs map to node result_data."""
        step = TaskStep(
            id="step_1",
            name="Completed Step",
            description="Step with outputs",
            agent_type="processor",
            status=StepStatus.DONE,
            outputs={"result": "success", "data": {"count": 42}}
        )

        node = task_step_to_node(step)

        assert node.result_data == {"result": "success", "data": {"count": 42}}
        assert node.status == ExecutionStatus.COMPLETED

    def test_step_with_error(self):
        """Step error message maps to node error_data."""
        step = TaskStep(
            id="step_1",
            name="Failed Step",
            description="Step that failed",
            agent_type="processor",
            status=StepStatus.FAILED,
            error_message="Connection timeout"
        )

        node = task_step_to_node(step)

        assert node.error_data == {"error": "Connection timeout"}
        assert node.status == ExecutionStatus.FAILED

    def test_step_with_timing(self):
        """Step timing is preserved in node metrics."""
        started = datetime(2024, 1, 1, 10, 0, 0)
        completed = datetime(2024, 1, 1, 10, 5, 0)

        step = TaskStep(
            id="step_1",
            name="Timed Step",
            description="Step with timing",
            agent_type="processor",
            status=StepStatus.DONE,
            started_at=started,
            completed_at=completed
        )

        node = task_step_to_node(step)

        assert node.metrics.start_time == started
        assert node.metrics.end_time == completed
        assert node.metrics.duration == timedelta(minutes=5)

    def test_step_retry_count(self):
        """Step retry settings are preserved."""
        step = TaskStep(
            id="step_1",
            name="Retry Step",
            description="Step with retries",
            agent_type="processor",
            retry_count=2,
            max_retries=5
        )

        node = task_step_to_node(step)

        assert node.retry_count == 2
        assert node.max_retries == 5

    def test_step_parallel_group(self):
        """Step parallel_group is preserved in metadata."""
        step = TaskStep(
            id="step_1",
            name="Parallel Step",
            description="Step in parallel group",
            agent_type="processor",
            parallel_group="fetch_group"
        )

        node = task_step_to_node(step)

        assert node.metadata["parallel_group"] == "fetch_group"


class TestNodeToTaskStep:
    """Tests for node_to_task_step conversion."""

    def test_basic_node_conversion(self):
        """Basic ExecutionNode converts to TaskStep with correct fields."""
        node = ExecutionNode(
            id="node_1",
            name="Process Node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.PENDING,
            metadata={
                "agent_type": "processor",
                "description": "Process data",
                "inputs": {"data": "test"}
            },
            task_data={"data": "test"}
        )

        step = node_to_task_step(node)

        assert step.id == "node_1"
        assert step.name == "Process Node"
        assert step.agent_type == "processor"
        assert step.description == "Process data"
        assert step.status == StepStatus.PENDING
        assert step.inputs == {"data": "test"}

    def test_node_with_dependencies(self):
        """Node dependencies convert to step dependencies as List."""
        node = ExecutionNode(
            id="node_2",
            name="Dependent Node",
            node_type=NodeType.AGENT,
            dependencies={"node_1", "node_0"},
            metadata={"agent_type": "processor", "description": ""}
        )

        step = node_to_task_step(node)

        # Dependencies should be a list (order may vary)
        assert set(step.dependencies) == {"node_1", "node_0"}

    def test_root_dependency_is_filtered(self):
        """Root dependency is filtered out from step dependencies."""
        node = ExecutionNode(
            id="node_1",
            name="First Node",
            node_type=NodeType.AGENT,
            dependencies={"root", "node_0"},
            metadata={"agent_type": "processor", "description": ""}
        )

        step = node_to_task_step(node)

        assert "root" not in step.dependencies
        assert "node_0" in step.dependencies

    def test_node_with_result_data(self):
        """Node result_data maps to step outputs."""
        node = ExecutionNode(
            id="node_1",
            name="Completed Node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.COMPLETED,
            result_data={"output": "success", "count": 10},
            metadata={"agent_type": "processor", "description": ""}
        )

        step = node_to_task_step(node)

        assert step.outputs == {"output": "success", "count": 10}
        assert step.status == StepStatus.DONE

    def test_node_with_error_data(self):
        """Node error_data maps to step error_message."""
        node = ExecutionNode(
            id="node_1",
            name="Failed Node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.FAILED,
            error_data={"error": "Network failure", "code": 500},
            metadata={"agent_type": "processor", "description": ""}
        )

        step = node_to_task_step(node)

        assert step.error_message == "Network failure"
        assert step.status == StepStatus.FAILED

    def test_node_with_checkpoint_config(self):
        """Node checkpoint_config in metadata is reconstructed."""
        node = ExecutionNode(
            id="node_1",
            name="Checkpoint Node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.PAUSED,
            metadata={
                "agent_type": "notifier",
                "description": "",
                "checkpoint_required": True,
                "checkpoint_config": {
                    "name": "Review Required",
                    "description": "Needs review",
                    "approval_type": "explicit",
                    "timeout_minutes": 30,
                    "checkpoint_type": "approval"
                }
            }
        )

        step = node_to_task_step(node)

        assert step.checkpoint_required is True
        assert step.checkpoint_config is not None
        assert step.checkpoint_config.name == "Review Required"
        assert step.checkpoint_config.approval_type == ApprovalType.EXPLICIT
        assert step.status == StepStatus.CHECKPOINT

    def test_node_with_timing_metrics(self):
        """Node timing metrics are reconstructed in step."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 10, 0)
        duration = timedelta(minutes=10)

        metrics = ExecutionMetrics(
            start_time=start,
            end_time=end,
            duration=duration
        )

        node = ExecutionNode(
            id="node_1",
            name="Timed Node",
            node_type=NodeType.AGENT,
            status=ExecutionStatus.COMPLETED,
            metrics=metrics,
            metadata={"agent_type": "processor", "description": ""}
        )

        step = node_to_task_step(node)

        assert step.started_at == start
        assert step.completed_at == end
        assert step.execution_time_ms == 600000  # 10 minutes in ms

    def test_node_fallback_when_no_agent_type(self):
        """When agent_type not in metadata, fall back to node_type."""
        node = ExecutionNode(
            id="node_1",
            name="Generic Node",
            node_type=NodeType.AGENT,
            metadata={"description": "No agent type specified"}
        )

        step = node_to_task_step(node)

        assert step.agent_type == "agent"  # NodeType.AGENT.value


class TestRoundTrip:
    """Tests for bidirectional conversion integrity."""

    def test_step_to_node_to_step_preserves_data(self):
        """Converting step→node→step preserves all essential data."""
        original_step = TaskStep(
            id="roundtrip_1",
            name="Round Trip Test",
            description="Testing round-trip conversion",
            agent_type="analyzer",
            domain="research",
            inputs={"query": "test query", "limit": 10},
            outputs={"results": ["a", "b"]},
            dependencies=["prev_step"],
            status=StepStatus.DONE,
            parallel_group="analysis_group",
            checkpoint_required=False,
            is_critical=True,
            retry_count=1,
            max_retries=3,
            error_message=None
        )

        # Convert to node and back
        node = task_step_to_node(original_step)
        restored_step = node_to_task_step(node)

        # Verify essential fields are preserved
        assert restored_step.id == original_step.id
        assert restored_step.name == original_step.name
        assert restored_step.description == original_step.description
        assert restored_step.agent_type == original_step.agent_type
        assert restored_step.domain == original_step.domain
        assert restored_step.inputs == original_step.inputs
        assert restored_step.outputs == original_step.outputs
        assert set(restored_step.dependencies) == set(original_step.dependencies)
        assert restored_step.status == original_step.status
        assert restored_step.parallel_group == original_step.parallel_group
        assert restored_step.checkpoint_required == original_step.checkpoint_required
        assert restored_step.is_critical == original_step.is_critical
        assert restored_step.retry_count == original_step.retry_count
        assert restored_step.max_retries == original_step.max_retries

    def test_step_with_checkpoint_round_trip(self):
        """Step with checkpoint config survives round-trip conversion."""
        checkpoint = CheckpointConfig(
            name="Approval Gate",
            description="Requires manager approval",
            approval_type=ApprovalType.TIMEOUT,
            timeout_minutes=120,
            checkpoint_type=CheckpointType.APPROVAL
        )

        original = TaskStep(
            id="checkpoint_step",
            name="Checkpoint Test",
            description="Test checkpoint preservation",
            agent_type="notifier",
            checkpoint_required=True,
            checkpoint_config=checkpoint
        )

        node = task_step_to_node(original)
        restored = node_to_task_step(node)

        assert restored.checkpoint_required is True
        assert restored.checkpoint_config is not None
        assert restored.checkpoint_config.name == "Approval Gate"
        assert restored.checkpoint_config.approval_type == ApprovalType.TIMEOUT
        assert restored.checkpoint_config.timeout_minutes == 120

    def test_step_with_fallback_round_trip(self):
        """Step with fallback config survives round-trip conversion."""
        fallback = FallbackConfig(
            models=["model-a", "model-b"],
            apis=["api-1", "api-2"],
            strategies=["strategy-x"]
        )

        original = TaskStep(
            id="fallback_step",
            name="Fallback Test",
            description="Test fallback preservation",
            agent_type="llm_call",
            fallback_config=fallback
        )

        node = task_step_to_node(original)
        restored = node_to_task_step(node)

        assert restored.fallback_config is not None
        assert restored.fallback_config.models == ["model-a", "model-b"]
        assert restored.fallback_config.apis == ["api-1", "api-2"]
        assert restored.fallback_config.strategies == ["strategy-x"]
