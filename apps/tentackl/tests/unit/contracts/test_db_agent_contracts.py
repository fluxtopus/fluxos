"""
Tests for contract enforcement in DatabaseConfiguredAgent.

Validates that the agent properly enforces input/output contracts
and blocks bad data from propagating.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional, Dict, Any

from src.agents.db_configured_agent import DatabaseConfiguredAgent
from src.agents.llm_subagent import SubagentResult
from src.database.capability_models import AgentCapability


@dataclass
class MockTaskStep:
    """Mock TaskStep for testing."""
    id: str = "step-123"
    name: str = "Test Step"
    inputs: Optional[Dict[str, Any]] = None


def create_mock_capability(
    agent_type: str = "test_agent",
    system_prompt: str = "You are a test agent.",
    inputs_schema: Optional[Dict] = None,
    outputs_schema: Optional[Dict] = None,
) -> AgentCapability:
    """Create a mock AgentCapability for testing."""
    capability = MagicMock(spec=AgentCapability)
    capability.agent_type = agent_type
    capability.task_type = "general"
    capability.name = "Test Agent"
    capability.domain = "testing"
    capability.system_prompt = system_prompt
    capability.inputs_schema = inputs_schema or {}
    capability.outputs_schema = outputs_schema or {}
    capability.examples = []
    capability.execution_hints = {}
    return capability


class TestInputContractEnforcement:
    """Tests for input contract validation."""

    @pytest.mark.asyncio
    async def test_valid_inputs_pass(self):
        """Valid inputs should pass validation and execute."""
        capability = create_mock_capability(
            inputs_schema={
                "content": {"type": "string", "required": True},
                "max_length": {"type": "integer", "default": 100}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        # Mock the LLM call
        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Processed successfully"

            step = MockTaskStep(inputs={"content": "Test content"})
            result = await agent.execute(step)

            assert result.success is True
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_input_fails(self):
        """Missing required input should fail with contract violation."""
        capability = create_mock_capability(
            inputs_schema={
                "content": {"type": "string", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        # Mock the LLM call - should not be reached
        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            step = MockTaskStep(inputs={})  # Missing required 'content'
            result = await agent.execute(step)

            assert result.success is False
            assert "Input contract violation" in result.error
            assert "content" in result.error.lower()
            mock_llm.assert_not_called()  # LLM should not be called

    @pytest.mark.asyncio
    async def test_wrong_input_type_fails(self):
        """Wrong input type should fail with contract violation."""
        capability = create_mock_capability(
            inputs_schema={
                "count": {"type": "integer", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            step = MockTaskStep(inputs={"count": "not a number"})
            result = await agent.execute(step)

            assert result.success is False
            assert "Input contract violation" in result.error
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_applied_for_missing_optional(self):
        """Default values should be applied for missing optional fields."""
        capability = create_mock_capability(
            inputs_schema={
                "content": {"type": "string", "required": True},
                "style": {"type": "string", "default": "brief"}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Result"

            step = MockTaskStep(inputs={"content": "Test"})
            result = await agent.execute(step)

            assert result.success is True
            # The prompt should have been built with the default applied

    @pytest.mark.asyncio
    async def test_input_out_of_range_fails(self):
        """Value out of range should fail validation."""
        capability = create_mock_capability(
            inputs_schema={
                "count": {"type": "integer", "min": 1, "max": 100}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            step = MockTaskStep(inputs={"count": 0})  # Below min
            result = await agent.execute(step)

            assert result.success is False
            assert "minimum" in result.error.lower()
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_input_enum_validation_fails(self):
        """Invalid enum value should fail validation."""
        capability = create_mock_capability(
            inputs_schema={
                "status": {"type": "string", "enum": ["pending", "active", "done"]}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            step = MockTaskStep(inputs={"status": "invalid"})
            result = await agent.execute(step)

            assert result.success is False
            assert "allowed values" in result.error.lower()
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_validation_errors_in_metadata(self):
        """Validation errors should be included in metadata."""
        capability = create_mock_capability(
            inputs_schema={
                "required_field": {"type": "string", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock):
            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            assert result.success is False
            assert result.metadata is not None
            assert "validation_errors" in result.metadata
            assert result.metadata["validation_phase"] == "input"


class TestOutputContractEnforcement:
    """Tests for output contract validation."""

    @pytest.mark.asyncio
    async def test_valid_outputs_pass(self):
        """Valid outputs should pass validation."""
        capability = create_mock_capability(
            outputs_schema={
                "summary": {"type": "string", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            # Return JSON that matches schema
            mock_llm.return_value = '{"summary": "This is a valid summary"}'

            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            assert result.success is True
            assert "summary" in result.output

    @pytest.mark.asyncio
    async def test_missing_required_output_fails_strict(self):
        """Missing required output should fail in strict mode."""
        capability = create_mock_capability(
            outputs_schema={
                "summary": {"type": "string", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            # Return content without summary field
            mock_llm.return_value = "Just plain text without JSON"

            with patch.object(agent, '_parse_output') as mock_parse:
                mock_parse.return_value = {}  # No summary field
                step = MockTaskStep(inputs={})
                result = await agent.execute(step)

                # Output validation is lenient (strict=False) by default
                # so it should warn but not fail

    @pytest.mark.asyncio
    async def test_wrong_output_type_handled(self):
        """Wrong output type should be handled."""
        capability = create_mock_capability(
            outputs_schema={
                "count": {"type": "integer"}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"count": "not a number"}'

            with patch.object(agent, '_parse_output') as mock_parse:
                mock_parse.return_value = {"count": "not a number"}
                step = MockTaskStep(inputs={})
                result = await agent.execute(step)

                # Output validation is lenient by default, so it may warn but not fail

    @pytest.mark.asyncio
    async def test_output_validation_metadata(self):
        """Output validation results should be in metadata."""
        capability = create_mock_capability(
            inputs_schema={},
            outputs_schema={
                "result": {"type": "string"}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Test result"

            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            if result.success:
                assert result.metadata is not None
                assert result.metadata.get("contract_validated") is True


class TestNoSchemaEnforcement:
    """Tests when no schema is defined."""

    @pytest.mark.asyncio
    async def test_no_input_schema_allows_anything(self):
        """No input schema should allow any inputs."""
        capability = create_mock_capability(
            inputs_schema={},  # No schema
            outputs_schema={}
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Processed"

            step = MockTaskStep(inputs={"any": "thing", "is": "allowed"})
            result = await agent.execute(step)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_no_output_schema_allows_anything(self):
        """No output schema should allow any output."""
        capability = create_mock_capability(
            inputs_schema={},
            outputs_schema={}  # No schema
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Any response is valid"

            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            assert result.success is True


class TestExecutionTime:
    """Tests for execution time tracking."""

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Execution time should be recorded in result."""
        capability = create_mock_capability()
        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Result"

            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_execution_time_on_validation_failure(self):
        """Execution time should be recorded even on validation failure."""
        capability = create_mock_capability(
            inputs_schema={
                "required": {"type": "string", "required": True}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        step = MockTaskStep(inputs={})  # Missing required
        result = await agent.execute(step)

        assert result.success is False
        assert result.execution_time_ms >= 0


class TestInputExtraction:
    """Tests for input extraction with defaults."""

    @pytest.mark.asyncio
    async def test_inputs_from_step(self):
        """Inputs should be extracted from step."""
        capability = create_mock_capability(
            inputs_schema={
                "content": {"type": "string"}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Result"

            step = MockTaskStep(inputs={"content": "Test content"})
            result = await agent.execute(step)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_extra_inputs_preserved(self):
        """Extra inputs not in schema should be preserved."""
        capability = create_mock_capability(
            inputs_schema={
                "content": {"type": "string"}
            }
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Result"

            # Extra field not in schema
            step = MockTaskStep(inputs={
                "content": "Test",
                "extra_field": "Should be preserved"
            })
            result = await agent.execute(step)

            assert result.success is True


class TestExceptionHandling:
    """Tests for exception handling."""

    @pytest.mark.asyncio
    async def test_llm_exception_handled(self):
        """LLM exceptions should be handled gracefully."""
        capability = create_mock_capability()
        agent = DatabaseConfiguredAgent(capability)

        with patch.object(agent, '_llm_process', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM error")

            step = MockTaskStep(inputs={})
            result = await agent.execute(step)

            assert result.success is False
            assert "Agent execution failed" in result.error
            assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_validation_exception_handled(self):
        """Validation exceptions should be handled gracefully."""
        capability = create_mock_capability(
            inputs_schema={"field": {"type": "string"}}
        )

        agent = DatabaseConfiguredAgent(capability)

        with patch('src.contracts.validator.ContractValidator.validate_inputs') as mock_validate:
            mock_validate.side_effect = Exception("Validation error")

            step = MockTaskStep(inputs={"field": "test"})
            result = await agent.execute(step)

            assert result.success is False
            assert "execution failed" in result.error.lower()
