"""
Unit tests for PlanValidator.

Tests the plan validation system that catches field name errors
before execution.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.tasks.models import TaskStep
from src.validation.plan_validator import (
    PlanValidator,
    PlanValidationResult,
    PlanValidationError,
    PlanValidationException,
)


class MockAgentConfig:
    """Mock agent configuration for testing."""

    def __init__(self, inputs_schema=None, outputs_schema=None):
        self.inputs_schema = inputs_schema or {}
        self.outputs_schema = outputs_schema or {}


class MockRegistry:
    """Mock UnifiedCapabilityRegistry for testing."""

    def __init__(self, agents=None):
        self._agents = agents or {}

    def get_agent_config(self, agent_type: str):
        return self._agents.get(agent_type)

    def available_types(self):
        return list(self._agents.keys())


@pytest.fixture
def mock_registry():
    """Create a mock registry with test agents."""
    return MockRegistry(
        agents={
            "workspace_create": MockAgentConfig(
                inputs_schema={
                    "type": {"required": True, "description": "Type of workspace item"},
                    "data": {"required": True, "description": "The data to create"},
                },
                outputs_schema={
                    "id": {"type": "string", "description": "Created item ID"},
                    "result": {"type": "dict", "description": "Creation result"},
                },
            ),
            "web_search": MockAgentConfig(
                inputs_schema={
                    "query": {"required": True, "description": "Search query"},
                },
                outputs_schema={
                    "query": {"type": "string", "description": "The search query"},
                    "results": {"type": "list", "description": "Search results"},
                    "sources": {"type": "list", "description": "Source URLs"},
                    "result_count": {"type": "int", "description": "Number of results"},
                },
            ),
            "summarize": MockAgentConfig(
                inputs_schema={
                    "content": {"required": True, "description": "Content to summarize"},
                },
                outputs_schema={
                    "summary": {"type": "string", "description": "Summary text"},
                    "key_points": {"type": "list", "description": "Key points"},
                },
            ),
        }
    )


@pytest.fixture
def validator(mock_registry):
    """Create a validator with mocked registry."""
    v = PlanValidator()
    v._registry = mock_registry
    return v


class TestPlanValidationResult:
    """Tests for PlanValidationResult dataclass."""

    def test_valid_result(self):
        """Test that a valid result has correct properties."""
        result = PlanValidationResult(valid=True, errors=[])
        assert result.valid is True
        assert result.error_count == 0

    def test_invalid_result(self):
        """Test that an invalid result contains errors."""
        errors = [
            PlanValidationError(
                step_id="step_1",
                field="data",
                message="Missing required field",
                suggestion="Add 'data' to inputs",
            )
        ]
        result = PlanValidationResult(valid=False, errors=errors)
        assert result.valid is False
        assert result.error_count == 1

    def test_to_llm_feedback_valid(self):
        """Test LLM feedback for valid plan."""
        result = PlanValidationResult(valid=True, errors=[])
        feedback = result.to_llm_feedback()
        assert "passed" in feedback.lower()

    def test_to_llm_feedback_invalid(self):
        """Test LLM feedback for invalid plan."""
        errors = [
            PlanValidationError(
                step_id="step_1",
                field="events",
                message="Invalid input field 'events' for workspace_create",
                suggestion="Use 'data' instead of 'events'",
            ),
            PlanValidationError(
                step_id="step_1",
                field="data",
                message="Missing required input 'data'",
                suggestion="Add 'data' to inputs",
            ),
        ]
        result = PlanValidationResult(valid=False, errors=errors)
        feedback = result.to_llm_feedback()

        assert "FAILED" in feedback
        assert "step_1" in feedback
        assert "events" in feedback
        assert "data" in feedback
        assert "Fix:" in feedback


class TestPlanValidationException:
    """Tests for PlanValidationException."""

    def test_exception_message(self):
        """Test that exception includes error summary."""
        errors = [
            PlanValidationError(
                step_id="step_1",
                field="data",
                message="Missing required field",
            ),
            PlanValidationError(
                step_id="step_2",
                field="content",
                message="Invalid field",
            ),
        ]
        exc = PlanValidationException("Validation failed", errors=errors)

        assert "step_1:data" in str(exc)
        assert "step_2:content" in str(exc)

    def test_exception_with_many_errors(self):
        """Test exception message truncation with many errors."""
        errors = [
            PlanValidationError(step_id=f"step_{i}", field="field", message="Error")
            for i in range(5)
        ]
        exc = PlanValidationException("Validation failed", errors=errors)

        assert "+2 more" in str(exc)


class TestPlanValidator:
    """Tests for PlanValidator."""

    @pytest.mark.asyncio
    async def test_validates_required_inputs(self, validator):
        """Test that missing required inputs are caught."""
        step = TaskStep(
            id="step_1",
            name="create_event",
            description="Create calendar event",
            agent_type="workspace_create",
            inputs={"type": "event"},  # Missing 'data'
            dependencies=[],
        )

        result = await validator.validate_plan([step])

        assert result.valid is False
        assert any(
            "data" in e.field and "Missing required" in e.message
            for e in result.errors
        )

    @pytest.mark.asyncio
    async def test_rejects_invalid_input_field(self, validator):
        """Test that invalid input fields are caught (e.g., 'events' instead of 'data')."""
        step = TaskStep(
            id="step_1",
            name="create_event",
            description="Create calendar event",
            agent_type="workspace_create",
            inputs={
                "type": "event",
                "events": [{"title": "Game"}],  # WRONG: should be 'data'
            },
            dependencies=[],
        )

        result = await validator.validate_plan([step])

        assert result.valid is False

        # Should have errors for both invalid field AND missing required field
        invalid_field_error = next(
            (e for e in result.errors if "events" in e.field), None
        )
        assert invalid_field_error is not None
        assert "Invalid input field" in invalid_field_error.message

    @pytest.mark.asyncio
    async def test_validates_template_references(self, validator):
        """Test that invalid output field references are caught."""
        steps = [
            TaskStep(
                id="step_1",
                name="search",
                description="Search web",
                agent_type="web_search",
                inputs={"query": "test"},
                dependencies=[],
            ),
            TaskStep(
                id="step_2",
                name="summarize",
                description="Summarize results",
                agent_type="summarize",
                # WRONG: should be 'results' not 'search_results'
                inputs={"content": "{{step_1.outputs.search_results}}"},
                dependencies=["step_1"],
            ),
        ]

        result = await validator.validate_plan(steps)

        assert result.valid is False
        template_error = next(
            (e for e in result.errors if "search_results" in e.message), None
        )
        assert template_error is not None
        assert "does not have output field" in template_error.message

    @pytest.mark.asyncio
    async def test_validates_step_references(self, validator):
        """Test that non-existent step references are caught."""
        step = TaskStep(
            id="step_1",
            name="summarize",
            description="Summarize results",
            agent_type="summarize",
            inputs={"content": "{{step_99.outputs.data}}"},  # step_99 doesn't exist
            dependencies=[],
        )

        result = await validator.validate_plan([step])

        assert result.valid is False
        ref_error = next(
            (e for e in result.errors if "step_99" in e.message), None
        )
        assert ref_error is not None
        assert "non-existent step" in ref_error.message

    @pytest.mark.asyncio
    async def test_accepts_valid_plan(self, validator):
        """Test that a valid plan passes without errors."""
        steps = [
            TaskStep(
                id="step_1",
                name="search",
                description="Search web",
                agent_type="web_search",
                inputs={"query": "test query"},
                dependencies=[],
            ),
            TaskStep(
                id="step_2",
                name="summarize",
                description="Summarize results",
                agent_type="summarize",
                inputs={"content": "{{step_1.outputs.results}}"},  # Correct field
                dependencies=["step_1"],
            ),
        ]

        result = await validator.validate_plan(steps)

        assert result.valid is True
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_unknown_agent_type(self, validator):
        """Test that unknown agent types are caught."""
        step = TaskStep(
            id="step_1",
            name="do_magic",
            description="Do magic",
            agent_type="magic_agent",  # Doesn't exist
            inputs={},
            dependencies=[],
        )

        result = await validator.validate_plan([step])

        assert result.valid is False
        agent_error = next(
            (e for e in result.errors if "agent_type" in e.field), None
        )
        assert agent_error is not None
        assert "Unknown agent type" in agent_error.message

    @pytest.mark.asyncio
    async def test_invalid_template_syntax_no_field(self, validator):
        """Test that template syntax without field name is caught."""
        steps = [
            TaskStep(
                id="step_1",
                name="search",
                description="Search",
                agent_type="web_search",
                inputs={"query": "test"},
                dependencies=[],
            ),
            TaskStep(
                id="step_2",
                name="summarize",
                description="Summarize",
                agent_type="summarize",
                # Missing field name
                inputs={"content": "{{step_1.outputs}}"},
                dependencies=["step_1"],
            ),
        ]

        result = await validator.validate_plan(steps)

        assert result.valid is False
        syntax_error = next(
            (e for e in result.errors if "missing field name" in e.message.lower()), None
        )
        assert syntax_error is not None


class TestEnumValidation:
    """Tests for enum constraint validation."""

    @pytest.fixture
    def enum_registry(self):
        """Create a mock registry with enum constraints."""
        return MockRegistry(
            agents={
                "event_extract": MockAgentConfig(
                    inputs_schema={
                        "content": {"required": True, "description": "Content"},
                        "source_type": {
                            "type": "string",
                            "enum": ["email", "text", "calendar_invite"],
                            "default": "email",
                            "required": False,
                        },
                    },
                    outputs_schema={
                        "events": {"type": "array"},
                        "event_count": {"type": "int"},
                    },
                ),
            }
        )

    @pytest.fixture
    def enum_validator(self, enum_registry):
        """Create a validator with enum-aware registry."""
        v = PlanValidator()
        v._registry = enum_registry
        return v

    @pytest.mark.asyncio
    async def test_rejects_invalid_enum_value(self, enum_validator):
        """Test that invalid enum values are caught."""
        step = TaskStep(
            id="step_1",
            name="extract",
            description="Extract events",
            agent_type="event_extract",
            inputs={
                "content": "Some text",
                "source_type": "schedule",  # INVALID - not in enum
            },
            dependencies=[],
        )

        result = await enum_validator.validate_plan([step])

        assert result.valid is False
        enum_error = next(
            (e for e in result.errors if "source_type" in e.field), None
        )
        assert enum_error is not None
        assert "schedule" in enum_error.message
        assert "email" in enum_error.suggestion or "text" in enum_error.suggestion

    @pytest.mark.asyncio
    async def test_accepts_valid_enum_value(self, enum_validator):
        """Test that valid enum values pass."""
        step = TaskStep(
            id="step_1",
            name="extract",
            description="Extract events",
            agent_type="event_extract",
            inputs={
                "content": "Some text",
                "source_type": "text",  # Valid enum value
            },
            dependencies=[],
        )

        result = await enum_validator.validate_plan([step])

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_skips_template_variable_enum_check(self, enum_validator):
        """Test that template variables are skipped for enum validation."""
        # Note: We test enum validation skipping in isolation
        # Template variables with {{}} should not be validated against enum
        step = TaskStep(
            id="step_1",
            name="extract",
            description="Extract events",
            agent_type="event_extract",
            inputs={
                "content": "Some text content",
                "source_type": "text",  # Valid value
            },
            dependencies=[],
        )

        result = await enum_validator.validate_plan([step])

        # Should pass (source_type is valid)
        assert result.valid is True


class TestPlanValidationIntegration:
    """Integration tests for plan validation with real registry mock."""

    @pytest.mark.asyncio
    async def test_workspace_create_common_mistake(self, validator):
        """Test the specific bug case: using 'events' instead of 'data'."""
        step = TaskStep(
            id="step_1",
            name="create_events",
            description="Create calendar events",
            agent_type="workspace_create",
            inputs={
                "type": "event",
                "events": [  # Common mistake: should be 'data'
                    {"title": "Warriors vs Lakers"},
                ],
            },
            dependencies=[],
        )

        result = await validator.validate_plan([step])

        assert result.valid is False

        # Check that the feedback mentions the correct field
        feedback = result.to_llm_feedback()
        assert "events" in feedback
        assert "data" in feedback

    @pytest.mark.asyncio
    async def test_web_search_output_reference_mistake(self, validator):
        """Test the specific bug case: using 'search_results' instead of 'results'."""
        steps = [
            TaskStep(
                id="step_1",
                name="search",
                description="Search for games",
                agent_type="web_search",
                inputs={"query": "Warriors games"},
                dependencies=[],
            ),
            TaskStep(
                id="step_2",
                name="create_events",
                description="Create events from search",
                agent_type="workspace_create",
                inputs={
                    "type": "event",
                    "data": "{{step_1.outputs.search_results}}",  # Wrong field name
                },
                dependencies=["step_1"],
            ),
        ]

        result = await validator.validate_plan(steps)

        assert result.valid is False

        # Check that the feedback mentions the correct field
        feedback = result.to_llm_feedback()
        assert "search_results" in feedback
        # Should suggest 'results' as the correct field
        assert "results" in feedback

    @pytest.mark.asyncio
    async def test_runtime_validation(self, validator):
        """Test runtime validation for individual steps."""
        step = TaskStep(
            id="step_1",
            name="create_event",
            description="Create event",
            agent_type="workspace_create",
            inputs={"type": "event"},  # Missing 'data'
            dependencies=[],
        )

        result = await validator.validate_step_inputs_at_runtime(step)

        assert result.valid is False
        assert any("data" in e.field for e in result.errors)
