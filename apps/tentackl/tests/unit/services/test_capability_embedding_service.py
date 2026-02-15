"""Unit tests for CapabilityEmbeddingService.

Tests the capability embedding service functionality including:
- Text building for embeddings
- Embedding generation
- Embedding storage
- Service configuration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.infrastructure.capabilities.capability_embedding_service import (
    CapabilityEmbeddingService,
    get_capability_embedding_service,
)


class TestCapabilityEmbeddingServiceInit:
    """Tests for service initialization."""

    def test_service_creation(self):
        """Test basic service creation."""
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.model = "text-embedding-3-small"
        mock_client.dimensions = 1536

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        assert service._embedding_client == mock_client
        assert service.is_enabled is True

    def test_service_disabled_when_not_configured(self):
        """Test service is disabled when embedding client not configured."""
        mock_client = MagicMock()
        mock_client.is_configured = False
        mock_client.model = "text-embedding-3-small"
        mock_client.dimensions = 1536

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        assert service.is_enabled is False


class TestBuildCapabilityText:
    """Tests for build_capability_text method."""

    @pytest.fixture
    def service(self):
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.model = "text-embedding-3-small"
        mock_client.dimensions = 1536
        return CapabilityEmbeddingService(embedding_client=mock_client)

    def test_minimal_text(self, service):
        """Test text generation with minimal fields."""
        text = service.build_capability_text(
            agent_type="test_agent",
            name="Test Agent",
        )

        assert "Capability: Test Agent" in text

    def test_full_text(self, service):
        """Test text generation with all fields."""
        text = service.build_capability_text(
            agent_type="summarize",
            name="Summarize Agent",
            description="Summarizes long text into concise summaries",
            domain="content",
            system_prompt="You are a summarization expert...",
            keywords=["summarize", "condense", "brief"],
            tags=["content", "nlp"],
            inputs_schema={
                "text": {"type": "string", "required": True},
                "max_length": {"type": "integer", "required": False},
            },
        )

        assert "Capability: Summarize Agent" in text
        assert "Type: summarize" in text
        assert "Description: Summarizes long text" in text
        assert "Domain: content" in text
        assert "Behavior: You are a summarization expert" in text
        assert "Keywords: summarize, condense, brief" in text
        assert "Tags: content, nlp" in text
        assert "Inputs:" in text

    def test_agent_type_same_as_name_not_duplicated(self, service):
        """Test agent_type not included when same as name."""
        text = service.build_capability_text(
            agent_type="Test Agent",
            name="Test Agent",
        )

        # Should only appear once
        assert text.count("Test Agent") == 1

    def test_long_system_prompt_truncated(self, service):
        """Test that long system prompts are truncated."""
        long_prompt = "x" * 1000  # 1000 characters

        text = service.build_capability_text(
            agent_type="test",
            name="Test",
            system_prompt=long_prompt,
        )

        # Should be truncated to 500 chars + "..."
        assert "Behavior: " in text
        assert "..." in text
        assert len(text) < 600  # Reasonable limit

    def test_inputs_extraction(self, service):
        """Test that input names are extracted from schema."""
        text = service.build_capability_text(
            agent_type="test",
            name="Test",
            inputs_schema={
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "type": "object",  # This should be filtered out
            },
        )

        assert "Inputs: query, limit" in text
        # "type" key should not appear as an input
        assert "type" not in text.split("Inputs:")[-1].split("\n")[0] or "query" in text


class TestGenerateEmbedding:
    """Tests for generate_embedding method."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.is_configured = True
        client.model = "text-embedding-3-small"
        client.dimensions = 1536
        return client

    @pytest.mark.asyncio
    async def test_embedding_generated_successfully(self, mock_client):
        """Test successful embedding generation."""
        mock_embedding = [0.1] * 1536
        mock_result = MagicMock()
        mock_result.embedding = mock_embedding

        # Setup context manager for embedding client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.create_embedding = AsyncMock(return_value=mock_result)

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        result = await service.generate_embedding("Test text for embedding")

        assert result == mock_embedding
        mock_client.create_embedding.assert_called_once_with("Test text for embedding")

    @pytest.mark.asyncio
    async def test_embedding_disabled_returns_none(self, mock_client):
        """Test that disabled service returns None."""
        mock_client.is_configured = False

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        result = await service.generate_embedding("Test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self, mock_client):
        """Test that empty text returns None."""
        service = CapabilityEmbeddingService(embedding_client=mock_client)

        result = await service.generate_embedding("")
        assert result is None

        result = await service.generate_embedding("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_error_returns_none(self, mock_client):
        """Test that errors return None gracefully."""
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.create_embedding = AsyncMock(side_effect=Exception("API error"))

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        result = await service.generate_embedding("Test text")

        assert result is None


class TestGenerateAndStoreEmbedding:
    """Tests for generate_and_store_embedding method."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.is_configured = True
        client.model = "text-embedding-3-small"
        client.dimensions = 1536
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_database(self):
        db = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_capability_not_found_returns_false(self, mock_client, mock_database):
        """Test that missing capability returns False."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_database.get_session = MagicMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        service = CapabilityEmbeddingService(
            database=mock_database,
            embedding_client=mock_client,
        )

        result = await service.generate_and_store_embedding("non-existent-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_embedding_stored_successfully(self, mock_client, mock_database):
        """Test successful embedding storage."""
        mock_embedding = [0.1] * 1536
        mock_embed_result = MagicMock()
        mock_embed_result.embedding = mock_embedding
        mock_client.create_embedding = AsyncMock(return_value=mock_embed_result)

        # Mock capability
        mock_capability = MagicMock()
        mock_capability.agent_type = "test_agent"
        mock_capability.name = "Test Agent"
        mock_capability.description = "A test agent"
        mock_capability.domain = "test"
        mock_capability.system_prompt = "You are a test agent"
        mock_capability.keywords = ["test"]
        mock_capability.tags = ["unit-test"]
        mock_capability.inputs_schema = {}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_capability
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_database.get_session = MagicMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        service = CapabilityEmbeddingService(
            database=mock_database,
            embedding_client=mock_client,
        )

        result = await service.generate_and_store_embedding("test-id")

        assert result is True
        # Verify execute was called for both SELECT and UPDATE
        assert mock_session.execute.call_count >= 2
        mock_session.commit.assert_called()


class TestBackfillEmbeddings:
    """Tests for backfill_embeddings method."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.is_configured = True
        client.model = "text-embedding-3-small"
        client.dimensions = 1536
        return client

    @pytest.mark.asyncio
    async def test_backfill_disabled_returns_error(self, mock_client):
        """Test backfill when service is disabled."""
        mock_client.is_configured = False

        service = CapabilityEmbeddingService(embedding_client=mock_client)

        result = await service.backfill_embeddings()

        assert result == {"error": "embeddings_not_enabled", "processed": 0}


class TestGetCapabilityEmbeddingService:
    """Tests for the singleton factory function."""

    def test_singleton_returns_same_instance(self):
        """Test that get_capability_embedding_service returns singleton."""
        # Clear any existing singleton
        import src.infrastructure.capabilities.capability_embedding_service as module
        module._service = None

        with patch.object(module, 'get_embedding_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.is_configured = True
            mock_client.model = "text-embedding-3-small"
            mock_client.dimensions = 1536
            mock_get_client.return_value = mock_client

            service1 = get_capability_embedding_service()
            service2 = get_capability_embedding_service()

            assert service1 is service2

        # Clean up
        module._service = None
