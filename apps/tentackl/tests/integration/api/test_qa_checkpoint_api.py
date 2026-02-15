"""
Integration tests for QA checkpoint API flow.

Tests the complete flow of:
1. Agent returning questions in SubagentResult
2. CheckpointResponse model including QA fields
3. QA checkpoint creation from SubagentResult
"""

import pytest
from datetime import datetime

from src.domain.checkpoints.models import CheckpointState, CheckpointType, CheckpointDecision


class TestCheckpointTypeInResponse:
    """Tests for checkpoint type field in API responses."""

    @pytest.mark.asyncio
    async def test_checkpoint_response_includes_type_for_qa(self):
        """Test that checkpoint API responses include the checkpoint_type field for QA checkpoints."""
        from src.api.routers.tasks import _checkpoint_to_response

        checkpoint = CheckpointState(
            plan_id="task-123",
            step_id="step-1",
            checkpoint_name="qa_checkpoint",
            description="Needs answers",
            decision=CheckpointDecision.PENDING,
            preview_data={},
            created_at=datetime.utcnow(),
            checkpoint_type=CheckpointType.QA,
            questions=["Q1?", "Q2?"],
            context_data={"hint": "provide short answers"},
        )

        response = _checkpoint_to_response(checkpoint)

        assert response.checkpoint_type == "qa"
        assert response.questions == ["Q1?", "Q2?"]
        assert response.context_data == {"hint": "provide short answers"}

    @pytest.mark.asyncio
    async def test_checkpoint_response_includes_type_for_approval(self):
        """Test that approval checkpoints have correct type."""
        from src.api.routers.tasks import _checkpoint_to_response

        checkpoint = CheckpointState(
            plan_id="task-456",
            step_id="step-2",
            checkpoint_name="approval_checkpoint",
            description="Approve action",
            decision=CheckpointDecision.PENDING,
            preview_data={"action": "send_email"},
            created_at=datetime.utcnow(),
            checkpoint_type=CheckpointType.APPROVAL,
        )

        response = _checkpoint_to_response(checkpoint)

        assert response.checkpoint_type == "approval"
        assert response.questions is None

    @pytest.mark.asyncio
    async def test_checkpoint_response_includes_all_interactive_fields(self):
        """Test that all interactive checkpoint fields are included in response."""
        from src.api.routers.tasks import _checkpoint_to_response

        checkpoint = CheckpointState(
            plan_id="task-789",
            step_id="step-3",
            checkpoint_name="select_checkpoint",
            description="Choose an option",
            decision=CheckpointDecision.PENDING,
            preview_data={},
            created_at=datetime.utcnow(),
            checkpoint_type=CheckpointType.SELECT,
            alternatives=[
                {"value": "A", "label": "Option A"},
                {"value": "B", "label": "Option B"},
            ],
        )

        response = _checkpoint_to_response(checkpoint)

        assert response.checkpoint_type == "select"
        assert response.alternatives == [
            {"value": "A", "label": "Option A"},
            {"value": "B", "label": "Option B"},
        ]


class TestQACheckpointCreation:
    """Tests for QA checkpoint creation from SubagentResult."""

    def test_subagent_result_with_questions_creates_qa_checkpoint(self):
        """Test that SubagentResult with questions triggers QA checkpoint creation."""
        from src.agents.llm_subagent import SubagentResult

        result = SubagentResult(
            success=True,
            output={"partial_work": "data"},
            questions=["What priority should this have?"],
            questions_context={"options": ["high", "medium", "low"]},
        )

        assert result.needs_clarification() is True
        assert result.questions == ["What priority should this have?"]
        assert result.questions_context == {"options": ["high", "medium", "low"]}

    def test_checkpoint_config_with_qa_type(self):
        """Test creating CheckpointConfig with QA type."""
        from src.domain.tasks.models import CheckpointConfig, CheckpointType

        config = CheckpointConfig(
            name="clarification_checkpoint",
            description="Agent needs clarification",
            checkpoint_type=CheckpointType.QA,
            questions=["What is your preferred output format?", "Who is the audience?"],
            context_data={"current_progress": "50%"},
        )

        assert config.checkpoint_type == CheckpointType.QA
        assert len(config.questions) == 2
        assert config.context_data == {"current_progress": "50%"}

        # Test serialization
        config_dict = config.to_dict()
        assert config_dict["checkpoint_type"] == "qa"
        assert config_dict["questions"] == ["What is your preferred output format?", "Who is the audience?"]

        # Test deserialization
        restored = CheckpointConfig.from_dict(config_dict)
        assert restored.checkpoint_type == CheckpointType.QA
        assert restored.questions == config.questions


class TestResolveQACheckpointEndpoint:
    """Tests for the resolve QA checkpoint endpoint model."""

    def test_resolve_qa_checkpoint_request_model(self):
        """Test the ResolveQACheckpointRequest model."""
        from src.api.routers.tasks import ResolveQACheckpointRequest

        request = ResolveQACheckpointRequest(
            answers={
                "What format?": "PDF",
                "What audience?": "Developers",
            },
            feedback="Thanks for asking!",
            learn_preference=True,
        )

        assert request.answers == {
            "What format?": "PDF",
            "What audience?": "Developers",
        }
        assert request.feedback == "Thanks for asking!"
        assert request.learn_preference is True

    def test_resolve_qa_checkpoint_request_minimal(self):
        """Test ResolveQACheckpointRequest with minimal fields."""
        from src.api.routers.tasks import ResolveQACheckpointRequest

        request = ResolveQACheckpointRequest(
            answers={"Question?": "Answer"},
        )

        assert request.answers == {"Question?": "Answer"}
        assert request.feedback is None
        assert request.learn_preference is True  # default


class TestCheckpointResponseModel:
    """Tests for the CheckpointResponse model."""

    def test_checkpoint_response_model_with_qa_fields(self):
        """Test CheckpointResponse model includes QA fields."""
        from src.api.routers.tasks import CheckpointResponse

        response = CheckpointResponse(
            task_id="task-123",
            step_id="step-1",
            checkpoint_name="qa_test",
            description="Test description",
            decision="pending",
            preview_data={},
            created_at=datetime.utcnow(),
            checkpoint_type="qa",
            questions=["Q1?", "Q2?"],
            context_data={"key": "value"},
        )

        assert response.checkpoint_type == "qa"
        assert response.questions == ["Q1?", "Q2?"]
        assert response.context_data == {"key": "value"}

    def test_checkpoint_response_model_defaults(self):
        """Test CheckpointResponse model has correct defaults."""
        from src.api.routers.tasks import CheckpointResponse

        response = CheckpointResponse(
            task_id="task-456",
            step_id="step-2",
            checkpoint_name="approval_test",
            description="Approval description",
            decision="pending",
            preview_data={"action": "test"},
            created_at=datetime.utcnow(),
        )

        # Default checkpoint_type should be "approval"
        assert response.checkpoint_type == "approval"
        assert response.questions is None
        assert response.context_data is None
        assert response.alternatives is None
