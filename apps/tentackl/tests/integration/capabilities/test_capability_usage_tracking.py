"""Integration tests for capability usage tracking (CAP-012).

Tests the track_capability_usage function against a real database.
Verifies that usage_count, success_count, failure_count, and last_used_at
are properly updated for capabilities after step execution.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from uuid import uuid4

from src.database.capability_models import AgentCapability
from src.infrastructure.execution_runtime.plugin_executor import track_capability_usage


@pytest_asyncio.fixture
async def seed_tracking_capabilities(test_db):
    """Seed test capabilities for usage tracking tests.

    Creates:
    - A system capability with existing usage stats
    - An org capability with existing usage stats
    - A capability with zero counts
    """
    system_cap_id = uuid4()
    org_cap_id = uuid4()
    zero_cap_id = uuid4()
    org_id = uuid4()

    unique_suffix = uuid4().hex[:8]

    async with test_db.get_session() as session:
        # System capability with existing stats
        system_cap = AgentCapability(
            id=system_cap_id,
            organization_id=None,
            agent_type=f"track_summarize_{unique_suffix}",
            name="Tracking Test Summarize Agent",
            description="Test capability for tracking",
            domain="content",
            task_type="general",
            system_prompt="You are a test agent.",
            inputs_schema={"type": "object"},
            outputs_schema={"type": "object"},
            is_system=True,
            is_active=True,
            is_latest=True,
            version=1,
            usage_count=100,
            success_count=95,
            failure_count=5,
            last_used_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )

        # Org capability with existing stats
        org_cap = AgentCapability(
            id=org_cap_id,
            organization_id=org_id,
            agent_type=f"track_custom_{unique_suffix}",
            name="Tracking Test Custom Agent",
            description="Custom test capability for tracking",
            domain="custom",
            task_type="general",
            system_prompt="You are a custom test agent.",
            inputs_schema={"type": "object"},
            outputs_schema={"type": "object"},
            is_system=False,
            is_active=True,
            is_latest=True,
            version=1,
            usage_count=10,
            success_count=8,
            failure_count=2,
            last_used_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )

        # Capability with zero counts
        zero_cap = AgentCapability(
            id=zero_cap_id,
            organization_id=None,
            agent_type=f"track_zero_{unique_suffix}",
            name="Tracking Test Zero Agent",
            description="Capability with zero usage",
            domain="test",
            task_type="general",
            system_prompt="You are a test agent.",
            inputs_schema={"type": "object"},
            outputs_schema={"type": "object"},
            is_system=True,
            is_active=True,
            is_latest=True,
            version=1,
            usage_count=0,
            success_count=0,
            failure_count=0,
            last_used_at=None,
        )

        session.add(system_cap)
        session.add(org_cap)
        session.add(zero_cap)
        await session.commit()

    return {
        "system_cap_id": system_cap_id,
        "org_cap_id": org_cap_id,
        "zero_cap_id": zero_cap_id,
        "org_id": org_id,
        "unique_suffix": unique_suffix,
        "system_agent_type": f"track_summarize_{unique_suffix}",
        "org_agent_type": f"track_custom_{unique_suffix}",
        "zero_agent_type": f"track_zero_{unique_suffix}",
    }


class TestCapabilityUsageTrackingIntegration:
    """Integration tests for track_capability_usage function."""

    @pytest.mark.asyncio
    async def test_increments_success_count_for_system_capability(
        self, test_db, seed_tracking_capabilities
    ):
        """Should increment usage_count and success_count for successful execution."""
        agent_type = seed_tracking_capabilities["system_agent_type"]
        cap_id = seed_tracking_capabilities["system_cap_id"]

        # Track a successful execution
        await track_capability_usage(
            agent_type=agent_type,
            success=True,
        )

        # Verify the counts were updated
        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 101  # was 100
            assert cap.success_count == 96  # was 95
            assert cap.failure_count == 5  # unchanged
            assert cap.last_used_at is not None
            assert cap.last_used_at > datetime(2026, 1, 1, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_increments_failure_count_for_system_capability(
        self, test_db, seed_tracking_capabilities
    ):
        """Should increment usage_count and failure_count for failed execution."""
        agent_type = seed_tracking_capabilities["system_agent_type"]
        cap_id = seed_tracking_capabilities["system_cap_id"]

        # Track a failed execution
        await track_capability_usage(
            agent_type=agent_type,
            success=False,
        )

        # Verify the counts were updated
        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 101  # was 100
            assert cap.success_count == 95  # unchanged
            assert cap.failure_count == 6  # was 5
            assert cap.last_used_at is not None

    @pytest.mark.asyncio
    async def test_prefers_org_capability_over_system(
        self, test_db, seed_tracking_capabilities
    ):
        """Should update org capability when organization_id is provided."""
        agent_type = seed_tracking_capabilities["org_agent_type"]
        org_id = str(seed_tracking_capabilities["org_id"])
        cap_id = seed_tracking_capabilities["org_cap_id"]

        # Track execution with org_id
        await track_capability_usage(
            agent_type=agent_type,
            success=True,
            organization_id=org_id,
        )

        # Verify org capability was updated
        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 11  # was 10
            assert cap.success_count == 9  # was 8
            assert cap.failure_count == 2  # unchanged

    @pytest.mark.asyncio
    async def test_falls_back_to_system_when_org_not_found(
        self, test_db, seed_tracking_capabilities
    ):
        """Should update system capability when org capability doesn't exist."""
        # Use the system agent_type with a random org_id
        agent_type = seed_tracking_capabilities["system_agent_type"]
        random_org_id = str(uuid4())
        system_cap_id = seed_tracking_capabilities["system_cap_id"]

        # Track execution with non-matching org_id
        await track_capability_usage(
            agent_type=agent_type,
            success=True,
            organization_id=random_org_id,
        )

        # Verify system capability was updated (fallback)
        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == system_cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 101  # was 100

    @pytest.mark.asyncio
    async def test_handles_capability_with_zero_counts(
        self, test_db, seed_tracking_capabilities
    ):
        """Should handle capabilities starting with zero counts."""
        agent_type = seed_tracking_capabilities["zero_agent_type"]
        cap_id = seed_tracking_capabilities["zero_cap_id"]

        # Track a successful execution
        await track_capability_usage(
            agent_type=agent_type,
            success=True,
        )

        # Verify counts were updated from zero
        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 1  # was 0
            assert cap.success_count == 1  # was 0
            assert cap.failure_count == 0  # unchanged
            assert cap.last_used_at is not None  # was None

    @pytest.mark.asyncio
    async def test_no_error_when_capability_not_found(
        self, test_db, seed_tracking_capabilities
    ):
        """Should not raise error when capability doesn't exist."""
        # Track execution for non-existent agent type
        # Should not raise - just log and continue
        await track_capability_usage(
            agent_type="nonexistent_agent_type_xyz",
            success=True,
        )
        # No assertion needed - test passes if no exception raised

    @pytest.mark.asyncio
    async def test_updates_last_used_at_timestamp(
        self, test_db, seed_tracking_capabilities
    ):
        """Should update last_used_at to current timestamp."""
        agent_type = seed_tracking_capabilities["zero_agent_type"]
        cap_id = seed_tracking_capabilities["zero_cap_id"]

        before_time = datetime.now(timezone.utc)

        await track_capability_usage(
            agent_type=agent_type,
            success=True,
        )

        after_time = datetime.now(timezone.utc)

        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.last_used_at is not None
            assert before_time <= cap.last_used_at <= after_time

    @pytest.mark.asyncio
    async def test_multiple_executions_accumulate(
        self, test_db, seed_tracking_capabilities
    ):
        """Should accumulate counts across multiple executions."""
        agent_type = seed_tracking_capabilities["zero_agent_type"]
        cap_id = seed_tracking_capabilities["zero_cap_id"]

        # Track multiple executions
        await track_capability_usage(agent_type=agent_type, success=True)
        await track_capability_usage(agent_type=agent_type, success=True)
        await track_capability_usage(agent_type=agent_type, success=False)
        await track_capability_usage(agent_type=agent_type, success=True)

        async with test_db.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 4
            assert cap.success_count == 3
            assert cap.failure_count == 1
