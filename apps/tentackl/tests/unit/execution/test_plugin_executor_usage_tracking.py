"""
Unit tests for plugin_executor's capability usage tracking.

Tests the track_capability_usage function that updates analytics columns
(usage_count, success_count, failure_count, last_used_at) in capabilities_agents.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.infrastructure.execution_runtime.plugin_executor import (
    track_capability_usage,
    execute_step,
    ExecutionResult,
    PLUGIN_REGISTRY,
)


class TestTrackCapabilityUsage:
    """Tests for the track_capability_usage function."""

    @pytest.mark.asyncio
    async def test_skips_infrastructure_plugins(self):
        """Plugin registry types should not be tracked (they're code-based)."""
        # All PLUGIN_REGISTRY types should be skipped without DB access
        for agent_type in PLUGIN_REGISTRY.keys():
            # Should return immediately without any DB operations
            await track_capability_usage(
                agent_type=agent_type,
                success=True,
            )
        # If we got here without errors, plugins were properly skipped

    @pytest.mark.asyncio
    async def test_tracks_success_for_system_capability(self):
        """Should increment usage_count and success_count for successful execution."""
        mock_capability = MagicMock()
        mock_capability.id = uuid4()
        mock_capability.usage_count = 5
        mock_capability.success_count = 4
        mock_capability.failure_count = 1
        mock_capability.last_used_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_capability)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            await track_capability_usage(
                agent_type="summarize",
                success=True,
            )

        # Verify analytics were updated
        assert mock_capability.usage_count == 6
        assert mock_capability.success_count == 5
        assert mock_capability.failure_count == 1  # unchanged
        assert mock_capability.last_used_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_tracks_failure_for_system_capability(self):
        """Should increment usage_count and failure_count for failed execution."""
        mock_capability = MagicMock()
        mock_capability.id = uuid4()
        mock_capability.usage_count = 10
        mock_capability.success_count = 8
        mock_capability.failure_count = 2
        mock_capability.last_used_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_capability)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            await track_capability_usage(
                agent_type="web_research",
                success=False,
            )

        # Verify analytics were updated
        assert mock_capability.usage_count == 11
        assert mock_capability.success_count == 8  # unchanged
        assert mock_capability.failure_count == 3
        assert mock_capability.last_used_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_capability_not_found(self):
        """Should log debug message when capability not found."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Return None for both org and system queries
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            # Should not raise an error
            await track_capability_usage(
                agent_type="unknown_agent_type",
                success=True,
            )

        # Commit should not be called since no capability was found
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_prefers_org_capability_over_system(self):
        """Should try org-specific capability first when organization_id provided."""
        org_id = str(uuid4())
        org_capability = MagicMock()
        org_capability.id = uuid4()
        org_capability.usage_count = 1
        org_capability.success_count = 1
        org_capability.failure_count = 0
        org_capability.last_used_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # First call returns org capability, system query should not be made
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=org_capability)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            await track_capability_usage(
                agent_type="custom_agent",
                success=True,
                organization_id=org_id,
            )

        # Should have used org capability
        assert org_capability.usage_count == 2
        assert org_capability.success_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_system_when_org_not_found(self):
        """Should fall back to system capability when org-specific not found."""
        org_id = str(uuid4())
        system_capability = MagicMock()
        system_capability.id = uuid4()
        system_capability.usage_count = 100
        system_capability.success_count = 95
        system_capability.failure_count = 5
        system_capability.last_used_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # First call (org query) returns None, second (system query) returns capability
        org_result = MagicMock()
        org_result.scalar_one_or_none = MagicMock(return_value=None)

        system_result = MagicMock()
        system_result.scalar_one_or_none = MagicMock(return_value=system_capability)

        mock_session.execute = AsyncMock(side_effect=[org_result, system_result])
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            await track_capability_usage(
                agent_type="summarize",
                success=True,
                organization_id=org_id,
            )

        # Should have fallen back to system capability
        assert system_capability.usage_count == 101
        assert system_capability.success_count == 96
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_db_connection_error_gracefully(self):
        """Should log warning and continue when DB connection fails."""
        mock_db = MagicMock()
        mock_db.connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_db.disconnect = AsyncMock()

        with patch("src.interfaces.database.Database", return_value=mock_db):
            # Should not raise an error - just log and continue
            await track_capability_usage(
                agent_type="summarize",
                success=True,
            )

    @pytest.mark.asyncio
    async def test_handles_query_error_gracefully(self):
        """Should log warning and continue when query fails."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            # Should not raise an error - just log and continue
            await track_capability_usage(
                agent_type="summarize",
                success=True,
            )

    @pytest.mark.asyncio
    async def test_handles_null_counts(self):
        """Should handle capabilities with NULL count values."""
        mock_capability = MagicMock()
        mock_capability.id = uuid4()
        mock_capability.usage_count = None  # NULL in DB
        mock_capability.success_count = None
        mock_capability.failure_count = None
        mock_capability.last_used_at = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_capability)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_session = MagicMock(return_value=mock_session)

        with patch("src.interfaces.database.Database", return_value=mock_db):
            await track_capability_usage(
                agent_type="summarize",
                success=True,
            )

        # Should handle NULL by treating as 0
        assert mock_capability.usage_count == 1
        assert mock_capability.success_count == 1
        assert mock_capability.failure_count is None or mock_capability.failure_count == 0


