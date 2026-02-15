"""Unit tests for the schedule_job plugin.

Tests:
- Recurring: valid cron creates Automation with correct fields
- One-time: valid execute_at creates Automation with cron=None
- Validation: missing required fields return error
- Skip on cloned execution: _task_metadata.automation_id present -> returns "skipped"
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.plugins.schedule_job_plugin import schedule_handler, PLUGIN_DEFINITION


class TestPluginDefinition:
    """Tests for the PLUGIN_DEFINITION structure."""

    def test_has_required_fields(self):
        required = ["name", "description", "handler", "inputs_schema", "outputs_schema"]
        for field in required:
            assert field in PLUGIN_DEFINITION, f"Missing {field}"

    def test_name_is_schedule_job(self):
        assert PLUGIN_DEFINITION["name"] == "schedule_job"

    def test_category_is_scheduling(self):
        assert PLUGIN_DEFINITION["category"] == "scheduling"

    def test_handler_is_schedule_handler(self):
        assert PLUGIN_DEFINITION["handler"] is schedule_handler


class TestScheduleHandlerValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_missing_plan_id(self):
        result = await schedule_handler({"step_id": "s1", "user_id": "u1"})
        assert result["status"] == "error"
        assert "plan_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_step_id(self):
        result = await schedule_handler({"plan_id": "p1", "user_id": "u1"})
        assert result["status"] == "error"
        assert "step_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_user_id(self):
        result = await schedule_handler({"plan_id": "p1", "step_id": "s1"})
        assert result["status"] == "error"
        assert "user_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_schedule_method(self):
        result = await schedule_handler({
            "plan_id": "p1",
            "step_id": "s1",
            "user_id": "u1",
        })
        assert result["status"] == "error"
        assert "execute_at" in result["error"] or "cron" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_execute_at_format(self):
        result = await schedule_handler({
            "plan_id": str(uuid.uuid4()),
            "step_id": "s1",
            "user_id": "u1",
            "execute_at": "not-a-date",
        })
        assert result["status"] == "error"
        assert "execute_at" in result["error"].lower() or "format" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_cron_expression(self):
        with patch("src.core.cron_utils.validate_cron_string", return_value=False):
            result = await schedule_handler({
                "plan_id": str(uuid.uuid4()),
                "step_id": "s1",
                "user_id": "u1",
                "cron": "invalid cron",
            })
        assert result["status"] == "error"
        assert "cron" in result["error"].lower()


class TestScheduleHandlerSkipCloned:
    """Tests for clone detection (metadata-based skip)."""

    @pytest.mark.asyncio
    async def test_skips_when_automation_id_in_metadata(self):
        auto_id = str(uuid.uuid4())
        result = await schedule_handler({
            "plan_id": str(uuid.uuid4()),
            "step_id": "s1",
            "user_id": "u1",
            "cron": "0 8 * * *",
            "_task_metadata": {"automation_id": auto_id},
        })
        assert result["status"] == "skipped"
        assert result["job_id"] == auto_id

    @pytest.mark.asyncio
    async def test_does_not_skip_without_metadata(self):
        """Without metadata, should proceed to create automation (mocked)."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_db = MagicMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        next_run = datetime.utcnow() + timedelta(hours=1)

        with patch("src.core.tasks.get_shared_db", new_callable=AsyncMock, return_value=mock_db), \
             patch("src.core.cron_utils.validate_cron_string", return_value=True), \
             patch("src.core.cron_utils.calculate_next_run", return_value=next_run):

            result = await schedule_handler({
                "plan_id": str(uuid.uuid4()),
                "step_id": "s1",
                "user_id": "u1",
                "cron": "0 8 * * *",
            })

        assert result["status"] == "scheduled"
        assert result["schedule_type"] == "recurring"
        mock_session.add.assert_called_once()


class TestScheduleHandlerRecurring:
    """Tests for recurring (cron-based) automation creation."""

    @pytest.mark.asyncio
    async def test_creates_recurring_automation(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_db = MagicMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        plan_id = str(uuid.uuid4())
        next_run = datetime.utcnow() + timedelta(hours=1)

        with patch("src.core.tasks.get_shared_db", new_callable=AsyncMock, return_value=mock_db), \
             patch("src.core.cron_utils.validate_cron_string", return_value=True), \
             patch("src.core.cron_utils.calculate_next_run", return_value=next_run):

            result = await schedule_handler({
                "plan_id": plan_id,
                "step_id": "s1",
                "user_id": "u1",
                "cron": "0 8 * * *",
                "timezone": "America/New_York",
                "name": "Daily news",
            })

        assert result["status"] == "scheduled"
        assert result["schedule_type"] == "recurring"
        assert result["name"] == "Daily news"
        assert "job_id" in result

        # Verify the Automation was added to session
        added = mock_session.add.call_args[0][0]
        assert added.cron == "0 8 * * *"
        assert added.execute_at is None
        assert added.timezone == "America/New_York"
        assert added.enabled is True
        assert str(added.task_id) == plan_id


class TestScheduleHandlerOneTime:
    """Tests for one-time (execute_at-based) automation creation."""

    @pytest.mark.asyncio
    async def test_creates_one_time_automation(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_db = MagicMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        plan_id = str(uuid.uuid4())
        execute_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z"

        with patch("src.core.tasks.get_shared_db", new_callable=AsyncMock, return_value=mock_db):
            result = await schedule_handler({
                "plan_id": plan_id,
                "step_id": "s1",
                "user_id": "u1",
                "execute_at": execute_at,
            })

        assert result["status"] == "scheduled"
        assert result["schedule_type"] == "one_time"

        added = mock_session.add.call_args[0][0]
        assert added.cron is None
        assert added.execute_at is not None
        assert added.enabled is True
        assert str(added.task_id) == plan_id
