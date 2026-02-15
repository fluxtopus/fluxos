"""Unit tests for the agent creation plugin.

The agent creation plugin now uses the unified capabilities system
(capabilities_agents table) instead of the deprecated AgentRegistryManager.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
import uuid

from src.plugins.agent_creation_plugin import (
    create_agent_handler,
    CREATE_AGENT_PLUGIN_DEFINITION,
)


@dataclass
class MockIdeationResult:
    suggested_name: str = "test_agent"
    suggested_type: str = "compose"
    suggested_category: str = "content"
    suggested_capabilities: list = None
    suggested_keywords: list = None
    brief: str = "A test agent for unit testing"
    reasoning: str = "Test reasoning"

    def __post_init__(self):
        if self.suggested_capabilities is None:
            self.suggested_capabilities = ["http_fetch"]
        if self.suggested_keywords is None:
            self.suggested_keywords = ["test", "mock"]


@dataclass
class MockGenerationResult:
    yaml_spec: str = """
name: test_agent
type: compose
version: "1.0.0"
description: A test agent
"""
    parsed_spec: dict = None
    name: str = "test_agent"
    version: str = "1.0.0"
    validation_warnings: list = None

    def __post_init__(self):
        if self.parsed_spec is None:
            self.parsed_spec = {"name": "test_agent", "type": "compose"}
        if self.validation_warnings is None:
            self.validation_warnings = []


def create_mock_generator():
    """Create a mock AgentGeneratorService."""
    mock_service = MagicMock()
    mock_service.ideate = AsyncMock(return_value=MockIdeationResult())
    mock_service.generate = AsyncMock(return_value=MockGenerationResult())
    return mock_service


def create_mock_use_cases(capability_payload=None):
    """Create mock capability use cases."""
    if capability_payload is None:
        capability_payload = {
            "id": uuid.uuid4(),
            "name": "test_agent",
            "domain": "content",
            "version": 1,
            "agent_type": "test_agent",
            "inputs_schema": {"input": {"type": "string"}},
            "outputs_schema": {},
            "tags": ["test"],
        }
    mock_use_cases = AsyncMock()
    mock_use_cases.create_capability = AsyncMock(
        return_value={"capability": capability_payload}
    )
    return mock_use_cases, capability_payload


class TestCreateAgentHandler:
    """Tests for create_agent_handler function."""

    @pytest.mark.asyncio
    async def test_missing_description_returns_error(self):
        """Test that missing agent_description returns an error."""
        result = await create_agent_handler({})
        assert result["success"] is False
        assert "agent_description is required" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_description_returns_error(self):
        """Test that empty agent_description returns an error."""
        result = await create_agent_handler({"agent_description": ""})
        assert result["success"] is False
        assert "agent_description is required" in result["error"]

    @pytest.mark.asyncio
    async def test_tags_string_parsing(self):
        """Test that comma-separated tags string is parsed correctly."""
        mock_service = create_mock_generator()
        mock_use_cases, _payload = create_mock_use_cases()

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ), patch(
            "src.plugins.agent_creation_plugin._get_capability_use_cases",
            return_value=mock_use_cases,
        ):
            await create_agent_handler({
                "agent_description": "Test agent",
                "tags": "tag1, tag2, tag3",
                "organization_id": "org-123",
            })

            # Verify tags were parsed correctly
            call_kwargs = mock_use_cases.create_capability.call_args.kwargs
            assert call_kwargs["tags"] == ["tag1", "tag2", "tag3"]

    @pytest.mark.asyncio
    async def test_successful_agent_creation(self):
        """Test successful agent creation flow."""
        mock_service = create_mock_generator()
        mock_use_cases, payload = create_mock_use_cases(
            capability_payload={
                "id": uuid.uuid4(),
                "name": "test_agent",
                "domain": "automation",
                "version": 1,
                "agent_type": "test_agent",
                "inputs_schema": {"input": {"type": "string"}},
                "outputs_schema": {},
                "tags": ["meals", "planning"],
            }
        )

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ), patch(
            "src.plugins.agent_creation_plugin._get_capability_use_cases",
            return_value=mock_use_cases,
        ):
            result = await create_agent_handler({
                "agent_description": "An agent that creates meal plans",
                "agent_name": "meal_planner",
                "category": "automation",
                "tags": ["meals", "planning"],
                "organization_id": "org-123",
            })

            assert result["success"] is True
            assert "capability_id" in result or "spec_id" in result
            assert result["agent_name"] == payload["name"]
            assert result["version"] == payload["version"]
            assert result["published"] is True  # Capabilities are active immediately
            assert "created" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test that validation errors are handled properly."""
        mock_service = MagicMock()
        mock_service.ideate = AsyncMock(side_effect=ValueError("Invalid agent description"))

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ):
            result = await create_agent_handler({
                "agent_description": "Invalid",
                "organization_id": "org-123",
            })

            assert result["success"] is False
            assert "validation failed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self):
        """Test that generic exceptions are handled properly."""
        mock_service = MagicMock()
        mock_service.ideate = AsyncMock(side_effect=Exception("Unexpected error"))

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ):
            result = await create_agent_handler({
                "agent_description": "Test agent",
                "organization_id": "org-123",
            })

            assert result["success"] is False
            assert "Failed to create agent" in result["error"]

    @pytest.mark.asyncio
    async def test_uses_suggested_name_if_not_provided(self):
        """Test that suggested name from ideation is used if name not provided."""
        mock_service = create_mock_generator()
        mock_use_cases, _payload = create_mock_use_cases()
        mock_service.ideate = AsyncMock(return_value=MockIdeationResult(
            suggested_name="auto_generated_name"
        ))

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ), patch(
            "src.plugins.agent_creation_plugin._get_capability_use_cases",
            return_value=mock_use_cases,
        ):
            await create_agent_handler({
                "agent_description": "Test agent",
                # No agent_name provided
                "organization_id": "org-123",
            })

            # Verify generate was called with auto-generated name
            call_kwargs = mock_service.generate.call_args.kwargs
            assert call_kwargs["name"] == "auto_generated_name"

    @pytest.mark.asyncio
    async def test_db_cleanup_on_success(self):
        """Test that capability use cases are invoked on success."""
        mock_service = create_mock_generator()
        mock_use_cases, _payload = create_mock_use_cases()

        with patch(
            "src.infrastructure.agents.agent_generator_service.AgentGeneratorService",
            return_value=mock_service,
        ), patch(
            "src.plugins.agent_creation_plugin._get_capability_use_cases",
            return_value=mock_use_cases,
        ):
            await create_agent_handler({
                "agent_description": "Test agent",
                "organization_id": "org-123",
            })

            assert mock_use_cases.create_capability.called


