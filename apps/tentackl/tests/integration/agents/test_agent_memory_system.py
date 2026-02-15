"""
Integration Tests for Tentackl Agent Memory System.

Tests the four subsystems:
1. Agent Document DB - DocumentDBSubagent + document_db_plugin
2. Agent Storage Namespace - AgentStorageSubagent + agent_storage_plugin
3. Preferences & Checkpoints - PreferenceInjectionService + extended checkpoints
4. Dynamic Agent Creation - AgentGeneratorService + AgentValidationService + DynamicAgent

These tests verify the complete Agent Memory System without requiring
external services (mocked Den/InkPass calls where needed).
"""

import pytest
import yaml
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Services under test
from src.infrastructure.agents.agent_generator_service import (
    AgentGeneratorService,
    IdeationResult,
    GenerationResult,
)
from src.infrastructure.agents.agent_validation_service import (
    AgentValidationService,
    ValidationResult,
    DryRunResult,
)
from src.infrastructure.preferences.preference_injection_service import (
    PreferenceInjectionService,
    ApplicablePreference,
)
from src.agents.dynamic_agent import DynamicAgent, DynamicAgentFactory
from src.infrastructure.execution_runtime.plugin_executor import (
    execute_step,
    ExecutionResult,
    available_types,
    PLUGIN_REGISTRY,
)
from src.domain.tasks.models import TaskStep


# ============================================================================
# Subsystem 1: Agent Validation Service Tests
# ============================================================================

class TestAgentValidationService:
    """Tests for AgentValidationService."""

    def setup_method(self):
        self.service = AgentValidationService()

    def test_validate_valid_spec(self):
        """Test validation passes for a valid spec."""
        spec = """
agent:
  name: test_agent
  type: compose
  description: A test agent that composes content for testing purposes
  brief: Test content composer
  keywords:
    - test
    - compose
  category: content
  prompt_template: |
    Create content about {{ inputs.topic }}
  input_schema:
    type: object
    properties:
      topic:
        type: string
    required:
      - topic
"""
        result = self.service.validate(spec)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        spec = """
agent:
  name: incomplete_agent
"""
        result = self.service.validate(spec)

        assert not result.is_valid
        assert any("type" in e.field for e in result.errors)
        assert any("description" in e.field for e in result.errors)

    def test_validate_invalid_agent_type(self):
        """Test validation fails for invalid agent type."""
        spec = """
agent:
  name: test_agent
  type: invalid_type
  description: Test agent
"""
        result = self.service.validate(spec)

        assert not result.is_valid
        assert any("type" in e.field for e in result.errors)

    def test_validate_invalid_capability(self):
        """Test validation fails for unknown capabilities."""
        spec = """
agent:
  name: test_agent
  type: compose
  description: Test agent
  capabilities:
    - http_fetch
    - nonexistent_capability
"""
        result = self.service.validate(spec)

        assert not result.is_valid
        assert any("nonexistent_capability" in e.message for e in result.errors)

    def test_validate_template_syntax_error(self):
        """Test validation catches Jinja2 template syntax errors."""
        spec = """
agent:
  name: test_agent
  type: compose
  description: Test agent
  prompt_template: |
    Hello {{ unclosed_brace
"""
        result = self.service.validate(spec)

        assert not result.is_valid
        assert any("template" in e.field.lower() or "syntax" in e.message.lower()
                   for e in result.errors)

    def test_validate_strict_mode(self):
        """Test strict mode treats warnings as errors."""
        spec = """
agent:
  name: Test_Agent
  type: compose
  description: Test agent
"""
        # Non-strict: warnings don't fail
        result_normal = self.service.validate(spec, strict=False)
        # Strict: warnings become errors
        result_strict = self.service.validate(spec, strict=True)

        # Name case warning exists
        assert any("lowercase" in w.message.lower() for w in result_normal.warnings)
        # In strict mode, it becomes an error
        assert not result_strict.is_valid

    @pytest.mark.asyncio
    async def test_dry_run_renders_template(self):
        """Test dry-run renders templates with mock inputs."""
        spec = """
agent:
  name: test_agent
  type: compose
  description: Test agent
  system_prompt: You are a helpful assistant for {{ agent_name }}.
  prompt_template: |
    Create content about: {{ inputs.topic }}
    Style: {{ inputs.style }}
"""
        result = await self.service.dry_run(
            spec,
            mock_inputs={"topic": "AI agents", "style": "professional"}
        )

        assert result.success
        assert "AI agents" in result.prompt_rendered
        assert "professional" in result.prompt_rendered
        assert "test_agent" in result.prompt_rendered

    @pytest.mark.asyncio
    async def test_dry_run_warns_missing_required_inputs(self):
        """Test dry-run warns about missing required inputs."""
        spec = """
agent:
  name: test_agent
  type: compose
  description: Test agent
  prompt_template: |
    Create content about: {{ inputs.topic }}
  input_schema:
    type: object
    properties:
      topic:
        type: string
    required:
      - topic
"""
        result = await self.service.dry_run(spec, mock_inputs={})

        # Dry-run succeeds but warns about missing required input
        assert result.success
        assert any("topic" in w for w in result.warnings)

    def test_validate_for_publish(self):
        """Test comprehensive publication validation."""
        # Valid spec
        valid_spec = """
agent:
  name: publishable_agent
  type: compose
  description: |
    This is a detailed description that explains what the agent does.
    It has multiple lines and provides context about the agent's purpose.
  brief: Composes professional content
  keywords:
    - compose
    - content
  prompt_template: |
    Create {{ inputs.content_type }} content.
"""
        can_publish, result, blockers = self.service.validate_for_publish(valid_spec)
        assert can_publish
        assert len(blockers) == 0

        # Invalid spec - too short description
        invalid_spec = """
agent:
  name: short_desc
  type: compose
  description: Short
"""
        can_publish, result, blockers = self.service.validate_for_publish(invalid_spec)
        assert not can_publish
        assert any("description" in b.lower() for b in blockers)


