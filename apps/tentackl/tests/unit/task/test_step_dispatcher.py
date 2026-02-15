"""
Unit tests for StepDispatcher.

Tests the single source of truth for step preparation and dispatch,
covering template resolution, context injection, and dispatch logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.domain.tasks.models import (
    Task, TaskStep, StepStatus, TaskStatus,
)
from src.infrastructure.tasks.step_dispatcher import (
    StepDispatcher,
    DispatchResult,
    validate_template_references,
    build_completed_outputs,
    resolve_template_variables,
    inject_context,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_task():
    """Create a sample task with completed steps for testing."""
    task_id = str(uuid4())
    return Task(
        id=task_id,
        user_id="user-123",
        organization_id="org-456",
        goal="Research AI and create a report",
        tree_id=f"tree-{task_id}",
        steps=[
            TaskStep(
                id="step_1",
                name="research_ai",
                description="Research AI topics",
                agent_type="web_research",
                inputs={"query": "AI news"},
                status=StepStatus.DONE,
                outputs={"summary": "AI is evolving rapidly", "items": ["item1", "item2"]}
            ),
            TaskStep(
                id="step_2",
                name="generate_pdf",
                description="Generate PDF report",
                agent_type="pdf_generator",
                inputs={"content": "{{step_1.outputs.summary}}"},
                status=StepStatus.PENDING,
            ),
            TaskStep(
                id="step_3",
                name="store_file",
                description="Store PDF to CDN",
                agent_type="file_storage",
                inputs={
                    "operation": "upload",
                    "file_data": "{{step_2.outputs.file}}",
                    "filename": "report.pdf"
                },
                status=StepStatus.PENDING,
            ),
        ]
    )


@pytest.fixture
def mock_plan_store():
    """Create a mock plan store."""
    store = AsyncMock()
    store._connect = AsyncMock()
    store.get_task = AsyncMock()
    return store


@pytest.fixture
def mock_tree_adapter():
    """Create a mock tree adapter."""
    adapter = AsyncMock()
    adapter.update_step_inputs = AsyncMock()
    return adapter


# ============================================================================
# Test: validate_template_references
# ============================================================================

class TestValidateTemplateReferences:
    """Tests for template validation before resolution."""

    def test_valid_template_passes(self):
        """Valid template syntax passes validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={"content": "{{step_0.outputs.summary}}"}
        )
        # Should not raise
        validate_template_references(step)

    def test_valid_nested_template_passes(self):
        """Nested template syntax passes validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={
                "data": {
                    "content": "{{step_0.outputs.summary}}",
                    "items": "{{step_0.outputs.items}}"
                }
            }
        )
        validate_template_references(step)

    def test_empty_inputs_passes(self):
        """Step with no inputs passes validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs=None
        )
        validate_template_references(step)

    def test_inputs_without_templates_passes(self):
        """Inputs without templates pass validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={"query": "plain text", "count": 5}
        )
        validate_template_references(step)

    def test_invalid_template_missing_s_fails(self):
        """Template with 'output' (singular) fails validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={"content": "{{step_0.output}}"}  # Missing 's' and field
        )
        with pytest.raises(ValueError) as exc_info:
            validate_template_references(step)
        assert "template" in str(exc_info.value).lower() or "syntax" in str(exc_info.value).lower()

    def test_invalid_template_output_with_field_fails(self):
        """Template with 'output.field' (singular output) fails validation."""
        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={"content": "{{step_0.output.summary}}"}  # Missing 's' in outputs
        )
        with pytest.raises(ValueError) as exc_info:
            validate_template_references(step)
        assert "template" in str(exc_info.value).lower() or "syntax" in str(exc_info.value).lower()


# ============================================================================
# Test: build_completed_outputs
# ============================================================================

