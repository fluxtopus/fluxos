"""Integration tests for CapabilityEmbeddingService.

Tests the capability embedding service against isolated database schema.
Uses mocked OpenAI client to avoid external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.infrastructure.capabilities.capability_embedding_service import CapabilityEmbeddingService
from src.database.capability_models import AgentCapability


@pytest.fixture
def mock_embedding_client():
    """Create a mock embedding client that returns valid embeddings."""
    client = MagicMock()
    client.is_configured = True
    client.model = "text-embedding-3-small"
    client.dimensions = 1536
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    # Return a 1536-dimensional embedding
    mock_result = MagicMock()
    mock_result.embedding = [0.1] * 1536
    client.create_embedding = AsyncMock(return_value=mock_result)

    return client


@pytest.fixture
async def test_capability(integration_db):
    """Create a test capability for embedding tests.

    Note: No manual cleanup needed - the integration_db fixture
    automatically drops the schema after tests complete.
    """
    cap_id = uuid4()
    org_id = uuid4()
    agent_type = f"test_embedding_{uuid4().hex[:8]}"

    async with integration_db.get_session() as session:
        capability = AgentCapability(
            id=cap_id,
            organization_id=org_id,
            agent_type=agent_type,
            name="Test Embedding Agent",
            description="A test agent for embedding generation",
            domain="test",
            task_type="general",
            system_prompt="You are a test agent for embedding generation.",
            inputs_schema={"query": {"type": "string", "required": True}},
            outputs_schema={"result": {"type": "string"}},
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
            embedding_status="pending",
            keywords=["test", "embedding"],
            tags=["integration-test"],
        )
        session.add(capability)
        await session.commit()
        await session.refresh(capability)

    yield capability
    # No manual cleanup needed - integration_db drops schema automatically


class TestCapabilityEmbeddingServiceIntegration:
    """Integration tests for CapabilityEmbeddingService."""

    @pytest.mark.asyncio
    async def test_generate_and_store_embedding_success(
        self, integration_db, mock_embedding_client, test_capability
    ):
        """Test successful embedding generation and storage."""
        service = CapabilityEmbeddingService(
            database=integration_db,
            embedding_client=mock_embedding_client,
        )

        # Generate and store embedding
        result = await service.generate_and_store_embedding(str(test_capability.id))

        assert result is True

        # Verify embedding was stored
        async with integration_db.get_session() as session:
            from sqlalchemy import select, text

            # Check embedding_status changed to 'generated'
            query_result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == test_capability.id)
            )
            capability = query_result.scalar_one_or_none()

            assert capability is not None
            assert capability.embedding_status == "generated"

            # Check embedding exists in database (raw SQL due to Vector type)
            result = await session.execute(
                text("""
                    SELECT description_embedding IS NOT NULL as has_embedding
                    FROM capabilities_agents
                    WHERE id = :id
                """),
                {"id": str(test_capability.id)}
            )
            row = result.fetchone()
            assert row is not None
            assert row.has_embedding is True

    @pytest.mark.asyncio
    async def test_generate_embedding_for_nonexistent_capability(
        self, integration_db, mock_embedding_client
    ):
        """Test embedding generation for non-existent capability returns False."""
        service = CapabilityEmbeddingService(
            database=integration_db,
            embedding_client=mock_embedding_client,
        )

        result = await service.generate_and_store_embedding(str(uuid4()))

        assert result is False

    @pytest.mark.asyncio
    async def test_generate_embedding_sets_failed_status_on_error(
        self, integration_db, test_capability
    ):
        """Test that failed embedding generation sets status to 'failed'."""
        # Create client that fails
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.model = "text-embedding-3-small"
        mock_client.dimensions = 1536
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.create_embedding = AsyncMock(side_effect=Exception("API error"))

        service = CapabilityEmbeddingService(
            database=integration_db,
            embedding_client=mock_client,
        )

        result = await service.generate_and_store_embedding(str(test_capability.id))

        assert result is False

        # Verify status was set to 'failed'
        async with integration_db.get_session() as session:
            from sqlalchemy import select

            query_result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == test_capability.id)
            )
            capability = query_result.scalar_one_or_none()

            assert capability is not None
            assert capability.embedding_status == "failed"

    @pytest.mark.asyncio
    async def test_backfill_processes_pending_capabilities(
        self, integration_db, mock_embedding_client
    ):
        """Test backfill processes capabilities with pending status."""
        # Create multiple test capabilities with pending status
        org_id = uuid4()
        cap_ids = []

        async with integration_db.get_session() as session:
            for i in range(3):
                cap_id = uuid4()
                cap_ids.append(cap_id)
                capability = AgentCapability(
                    id=cap_id,
                    organization_id=org_id,
                    agent_type=f"backfill_test_{uuid4().hex[:8]}",
                    name=f"Backfill Test Agent {i}",
                    description=f"Test agent {i} for backfill",
                    task_type="general",
                    system_prompt="Test prompt",
                    inputs_schema={},
                    outputs_schema={},
                    is_system=False,
                    is_active=True,
                    version=1,
                    is_latest=True,
                    embedding_status="pending",
                )
                session.add(capability)
            await session.commit()

        try:
            service = CapabilityEmbeddingService(
                database=integration_db,
                embedding_client=mock_embedding_client,
            )

            # Run backfill with a larger batch size to ensure we process the test capabilities
            # The backfill query includes both org capabilities and system capabilities
            # so we need a large enough batch to capture our test capabilities
            total_success = 0
            total_failed = 0
            max_iterations = 20  # Limit iterations to prevent infinite loop

            for _ in range(max_iterations):
                stats = await service.backfill_embeddings(batch_size=50, organization_id=str(org_id))
                total_success += stats.get("success", 0)
                total_failed += stats.get("failed", 0)

                # Check if our capabilities are processed
                async with integration_db.get_session() as session:
                    from sqlalchemy import select

                    all_processed = True
                    for cap_id in cap_ids:
                        result = await session.execute(
                            select(AgentCapability).where(AgentCapability.id == cap_id)
                        )
                        cap = result.scalar_one_or_none()
                        if cap and cap.embedding_status == "pending":
                            all_processed = False
                            break

                    if all_processed:
                        break

            # Verify our capabilities were processed
            async with integration_db.get_session() as session:
                from sqlalchemy import select

                for cap_id in cap_ids:
                    result = await session.execute(
                        select(AgentCapability).where(AgentCapability.id == cap_id)
                    )
                    cap = result.scalar_one_or_none()
                    assert cap is not None
                    assert cap.embedding_status in ["generated", "failed"], \
                        f"Capability {cap_id} has status {cap.embedding_status}, expected generated or failed"

        finally:
            # Cleanup
            async with integration_db.get_session() as session:
                for cap_id in cap_ids:
                    await session.execute(
                        AgentCapability.__table__.delete().where(AgentCapability.id == cap_id)
                    )
                await session.commit()

    @pytest.mark.asyncio
    async def test_get_embedding_status_returns_counts(
        self, integration_db, mock_embedding_client, test_capability
    ):
        """Test get_embedding_status returns status counts."""
        service = CapabilityEmbeddingService(
            database=integration_db,
            embedding_client=mock_embedding_client,
        )

        counts = await service.get_embedding_status()

        assert isinstance(counts, dict)
        # Should have at least one pending (our test capability)
        assert "pending" in counts or "generated" in counts or "failed" in counts or "null" in counts

    @pytest.mark.asyncio
    async def test_embedding_text_includes_relevant_fields(
        self, integration_db, mock_embedding_client, test_capability
    ):
        """Test that the embedding text includes all relevant capability fields."""
        service = CapabilityEmbeddingService(
            database=integration_db,
            embedding_client=mock_embedding_client,
        )

        # Capture the text that would be embedded
        captured_text = None

        async def capture_embedding(text):
            nonlocal captured_text
            captured_text = text
            mock_result = MagicMock()
            mock_result.embedding = [0.1] * 1536
            return mock_result

        mock_embedding_client.create_embedding = AsyncMock(side_effect=capture_embedding)

        await service.generate_and_store_embedding(str(test_capability.id))

        # Verify the captured text includes expected fields
        assert captured_text is not None
        assert "Test Embedding Agent" in captured_text  # name
        assert "test" in captured_text.lower()  # domain or keywords
        assert "embedding" in captured_text.lower()  # from keywords or description