class TestPluginDefinition:
    """Tests for the plugin definition."""

    def test_plugin_definition_structure(self):
        """Test that plugin definition has required fields."""
        assert "name" in CREATE_AGENT_PLUGIN_DEFINITION
        assert "description" in CREATE_AGENT_PLUGIN_DEFINITION
        assert "handler" in CREATE_AGENT_PLUGIN_DEFINITION
        assert "inputs_schema" in CREATE_AGENT_PLUGIN_DEFINITION
        assert "outputs_schema" in CREATE_AGENT_PLUGIN_DEFINITION

    def test_plugin_name_is_create_agent(self):
        """Test that plugin name is 'create_agent'."""
        assert CREATE_AGENT_PLUGIN_DEFINITION["name"] == "create_agent"

    def test_inputs_schema_has_required_field(self):
        """Test that inputs_schema has agent_description as required."""
        inputs_schema = CREATE_AGENT_PLUGIN_DEFINITION["inputs_schema"]
        assert "agent_description" in inputs_schema["properties"]
        assert "agent_description" in inputs_schema["required"]

    def test_outputs_schema_has_expected_fields(self):
        """Test that outputs_schema has expected fields."""
        outputs_schema = CREATE_AGENT_PLUGIN_DEFINITION["outputs_schema"]
        expected_fields = ["success", "capability_id", "spec_id", "agent_name", "version", "error"]
        for field in expected_fields:
            assert field in outputs_schema["properties"]

    def test_execution_hints_require_checkpoint(self):
        """Test that execution hints require checkpoint."""
        hints = CREATE_AGENT_PLUGIN_DEFINITION["execution_hints"]
        assert hints["requires_checkpoint"] is True

    def test_handler_is_callable(self):
        """Test that handler is a callable function."""
        assert callable(CREATE_AGENT_PLUGIN_DEFINITION["handler"])