class TestBuildCompletedOutputs:
    """Tests for building output map from completed steps."""

    def test_builds_output_map_from_done_steps(self, sample_task):
        """Builds map from completed steps."""
        outputs = build_completed_outputs(sample_task)

        assert "step_1" in outputs
        assert outputs["step_1"]["summary"] == "AI is evolving rapidly"

    def test_maps_by_step_name(self, sample_task):
        """Also maps by step name for template resolution."""
        outputs = build_completed_outputs(sample_task)

        # Should be accessible by both ID and name
        assert "step_1" in outputs
        assert "research_ai" in outputs
        assert outputs["research_ai"]["summary"] == "AI is evolving rapidly"

    def test_excludes_pending_steps(self, sample_task):
        """Pending steps are not in the output map."""
        outputs = build_completed_outputs(sample_task)

        assert "step_2" not in outputs
        assert "generate_pdf" not in outputs

    def test_includes_skipped_steps(self):
        """Skipped steps are included in output map."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Test",
            steps=[
                TaskStep(
                    id="step_1",
                    name="skipped_step",
                    description="A skipped step",
                    agent_type="processor",
                    status=StepStatus.SKIPPED,
                    outputs={"reason": "Not needed"}
                )
            ]
        )
        outputs = build_completed_outputs(task)

        assert "step_1" in outputs
        assert outputs["step_1"]["reason"] == "Not needed"

    def test_empty_steps_returns_empty_map(self):
        """Task with no steps returns empty map."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Test",
            steps=[]
        )
        outputs = build_completed_outputs(task)

        assert outputs == {}


# ============================================================================
# Test: resolve_template_variables
# ============================================================================