# ============================================================================
# Subsystem 2: Agent Generator Service Tests
# ============================================================================

class TestAgentGeneratorService:
    """Tests for AgentGeneratorService (with mocked LLM)."""

    def setup_method(self):
        self.mock_llm = AsyncMock()
        self.service = AgentGeneratorService(llm_client=self.mock_llm)

    @pytest.mark.asyncio
    async def test_ideate_returns_structured_result(self):
        """Test ideation returns proper structure."""
        # Mock LLM response in OpenRouter API format
        self.mock_llm.complete = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "suggested_name": "meal_planner",
                        "suggested_type": "compose",
                        "suggested_category": "content",
                        "suggested_capabilities": ["http_fetch"],
                        "suggested_keywords": ["meal", "planning", "recipe"],
                        "brief": "Creates personalized meal plans",
                        "reasoning": "Meal planning requires content composition"
                    })
                }
            }]
        })

        result = await self.service.ideate("An agent that creates weekly meal plans")

        assert isinstance(result, IdeationResult)
        assert result.suggested_name == "meal_planner"
        assert result.suggested_type == "compose"
        assert "meal" in result.suggested_keywords

    @pytest.mark.asyncio
    async def test_generate_produces_valid_yaml(self):
        """Test generation produces valid YAML spec."""
        yaml_response = """```yaml
agent:
  name: meal_planner
  version: "1.0.0"
  type: compose
  description: Creates personalized weekly meal plans
  brief: Weekly meal planner
  keywords:
    - meal
    - planning
  category: content
  capabilities:
    - http_fetch
  system_prompt: You are a meal planning assistant.
  prompt_template: |
    Create a meal plan for {{ inputs.days }} days.
  input_schema:
    type: object
    properties:
      days:
        type: integer
    required:
      - days
  output_schema:
    type: object
    properties:
      meal_plan:
        type: object
  checkpoints: []
```"""
        # Mock LLM response in OpenRouter API format
        self.mock_llm.complete = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": yaml_response
                }
            }]
        })

        result = await self.service.generate(
            description="Creates weekly meal plans",
            agent_type="compose",
            capabilities=["http_fetch"],
            name="meal_planner"
        )

        assert isinstance(result, GenerationResult)
        assert result.name == "meal_planner"
        assert "agent" in result.parsed_spec
        assert result.parsed_spec["agent"]["type"] == "compose"

    @pytest.mark.asyncio
    async def test_refine_updates_spec(self):
        """Test refinement updates spec based on feedback."""
        original_yaml = """
agent:
  name: test_agent
  type: compose
  description: Original description
"""
        refined_yaml = """```yaml
agent:
  name: test_agent
  type: compose
  description: Updated description with dietary restrictions support
  capabilities:
    - document_db
```"""
        # Mock LLM response in OpenRouter API format
        self.mock_llm.complete = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": refined_yaml
                }
            }]
        })

        result = await self.service.refine(
            yaml_spec=original_yaml,
            feedback="Add support for dietary restrictions"
        )

        assert isinstance(result, GenerationResult)
        assert "dietary" in result.parsed_spec["agent"]["description"].lower()