class TestExecuteStepWithUsageTracking:
    """Tests for execute_step integration with usage tracking."""

    @pytest.mark.asyncio
    async def test_calls_track_usage_after_db_agent_execution(self):
        """Should call track_capability_usage after executing a DB agent."""
        import src.infrastructure.execution_runtime.plugin_executor as plugin_executor_module

        mock_step = MagicMock()
        mock_step.agent_type = "summarize"
        mock_step.id = str(uuid4())
        mock_step.inputs = {"text": "Test input"}

        # Use MagicMock for agent so hasattr checks work correctly
        # (AsyncMock returns True for all hasattr checks)
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=ExecutionResult(
            status="success",
            output={"summary": "Test summary"},
        ))
        # Explicitly remove execute_validated so hasattr returns False
        del mock_agent.execute_validated
        del mock_agent.initialize
        del mock_agent.cleanup

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(return_value=mock_agent)

        org_id = str(uuid4())

        async def mock_get_registry():
            return mock_registry

        with patch.object(plugin_executor_module, "track_capability_usage", new_callable=AsyncMock) as mock_track:
            with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
                result = await execute_step(
                    step=mock_step,
                    organization_id=org_id,
                )

                # Verify tracking was called with correct parameters
                mock_track.assert_called_once_with(
                    agent_type="summarize",
                    success=True,
                    organization_id=org_id,
                )

    @pytest.mark.asyncio
    async def test_tracks_failure_when_execution_fails(self):
        """Should track failure when DB agent execution fails."""
        import src.infrastructure.execution_runtime.plugin_executor as plugin_executor_module

        mock_step = MagicMock()
        mock_step.agent_type = "analyze"
        mock_step.id = str(uuid4())
        mock_step.inputs = {"data": "Test data"}

        # Use MagicMock for agent so hasattr checks work correctly
        # (AsyncMock returns True for all hasattr checks)
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=ExecutionResult(
            status="error",
            output=None,
            error="Execution failed",
        ))
        # Explicitly remove execute_validated so hasattr returns False
        del mock_agent.execute_validated
        del mock_agent.initialize
        del mock_agent.cleanup

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(return_value=mock_agent)

        async def mock_get_registry():
            return mock_registry

        with patch.object(plugin_executor_module, "track_capability_usage", new_callable=AsyncMock) as mock_track:
            with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
                result = await execute_step(
                    step=mock_step,
                )

                # Verify tracking was called with success=False
                mock_track.assert_called_once_with(
                    agent_type="analyze",
                    success=False,
                    organization_id=None,
                )

    @pytest.mark.asyncio
    async def test_no_tracking_for_plugin_registry_types(self):
        """Should not call track_capability_usage for plugin registry types."""
        import src.infrastructure.execution_runtime.plugin_executor as plugin_executor_module

        mock_step = MagicMock()
        mock_step.agent_type = "http_fetch"  # Plugin registry type
        mock_step.id = str(uuid4())
        mock_step.inputs = {"url": "https://example.com"}

        # Mock the plugin handler
        mock_handler = AsyncMock(return_value={"status": "success", "data": "Test"})

        with patch("importlib.import_module") as mock_importlib:
            mock_module = MagicMock()
            mock_module.http_request_handler = mock_handler
            mock_importlib.return_value = mock_module

            with patch.object(plugin_executor_module, "track_capability_usage", new_callable=AsyncMock) as mock_track:
                result = await execute_step(
                    step=mock_step,
                )

                # Plugin types return early, never reaching track_capability_usage
                mock_track.assert_not_called()

    @pytest.mark.asyncio
    async def test_tracks_exception_as_failure(self):
        """Should track as failure when exception is raised during execution."""
        import src.infrastructure.execution_runtime.plugin_executor as plugin_executor_module

        mock_step = MagicMock()
        mock_step.agent_type = "compose"
        mock_step.id = str(uuid4())
        mock_step.inputs = {"content": "Test content"}

        # Use MagicMock for agent so hasattr checks work correctly
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(side_effect=Exception("Unexpected error"))
        # Explicitly remove execute_validated so hasattr returns False
        del mock_agent.execute_validated
        del mock_agent.initialize
        del mock_agent.cleanup

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(return_value=mock_agent)

        async def mock_get_registry():
            return mock_registry

        with patch.object(plugin_executor_module, "track_capability_usage", new_callable=AsyncMock) as mock_track:
            with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
                result = await execute_step(
                    step=mock_step,
                )

                # Should track as failure
                mock_track.assert_called_once_with(
                    agent_type="compose",
                    success=False,
                    organization_id=None,
                )

    @pytest.mark.asyncio
    async def test_tracks_unknown_agent_type_as_failure(self):
        """Should track as failure when agent type is not found."""
        import src.infrastructure.execution_runtime.plugin_executor as plugin_executor_module

        mock_step = MagicMock()
        mock_step.agent_type = "nonexistent_agent"
        mock_step.id = str(uuid4())
        mock_step.inputs = {}

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(side_effect=ValueError("Unknown agent type"))

        async def mock_get_registry():
            return mock_registry

        with patch.object(plugin_executor_module, "track_capability_usage", new_callable=AsyncMock) as mock_track:
            with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
                result = await execute_step(
                    step=mock_step,
                )

                # Should track as failure
                mock_track.assert_called_once_with(
                    agent_type="nonexistent_agent",
                    success=False,
                    organization_id=None,
                )