class TestResolveTemplateVariables:
    """Tests for template variable resolution."""

    def test_resolves_simple_template(self):
        """Resolves simple {{step.outputs.field}} template."""
        inputs = {"content": "{{step_1.outputs.summary}}"}
        completed = {"step_1": {"summary": "AI is amazing"}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["content"] == "AI is amazing"

    def test_resolves_template_by_step_name(self):
        """Resolves template using step name."""
        inputs = {"content": "{{research.outputs.summary}}"}
        completed = {"research": {"summary": "Research findings"}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["content"] == "Research findings"

    def test_resolves_nested_templates(self):
        """Resolves templates in nested dicts."""
        inputs = {
            "data": {
                "title": "Report",
                "content": "{{step_1.outputs.summary}}",
                "items": "{{step_1.outputs.items}}"
            }
        }
        completed = {"step_1": {"summary": "Summary text", "items": ["a", "b"]}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["data"]["title"] == "Report"
        assert resolved["data"]["content"] == "Summary text"
        assert resolved["data"]["items"] == ["a", "b"]

    def test_resolves_templates_in_lists(self):
        """Resolves templates in list items."""
        inputs = {
            "items": [
                "{{step_1.outputs.item1}}",
                "{{step_1.outputs.item2}}",
                "static"
            ]
        }
        completed = {"step_1": {"item1": "first", "item2": "second"}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["items"] == ["first", "second", "static"]

    def test_resolves_array_index_access(self):
        """Resolves template with array index {{step.outputs.items[0]}}."""
        inputs = {"first_item": "{{step_1.outputs.items[0]}}"}
        completed = {"step_1": {"items": ["first", "second", "third"]}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["first_item"] == "first"

    def test_handles_missing_reference_gracefully(self):
        """Missing reference keeps original template."""
        inputs = {"content": "{{nonexistent.outputs.field}}"}
        completed = {}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["content"] == "{{nonexistent.outputs.field}}"

    def test_handles_missing_field_gracefully(self):
        """Missing field in existing step returns empty."""
        inputs = {"content": "{{step_1.outputs.missing_field}}"}
        completed = {"step_1": {"summary": "exists"}}

        resolved = resolve_template_variables(inputs, completed)

        # Returns empty string when field is missing
        assert resolved["content"] == ""

    def test_preserves_dict_type_for_whole_template(self):
        """When template is entire value, preserves dict type."""
        inputs = {"file_data": "{{step_1.outputs.metadata}}"}
        completed = {"step_1": {"metadata": {"type": "pdf", "size": 1024}}}

        resolved = resolve_template_variables(inputs, completed)

        assert isinstance(resolved["file_data"], dict)
        assert resolved["file_data"]["type"] == "pdf"

    def test_embedded_template_in_string(self):
        """Resolves template embedded in larger string."""
        inputs = {"message": "The summary is: {{step_1.outputs.summary}}. End."}
        completed = {"step_1": {"summary": "AI is evolving"}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["message"] == "The summary is: AI is evolving. End."

    def test_empty_inputs_returns_empty(self):
        """Empty inputs returns empty dict."""
        resolved = resolve_template_variables({}, {"step_1": {"data": "value"}})
        assert resolved == {}

    def test_none_inputs_returns_empty(self):
        """None inputs returns empty dict."""
        resolved = resolve_template_variables(None, {"step_1": {"data": "value"}})
        assert resolved == {}

    def test_dollar_node_syntax(self):
        """Resolves ${node.step_X.field} syntax."""
        inputs = {"content": "${node.step_1.summary}"}
        completed = {"step_1": {"summary": "Dollar syntax works"}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["content"] == "Dollar syntax works"


# ============================================================================
# Test: inject_context
# ============================================================================

class TestInjectContext:
    """Tests for context injection into step inputs."""

    def test_injects_file_storage_context(self, sample_task):
        """Injects org_id, workflow_id, agent_id for file_storage."""
        inputs = {"operation": "upload", "filename": "test.pdf"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_3",
            plan=sample_task
        )

        assert enriched["org_id"] == "org-456"
        assert enriched["workflow_id"] == str(sample_task.id)
        assert enriched["agent_id"] == "step_3"

    def test_overrides_org_id_from_plan(self, sample_task):
        """Always overrides org_id from trusted plan to prevent spoofing."""
        inputs = {"operation": "upload", "org_id": "custom-org"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_3",
            plan=sample_task
        )

        assert enriched["org_id"] == "org-456"

    def test_maps_file_data_to_content(self, sample_task):
        """Maps file_data to content for upload handler."""
        inputs = {"operation": "upload", "file_data": "base64data"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_3",
            plan=sample_task
        )

        assert enriched["content"] == "base64data"

    def test_infers_content_type_from_filename(self, sample_task):
        """Infers content_type from filename extension."""
        inputs = {"operation": "upload", "filename": "image.png"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_3",
            plan=sample_task
        )

        assert enriched["content_type"] == "image/png"

    def test_injects_generate_image_context(self, sample_task):
        """Injects context for generate_image agent."""
        inputs = {"prompt": "A beautiful sunset"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="generate_image",
            step_id="step_img",
            plan=sample_task
        )

        assert enriched["org_id"] == "org-456"
        assert enriched["workflow_id"] == str(sample_task.id)
        assert enriched["agent_id"] == "step_img"
        assert "folder_path" in enriched
        assert enriched["is_public"] is True

    def test_generate_image_folder_path_from_goal(self, sample_task):
        """Folder path is derived from plan goal."""
        inputs = {"prompt": "test"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="generate_image",
            step_id="step_1",
            plan=sample_task
        )

        # Goal: "Research AI and create a report"
        assert "/generated-images/" in enriched["folder_path"]
        assert "research-ai" in enriched["folder_path"].lower()

    def test_no_injection_for_other_agent_types(self, sample_task):
        """Other agent types get inputs unchanged."""
        inputs = {"query": "search term"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="web_research",
            step_id="step_1",
            plan=sample_task
        )

        # Should be unchanged
        assert enriched == {"query": "search term"}

    def test_handles_empty_inputs(self, sample_task):
        """Handles empty/None inputs gracefully."""
        enriched = inject_context(
            inputs={},
            agent_type="file_storage",
            step_id="step_1",
            plan=sample_task
        )

        assert enriched["org_id"] == "org-456"


# ============================================================================
# Test: StepDispatcher.dispatch_step
# ============================================================================

class TestStepDispatcher:
    """Tests for the StepDispatcher class."""

    @pytest.fixture(autouse=True)
    def skip_input_validation(self):
        """Skip runtime input validation (requires DB access to load agent specs)."""
        with patch.object(StepDispatcher, "_validate_resolved_inputs", return_value=None):
            yield

    @pytest.fixture
    def dispatcher(self, mock_plan_store, mock_tree_adapter):
        """Create dispatcher with mocked dependencies."""
        d = StepDispatcher(
            plan_store=mock_plan_store,
            tree_adapter=mock_tree_adapter
        )
        return d

    async def test_dispatch_step_success(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Successfully dispatches a step."""
        mock_plan_store.get_task.return_value = sample_task

        step = TaskStep(
            id="step_2",
            name="Test Step",
            description="Test step",
            agent_type="processor",
            inputs={"query": "test"}
        )

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-task-123")

            result = await dispatcher.dispatch_step(str(sample_task.id), step, sample_task)

        assert result.success is True
        assert result.celery_task_id == "celery-task-123"
        assert result.step_id == "step_2"
        mock_celery.delay.assert_called_once()

    async def test_dispatch_step_loads_plan_if_not_provided(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Loads plan from store if not provided."""
        mock_plan_store.get_task.return_value = sample_task

        step = TaskStep(
            id="step_2",
            name="Test Step",
            description="Test step",
            agent_type="processor",
            inputs={}
        )

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-123")

            result = await dispatcher.dispatch_step(str(sample_task.id), step)

        mock_plan_store.get_task.assert_called_once()
        assert result.success is True

    async def test_dispatch_step_fails_when_plan_not_found(
        self, dispatcher, mock_plan_store
    ):
        """Returns failure when plan is not found."""
        mock_plan_store.get_task.return_value = None

        step = TaskStep(
            id="step_1",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={}
        )

        result = await dispatcher.dispatch_step("nonexistent-task", step)

        assert result.success is False
        assert "not found" in result.error.lower()

    async def test_dispatch_step_fails_on_invalid_template(
        self, dispatcher, mock_plan_store, sample_task
    ):
        """Returns failure for invalid template syntax (missing 's' in outputs)."""
        mock_plan_store.get_task.return_value = sample_task

        # {{step_1.output}} is invalid - should be {{step_1.outputs.field}}
        step = TaskStep(
            id="step_2",
            name="Bad Template",
            description="Step with bad template",
            agent_type="processor",
            inputs={"content": "{{step_1.output}}"}
        )

        result = await dispatcher.dispatch_step(str(sample_task.id), step, sample_task)

        assert result.success is False
        assert "template" in result.error.lower() or "syntax" in result.error.lower()

    async def test_dispatch_step_resolves_templates(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Templates are resolved before dispatch."""
        step = TaskStep(
            id="step_2",
            name="With Template",
            description="Step with template",
            agent_type="processor",
            inputs={"content": "{{step_1.outputs.summary}}"}
        )

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-123")

            await dispatcher.dispatch_step(str(sample_task.id), step, sample_task)

        # Check that resolved inputs were used
        call_kwargs = mock_celery.delay.call_args.kwargs
        step_data = call_kwargs["step_data"]
        assert step_data["inputs"]["content"] == "AI is evolving rapidly"

    async def test_dispatch_step_injects_context_for_file_storage(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Context is injected for file_storage steps."""
        step = TaskStep(
            id="step_3",
            name="File Upload",
            description="Upload file",
            agent_type="file_storage",
            inputs={"operation": "upload", "filename": "test.pdf"}
        )

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-123")

            await dispatcher.dispatch_step(str(sample_task.id), step, sample_task)

        call_kwargs = mock_celery.delay.call_args.kwargs
        step_data = call_kwargs["step_data"]
        assert step_data["inputs"]["org_id"] == "org-456"
        assert step_data["inputs"]["workflow_id"] == str(sample_task.id)
        assert step_data["inputs"]["agent_id"] == "step_3"

    async def test_dispatch_step_updates_tree(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Tree is updated with resolved inputs."""
        step = TaskStep(
            id="step_2",
            name="Test",
            description="Test step",
            agent_type="processor",
            inputs={"data": "value"}
        )

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-123")

            await dispatcher.dispatch_step(str(sample_task.id), step, sample_task)

        mock_tree_adapter.update_step_inputs.assert_called_once()
        call_args = mock_tree_adapter.update_step_inputs.call_args.kwargs
        assert call_args["task_id"] == str(sample_task.id)
        assert call_args["step_id"] == "step_2"

    async def test_dispatch_multiple_steps(
        self, dispatcher, mock_plan_store, mock_tree_adapter, sample_task
    ):
        """Can dispatch multiple steps with single plan load."""
        mock_plan_store.get_task.return_value = sample_task

        steps = [
            TaskStep(id="step_a", name="A", description="Step A", agent_type="processor", inputs={}),
            TaskStep(id="step_b", name="B", description="Step B", agent_type="processor", inputs={}),
        ]

        with patch("src.core.tasks.execute_task_step") as mock_celery:
            mock_celery.delay.return_value = MagicMock(id="celery-123")

            results = await dispatcher.dispatch_steps(str(sample_task.id), steps)

        assert len(results) == 2
        assert all(r.success for r in results)
        # Plan should only be loaded once
        mock_plan_store.get_task.assert_called_once()


# ============================================================================
# Test: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_resolve_very_long_content_truncates(self):
        """Very long resolved content embedded in string is truncated."""
        # Truncation only applies when template is embedded in a larger string
        inputs = {"content": "prefix: {{step_1.outputs.data}} suffix"}
        # Create content longer than 50000 chars
        long_content = "x" * 60000
        completed = {"step_1": {"data": long_content}}

        resolved = resolve_template_variables(inputs, completed)

        # Should be truncated when embedded (prefix + truncated + suffix)
        assert len(resolved["content"]) < 60000 + 20  # Account for prefix/suffix
        assert "truncated" in resolved["content"]

    def test_inject_context_pdf_content_type(self, sample_task):
        """PDF filename gets correct content type."""
        inputs = {"operation": "upload", "filename": "report.pdf"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_1",
            plan=sample_task
        )

        assert enriched["content_type"] == "application/pdf"

    def test_inject_context_json_content_type(self, sample_task):
        """JSON filename gets correct content type."""
        inputs = {"operation": "upload", "filename": "data.json"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_1",
            plan=sample_task
        )

        assert enriched["content_type"] == "application/json"

    def test_inject_context_jpeg_content_type(self, sample_task):
        """JPEG filename gets correct content type."""
        inputs = {"operation": "upload", "filename": "photo.jpg"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_1",
            plan=sample_task
        )

        assert enriched["content_type"] == "image/jpeg"

    def test_array_index_out_of_bounds(self):
        """Out of bounds array index returns empty string."""
        inputs = {"item": "{{step_1.outputs.items[99]}}"}
        completed = {"step_1": {"items": ["only", "two"]}}

        resolved = resolve_template_variables(inputs, completed)

        assert resolved["item"] == ""

    def test_step_with_no_organization_id(self):
        """Handles task without organization_id."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id=None,  # No org
            goal="Test",
            steps=[]
        )
        inputs = {"operation": "upload"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="file_storage",
            step_id="step_1",
            plan=task
        )

        # Should not add org_id if not available
        assert "org_id" not in enriched or enriched.get("org_id") is None


# ============================================================================
# Test: Integration Context Injection
# ============================================================================

class TestInjectIntegrationContext:
    """Tests for integration context injection (list_integrations, execute_outbound_action)."""

    def test_injects_user_token_for_list_integrations(self):
        """Injects user_token from plan constraints for list_integrations."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Post a tweet",
            constraints={"user_token": "test-jwt-token-123"},
            steps=[]
        )
        inputs = {}

        enriched = inject_context(
            inputs=inputs,
            agent_type="list_integrations",
            step_id="step_1",
            plan=task,
        )

        assert enriched["user_token"] == "test-jwt-token-123"

    def test_injects_user_token_for_execute_outbound_action(self):
        """Injects user_token from plan constraints for execute_outbound_action."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Send discord message",
            constraints={"user_token": "test-jwt-token-456"},
            steps=[]
        )
        inputs = {"integration_id": "int-abc", "action_type": "send_message", "content": "Hello"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="execute_outbound_action",
            step_id="step_2",
            plan=task,
        )

        assert enriched["user_token"] == "test-jwt-token-456"
        # Original inputs preserved
        assert enriched["integration_id"] == "int-abc"
        assert enriched["action_type"] == "send_message"
        assert enriched["content"] == "Hello"

    def test_overrides_user_token_from_plan(self):
        """Always overrides user_token from trusted plan to prevent spoofing."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Test",
            constraints={"user_token": "plan-token"},
            steps=[]
        )
        inputs = {"user_token": "explicit-token"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="list_integrations",
            step_id="step_1",
            plan=task,
        )

        assert enriched["user_token"] == "plan-token"

    def test_handles_missing_constraints(self):
        """Handles plan with no constraints gracefully."""
        task = Task(
            id="task-1",
            user_id="user-1",
            organization_id="org-1",
            goal="Test",
            constraints={},
            steps=[]
        )
        inputs = {"integration_id": "int-abc"}

        enriched = inject_context(
            inputs=inputs,
            agent_type="execute_outbound_action",
            step_id="step_1",
            plan=task,
        )

        # No user_token injected since none in constraints
        assert "user_token" not in enriched
        assert enriched["integration_id"] == "int-abc"