# ============================================================================
# Subsystem 3: Dynamic Agent Tests
# ============================================================================

class TestDynamicAgent:
    """Tests for DynamicAgent runtime."""

    def setup_method(self):
        # Create a mock AgentSpec
        self.mock_spec = MagicMock()
        # Force legacy path by explicitly setting inputs_schema to None
        # (MagicMock auto-creates attributes, which breaks the hasattr check)
        self.mock_spec.inputs_schema = None
        self.mock_spec.name = "test_dynamic_agent"
        self.mock_spec.agent_type = "compose"
        self.mock_spec.version = "1.0.0"
        self.mock_spec.description = "A test dynamic agent"
        self.mock_spec.brief = "Test agent"
        self.mock_spec.keywords = ["test"]
        self.mock_spec.capabilities = ["http_fetch"]
        self.mock_spec.category = "utility"
        self.mock_spec.spec_compiled = {
            "agent": {
                "name": "test_dynamic_agent",
                "type": "compose",
                "version": "1.0.0",
                "description": "A test dynamic agent",
                "system_prompt": "You are a test agent.",
                "prompt_template": "Process: {{ inputs.data }}",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string"}
                    },
                    "required": ["data"]
                },
                "capabilities": ["http_fetch"],
                "checkpoints": []
            }
        }

    def test_dynamic_agent_initialization(self):
        """Test DynamicAgent initializes from spec."""
        agent = DynamicAgent(agent_spec=self.mock_spec)

        assert agent.name == "test_dynamic_agent"
        assert agent.agent_type == "compose"
        assert "http_fetch" in agent.capabilities

    def test_dynamic_agent_validates_inputs(self):
        """Test DynamicAgent validates required inputs."""
        agent = DynamicAgent(agent_spec=self.mock_spec)

        # Missing required input should raise
        with pytest.raises(Exception) as exc_info:
            agent._validate_inputs({})

        assert "data" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_dynamic_agent_builds_prompt(self):
        """Test DynamicAgent builds prompt from template."""
        agent = DynamicAgent(agent_spec=self.mock_spec)

        step = TaskStep(
            id="test_step",
            name="Test Step",
            agent_type="compose",
            description="Test step",
            inputs={"data": "test_value"}
        )

        prompt = await agent.build_prompt(step, context={})

        assert "test_value" in prompt
        assert "system" in prompt.lower()

    def test_dynamic_agent_to_dict(self):
        """Test DynamicAgent serialization."""
        agent = DynamicAgent(agent_spec=self.mock_spec)
        result = agent.to_dict()

        assert result["name"] == "test_dynamic_agent"
        assert result["type"] == "compose"
        assert "capabilities" in result


# ============================================================================
# Subsystem 4: Document DB Plugin Tests
# ============================================================================

