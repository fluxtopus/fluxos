"""Unit tests for CreateTriggeredTaskTool."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.inbox.tools.create_triggered_task import CreateTriggeredTaskTool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool():
    return CreateTriggeredTaskTool()


@pytest.fixture
def valid_context():
    return {
        "user_id": str(uuid.uuid4()),
        "organization_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
    }


@pytest.fixture
def valid_arguments():
    return {
        "goal": "Generate a programming joke",
        "trigger_source": "discord",
        "integration_id": str(uuid.uuid4()),
        "event_filter": {"command": "ping"},
        "response_type": "discord_followup",
    }


@pytest.fixture
def task_use_cases_with_task():
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    task_use_cases = AsyncMock()
    task_use_cases.create_task_with_steps = AsyncMock(return_value=mock_task)
    task_use_cases.link_conversation = AsyncMock()
    return task_use_cases, mock_task


@pytest.fixture
def trigger_use_cases():
    trigger_use_cases = AsyncMock()
    trigger_use_cases.register_trigger = AsyncMock(return_value=True)
    return trigger_use_cases


# ---------------------------------------------------------------------------
# Tool Definition Tests
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_name(self, tool):
        assert tool.name == "create_triggered_task"

    def test_description(self, tool):
        assert "automatically" in tool.description.lower()
        assert "events" in tool.description.lower()

    def test_definition_has_required_params(self, tool):
        definition = tool.get_definition()
        assert definition.name == "create_triggered_task"
        params = definition.parameters
        assert "goal" in params["properties"]
        assert "trigger_source" in params["properties"]
        assert "integration_id" in params["properties"]
        assert params["required"] == ["goal", "trigger_source", "integration_id"]

    def test_trigger_source_enum(self, tool):
        definition = tool.get_definition()
        trigger_source = definition.parameters["properties"]["trigger_source"]
        assert trigger_source["enum"] == ["discord", "slack", "webhook", "github"]

    def test_response_type_enum(self, tool):
        definition = tool.get_definition()
        response_type = definition.parameters["properties"]["response_type"]
        assert "discord_followup" in response_type["enum"]
        assert "slack_message" in response_type["enum"]
        assert "none" in response_type["enum"]


# ---------------------------------------------------------------------------
# Step Building Tests
# ---------------------------------------------------------------------------


class TestBuildSteps:
    def test_builds_compose_step(self, tool):
        steps = tool._build_steps("Generate a joke", "none", "discord")
        assert len(steps) == 1
        assert steps[0]["name"] == "generate_response"
        assert steps[0]["agent_type"] == "compose"
        assert steps[0]["inputs"]["topic"] == "Generate a joke"
        assert steps[0]["inputs"]["research"] == "${trigger_event.data}"
        assert steps[0]["inputs"]["length"] == "short"
        # Ensure only valid compose inputs are used
        valid_compose_inputs = {"format", "length", "requirements", "research", "tone", "topic"}
        assert set(steps[0]["inputs"].keys()).issubset(valid_compose_inputs)

    def test_builds_discord_followup_step(self, tool):
        steps = tool._build_steps("Generate a joke", "discord_followup", "discord")
        assert len(steps) == 2
        assert steps[1]["name"] == "send_response"
        assert steps[1]["agent_type"] == "discord_followup"
        assert "application_id" in steps[1]["inputs"]
        assert "interaction_token" in steps[1]["inputs"]
        assert steps[1]["dependencies"] == ["generate_response"]

    def test_builds_slack_message_step(self, tool):
        steps = tool._build_steps("Generate a joke", "slack_message", "slack")
        assert len(steps) == 2
        assert steps[1]["agent_type"] == "slack_message"
        assert "channel" in steps[1]["inputs"]

    def test_builds_webhook_step(self, tool):
        steps = tool._build_steps("Generate a joke", "webhook", "webhook")
        assert len(steps) == 2
        assert steps[1]["agent_type"] == "http_fetch"
        assert steps[1]["inputs"]["method"] == "POST"


# ---------------------------------------------------------------------------
# Trigger Config Building Tests
# ---------------------------------------------------------------------------


class TestBuildTriggerConfig:
    def test_basic_trigger_config(self, tool):
        config = tool._build_trigger_config("integration-123", {})
        assert config["type"] == "event"
        assert config["event_pattern"] == "external.integration.webhook"
        assert config["source_filter"] == "integration:integration-123"
        assert config["enabled"] is True

    def test_command_filter_adds_condition(self, tool):
        config = tool._build_trigger_config("int-123", {"command": "ping"})
        assert "condition" in config
        assert config["condition"] == {"==": [{"var": "data.command"}, "ping"]}

    def test_channel_filter_adds_condition(self, tool):
        config = tool._build_trigger_config("int-123", {"channel_id": "chan-456"})
        assert "condition" in config
        assert config["condition"] == {"==": [{"var": "data.channel_id"}, "chan-456"]}

    def test_combined_filters_use_and(self, tool):
        config = tool._build_trigger_config(
            "int-123", {"command": "ping", "channel_id": "chan-456"}
        )
        assert "condition" in config
        assert "and" in config["condition"]
        conditions = config["condition"]["and"]
        assert len(conditions) == 2


# ---------------------------------------------------------------------------
# Trigger Description Tests
# ---------------------------------------------------------------------------


class TestDescribeTrigger:
    def test_basic_description(self, tool):
        desc = tool._describe_trigger("discord", {})
        assert "discord" in desc
        assert "events arrive" in desc

    def test_command_description(self, tool):
        desc = tool._describe_trigger("discord", {"command": "ping"})
        assert "/ping" in desc

    def test_channel_description(self, tool):
        desc = tool._describe_trigger("discord", {"channel_id": "general"})
        assert "channel general" in desc


# ---------------------------------------------------------------------------
# Execute Tests
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_requires_user_id(self, tool, valid_arguments):
        context = {"organization_id": "org-1"}
        result = await tool.execute(valid_arguments, context)
        assert result.success is False
        assert "user_id" in result.error

    @pytest.mark.asyncio
    async def test_requires_organization_id(self, tool, valid_arguments):
        context = {"user_id": "user-1"}
        result = await tool.execute(valid_arguments, context)
        assert result.success is False
        assert "organization_id" in result.error

    @pytest.mark.asyncio
    async def test_creates_task_with_trigger_metadata(
        self, tool, valid_arguments, valid_context, task_use_cases_with_task, trigger_use_cases
    ):
        task_use_cases, mock_task = task_use_cases_with_task

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=trigger_use_cases),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        assert result.success is True
        assert result.data["task_id"] == mock_task.id
        assert result.data["trigger_source"] == "discord"

        # Verify task was created with correct metadata
        call_kwargs = task_use_cases.create_task_with_steps.call_args.kwargs
        assert "metadata" in call_kwargs
        assert "trigger" in call_kwargs["metadata"]
        assert call_kwargs["metadata"]["source"] == "inbox_triggered"

    @pytest.mark.asyncio
    async def test_trigger_config_in_metadata(
        self, tool, valid_arguments, valid_context, task_use_cases_with_task, trigger_use_cases
    ):
        task_use_cases, _mock_task = task_use_cases_with_task

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=trigger_use_cases),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        # Verify trigger config structure
        call_kwargs = task_use_cases.create_task_with_steps.call_args.kwargs
        trigger = call_kwargs["metadata"]["trigger"]
        assert trigger["type"] == "event"
        assert trigger["event_pattern"] == "external.integration.webhook"
        assert trigger["enabled"] is True
        # Should have command filter
        assert "condition" in trigger

    @pytest.mark.asyncio
    async def test_discord_followup_steps_created(
        self, tool, valid_arguments, valid_context, task_use_cases_with_task, trigger_use_cases
    ):
        task_use_cases, _mock_task = task_use_cases_with_task

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=trigger_use_cases),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        # Verify steps include discord_followup
        call_kwargs = task_use_cases.create_task_with_steps.call_args.kwargs
        steps = call_kwargs["steps"]
        assert len(steps) == 2
        assert steps[0]["agent_type"] == "compose"
        assert steps[1]["agent_type"] == "discord_followup"

    @pytest.mark.asyncio
    async def test_confirmation_message(self, tool, valid_arguments, valid_context):
        task_use_cases = AsyncMock()
        mock_task = MagicMock()
        mock_task.id = str(uuid.uuid4())
        task_use_cases.create_task_with_steps = AsyncMock(return_value=mock_task)
        task_use_cases.link_conversation = AsyncMock()

        trigger_use_cases = AsyncMock()
        trigger_use_cases.register_trigger = AsyncMock(return_value=True)

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=trigger_use_cases),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        # Verify message describes when the task fires
        assert result.message is not None
        assert "triggered" in result.message.lower() or "run" in result.message.lower()
        assert "/ping" in result.message
        assert "discord" in result.message.lower()

    @pytest.mark.asyncio
    async def test_registers_trigger_in_redis(
        self, tool, valid_arguments, valid_context, task_use_cases_with_task, trigger_use_cases
    ):
        """Verify the trigger is registered in Redis via TaskTriggerRegistry."""
        task_use_cases, mock_task = task_use_cases_with_task

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=trigger_use_cases),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        assert result.success is True

        # Verify register_trigger was called with correct args
        trigger_use_cases.register_trigger.assert_called_once_with(
            task_id=mock_task.id,
            org_id=valid_context["organization_id"],
            trigger_config={
                "type": "event",
                "event_pattern": "external.integration.webhook",
                "source_filter": f"integration:{valid_arguments['integration_id']}",
                "enabled": True,
                "condition": {"==": [{"var": "data.command"}, "ping"]},
            },
            user_id=valid_context["user_id"],
        )

    @pytest.mark.asyncio
    async def test_handles_service_error(self, tool, valid_arguments, valid_context):
        task_use_cases = AsyncMock()
        task_use_cases.create_task_with_steps = AsyncMock(
            side_effect=Exception("DB connection failed")
        )

        with patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_task_use_cases",
            new=AsyncMock(return_value=task_use_cases),
        ), patch(
            "src.infrastructure.inbox.tools.create_triggered_task._get_trigger_use_cases",
            new=AsyncMock(return_value=AsyncMock()),
        ):
            result = await tool.execute(valid_arguments, valid_context)

        assert result.success is False
        assert "DB connection failed" in result.error