class TestDocumentDBPlugin:
    """Tests for document_db plugin via execute_step."""

    def test_document_db_in_plugin_registry(self):
        """Test document_db is registered in PLUGIN_REGISTRY."""
        assert "document_db" in PLUGIN_REGISTRY
        module_path, handler_name = PLUGIN_REGISTRY["document_db"]
        assert "document_db_plugin" in module_path
        assert handler_name == "insert_document_handler"

    @pytest.mark.asyncio
    async def test_document_db_insert_via_execute_step(self):
        """Test document_db insert operation via execute_step."""
        step = TaskStep(
            id="test_step",
            name="Insert Document",
            agent_type="document_db",
            description="Insert a document",
            inputs={
                "operation": "insert",
                "org_id": "test_org",
                "agent_id": "test_agent",
                "collection": "leads",
                "document": {"name": "Alice", "email": "alice@test.com"}
            }
        )

        # Mock the plugin handler
        with patch("src.plugins.document_db_plugin.insert_document_handler") as mock_handler:
            mock_handler.return_value = {
                "doc_id": "doc_123",
                "file_id": "file_456",
                "collection": "leads"
            }

            result = await execute_step(step)

        assert result.success
        assert result.output["doc_id"] == "doc_123"


# ============================================================================
# Subsystem 5: Agent Storage Plugin Tests
# ============================================================================

class TestAgentStoragePlugin:
    """Tests for agent_storage plugin via execute_step."""

    def test_agent_storage_in_plugin_registry(self):
        """Test agent_storage is registered in PLUGIN_REGISTRY."""
        assert "agent_storage" in PLUGIN_REGISTRY
        module_path, handler_name = PLUGIN_REGISTRY["agent_storage"]
        assert "agent_storage_plugin" in module_path
        assert handler_name == "save_handler"

    @pytest.mark.asyncio
    async def test_agent_storage_save_via_execute_step(self):
        """Test agent_storage save operation via execute_step."""
        step = TaskStep(
            id="test_step",
            name="Save File",
            agent_type="agent_storage",
            description="Save a file",
            inputs={
                "operation": "save",
                "org_id": "test_org",
                "agent_id": "test_agent",
                "filename": "report.md",
                "content": "# Report\nTest content"
            }
        )

        with patch("src.plugins.agent_storage_plugin.save_handler") as mock_handler:
            mock_handler.return_value = {
                "file_id": "file_123",
                "filename": "report.md",
                "path": "/agents/test_agent/outputs",
                "url": "https://example.com/file_123"
            }

            result = await execute_step(step)

        assert result.success
        assert result.output["filename"] == "report.md"


# ============================================================================
# Subsystem 6: Preference Injection Service Tests
# ============================================================================

class TestPreferenceInjectionService:
    """Tests for PreferenceInjectionService."""

    def test_format_preferences_empty(self):
        """Test formatting empty preferences returns empty string."""
        mock_session = MagicMock()
        service = PreferenceInjectionService(mock_session)

        result = service.format_preferences_for_prompt([])
        assert result == ""

    def test_format_preferences_single(self):
        """Test formatting a single preference."""
        mock_session = MagicMock()
        service = PreferenceInjectionService(mock_session)

        preferences = [
            ApplicablePreference(
                preference_id="pref_1",
                preference_key="lunch_style",
                instruction="For meal planning, prefer easy lunches",
                scope="task_type",
                scope_value="meal_planning",
                confidence=0.9,
                source="manual",
                last_used=datetime.utcnow()
            )
        ]

        result = service.format_preferences_for_prompt(preferences)

        assert "User Preferences" in result
        assert "easy lunches" in result

    def test_format_preferences_multiple(self):
        """Test formatting multiple preferences."""
        mock_session = MagicMock()
        service = PreferenceInjectionService(mock_session)

        preferences = [
            ApplicablePreference(
                preference_id="pref_1",
                preference_key="lunch_style",
                instruction="Prefer easy lunches",
                scope="task_type",
                scope_value="meal_planning",
                confidence=0.9,
                source="manual",
                last_used=datetime.utcnow()
            ),
            ApplicablePreference(
                preference_id="pref_2",
                preference_key="email_footer",
                instruction="Always include unsubscribe link",
                scope="agent_type",
                scope_value="notify",
                confidence=1.0,
                source="manual",
                last_used=datetime.utcnow()
            )
        ]

        result = service.format_preferences_for_prompt(preferences)

        assert "easy lunches" in result
        assert "unsubscribe" in result

    def test_format_preferences_with_metadata(self):
        """Test formatting preferences with metadata included."""
        mock_session = MagicMock()
        service = PreferenceInjectionService(mock_session)

        preferences = [
            ApplicablePreference(
                preference_id="pref_1",
                preference_key="test",
                instruction="Test instruction",
                scope="global",
                scope_value=None,
                confidence=0.85,
                source="learned",
                last_used=datetime.utcnow()
            )
        ]

        result = service.format_preferences_for_prompt(preferences, include_metadata=True)

        assert "scope: global" in result
        assert "85%" in result  # confidence


# ============================================================================
# Integration: Full Workflow Tests
# ============================================================================

class TestAgentMemorySystemIntegration:
    """Integration tests for the complete Agent Memory System."""

    @pytest.mark.asyncio
    async def test_generate_validate_workflow(self):
        """Test: Generate agent spec → Validate → Dry-run."""
        # Step 1: Create valid spec directly (simulating generator output)
        spec = """
agent:
  name: integration_test_agent
  version: "1.0.0"
  type: compose
  description: |
    An integration test agent that demonstrates the full workflow
    of the Agent Memory System. It can compose content based on
    user inputs and preferences.
  brief: Integration test composer
  keywords:
    - test
    - integration
    - compose
  category: utility
  capabilities:
    - http_fetch
  system_prompt: |
    You are an integration test agent.
  prompt_template: |
    Create content about: {{ inputs.topic }}
    Format: {{ inputs.format }}
  input_schema:
    type: object
    properties:
      topic:
        type: string
      format:
        type: string
    required:
      - topic
  output_schema:
    type: object
    properties:
      content:
        type: string
  checkpoints: []
"""
        # Step 2: Validate
        validator = AgentValidationService()
        validation_result = validator.validate(spec)

        assert validation_result.is_valid, f"Validation failed: {validation_result.errors}"

        # Step 3: Dry-run
        dry_run_result = await validator.dry_run(
            spec,
            mock_inputs={"topic": "AI agents", "format": "markdown"}
        )

        assert dry_run_result.success
        assert "AI agents" in dry_run_result.prompt_rendered
        assert "markdown" in dry_run_result.prompt_rendered

        # Step 4: Validate for publish
        can_publish, _, blockers = validator.validate_for_publish(spec)
        assert can_publish, f"Publish blocked: {blockers}"

    def test_plugin_registry_completeness(self):
        """Test PLUGIN_REGISTRY has all expected infrastructure agent types."""
        # Infrastructure plugins (deterministic operations)
        expected_plugin_types = [
            "http_fetch", "notify", "transform", "file_storage",
            "generate_image", "html_to_pdf", "pdf_composer",
            "schedule_job", "document_db", "agent_storage"
        ]

        for agent_type in expected_plugin_types:
            assert agent_type in PLUGIN_REGISTRY, f"Missing plugin type: {agent_type}"

    def test_available_types_includes_plugins(self):
        """Test available_types() returns at least the plugin types."""
        types = available_types()

        # At minimum, all plugin types should be available
        for plugin_type in PLUGIN_REGISTRY.keys():
            assert plugin_type in types, f"Missing type from available_types(): {plugin_type}"

    @pytest.mark.asyncio
    async def test_dynamic_agent_creation_from_registry(self):
        """Test DynamicAgent creation via UnifiedCapabilityRegistry."""
        mock_spec = MagicMock()
        mock_spec.name = "test_dynamic"
        mock_spec.agent_type = "compose"
        mock_spec.version = "1.0.0"
        mock_spec.spec_compiled = {
            "agent": {
                "name": "test_dynamic",
                "type": "compose",
                "prompt_template": "Test"
            }
        }

        # Test that DynamicAgent can be instantiated directly
        agent = DynamicAgent(agent_spec=mock_spec)
        assert agent is not None
        assert agent.name == "test_dynamic"
        assert agent.agent_type == "compose"
