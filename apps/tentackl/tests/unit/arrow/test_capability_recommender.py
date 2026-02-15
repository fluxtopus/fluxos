"""Unit tests for CapabilityRecommender.

Tests for CAP-015 - the capability recommender that searches capabilities_agents
instead of agent_specs.
"""

from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.infrastructure.flux_runtime.capability_recommender import CapabilityRecommender, CapabilityMatch


@pytest.fixture
def mock_database():
    """Create a mock database instance."""
    return MagicMock()


@pytest.fixture
def recommender(mock_database):
    """Create a CapabilityRecommender instance."""
    return CapabilityRecommender(mock_database)


class TestCapabilityMatch:
    """Test suite for CapabilityMatch dataclass."""

    def test_capability_match_creation(self):
        """Test creating a CapabilityMatch."""
        match = CapabilityMatch(
            id="test-id",
            agent_type="summarize",
            name="Summarize Agent",
            description="Summarizes text",
            domain="content",
            tags=["text", "nlp"],
            similarity=0.85,
            match_type="semantic",
            is_system=True,
            inputs_schema={"text": {"type": "string"}},
            outputs_schema={"summary": {"type": "string"}},
            usage_count=100,
            success_rate=0.95
        )

        assert match.id == "test-id"
        assert match.agent_type == "summarize"
        assert match.name == "Summarize Agent"
        assert match.description == "Summarizes text"
        assert match.domain == "content"
        assert match.tags == ["text", "nlp"]
        assert match.similarity == 0.85
        assert match.match_type == "semantic"
        assert match.is_system is True
        assert match.inputs_schema == {"text": {"type": "string"}}
        assert match.outputs_schema == {"summary": {"type": "string"}}
        assert match.usage_count == 100
        assert match.success_rate == 0.95

    def test_capability_match_custom_capability(self):
        """Test creating a match for a custom (non-system) capability."""
        match = CapabilityMatch(
            id="custom-id",
            agent_type="my_custom_agent",
            name="My Agent",
            description="Custom agent",
            domain="custom",
            tags=[],
            similarity=0.7,
            match_type="keyword",
            is_system=False,
            inputs_schema={},
            outputs_schema={},
            usage_count=5,
            success_rate=0.8
        )

        assert match.is_system is False
        assert match.match_type == "keyword"


class TestCapabilityRecommenderInit:
    """Test suite for CapabilityRecommender initialization."""

    def test_init_stores_database(self, mock_database):
        """Test that recommender stores database reference."""
        recommender = CapabilityRecommender(mock_database)
        assert recommender.database is mock_database


class TestKeywordScoreCalculation:
    """Test suite for keyword score calculation."""

    def test_calculate_keyword_score_name_match(self, recommender):
        """Test that name matches get highest weight."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarize"],
            name="Summarize Agent",
            description="An agent",
            agent_type="some_type",
            tags=[],
            keywords=[]
        )
        # Name match = 2 points, max = 2 points, score = 1.0
        assert score == 1.0

    def test_calculate_keyword_score_agent_type_match(self, recommender):
        """Test that agent_type matches get high weight."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarize"],
            name="Agent",
            description="An agent",
            agent_type="summarize",
            tags=[],
            keywords=[]
        )
        # agent_type match = 1.5 points, max = 2 points, score = 0.75
        assert score == 0.75

    def test_calculate_keyword_score_description_match(self, recommender):
        """Test that description matches get medium weight."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarize"],
            name="Agent",
            description="This agent can summarize text",
            agent_type="text_agent",
            tags=[],
            keywords=[]
        )
        # description match = 1 point, max = 2 points, score = 0.5
        assert score == 0.5

    def test_calculate_keyword_score_tag_match(self, recommender):
        """Test that tag matches get medium weight."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarization"],
            name="Agent",
            description="An agent",
            agent_type="text_agent",
            tags=["summarization", "nlp"],
            keywords=[]
        )
        # tag match = 1 point, max = 2 points, score = 0.5
        assert score == 0.5

    def test_calculate_keyword_score_keyword_match(self, recommender):
        """Test that keyword matches get medium weight."""
        score = recommender._calculate_keyword_score(
            search_terms=["condense"],
            name="Agent",
            description="An agent",
            agent_type="text_agent",
            tags=[],
            keywords=["condense", "shorten"]
        )
        # keyword match = 1 point, max = 2 points, score = 0.5
        assert score == 0.5

    def test_calculate_keyword_score_multiple_terms(self, recommender):
        """Test score with multiple search terms."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarize", "text"],
            name="Summarize Text Agent",
            description="An agent",
            agent_type="type",
            tags=[],
            keywords=[]
        )
        # Both terms match name = 2 + 2 = 4 points, max = 4 points, score = 1.0
        assert score == 1.0

    def test_calculate_keyword_score_partial_match(self, recommender):
        """Test score when only some terms match."""
        score = recommender._calculate_keyword_score(
            search_terms=["summarize", "video"],
            name="Summarize Agent",
            description="Text processing",
            agent_type="type",
            tags=[],
            keywords=[]
        )
        # "summarize" matches name = 2 points, "video" no match
        # max = 4 points, score = 0.5
        assert score == 0.5

    def test_calculate_keyword_score_no_match(self, recommender):
        """Test score when no terms match."""
        score = recommender._calculate_keyword_score(
            search_terms=["video", "streaming"],
            name="Text Agent",
            description="Processes text",
            agent_type="text_type",
            tags=["text"],
            keywords=["document"]
        )
        assert score == 0.0

    def test_calculate_keyword_score_empty_terms(self, recommender):
        """Test score with empty search terms."""
        score = recommender._calculate_keyword_score(
            search_terms=[],
            name="Agent",
            description="Description",
            agent_type="type",
            tags=["tag"],
            keywords=["keyword"]
        )
        assert score == 0.0

    def test_calculate_keyword_score_case_insensitive(self, recommender):
        """Test that score calculation is case insensitive."""
        score = recommender._calculate_keyword_score(
            search_terms=["SUMMARIZE"],
            name="summarize agent",
            description="An agent",
            agent_type="type",
            tags=[],
            keywords=[]
        )
        assert score == 1.0


class TestCreateMatch:
    """Test suite for _create_match method."""

    def test_create_match_basic(self, recommender):
        """Test creating a match from a capability."""
        # Create a mock capability
        capability = MagicMock()
        capability.id = "cap-123"
        capability.agent_type = "summarize"
        capability.name = "Summarize Agent"
        capability.description = "Summarizes text"
        capability.domain = "content"
        capability.tags = ["text", "nlp"]
        capability.is_system = True
        capability.inputs_schema = {"text": {"type": "string"}}
        capability.outputs_schema = {"summary": {"type": "string"}}
        capability.usage_count = 100
        capability.success_count = 95

        match = recommender._create_match(capability, similarity=0.85, match_type="semantic")

        assert match.id == "cap-123"
        assert match.agent_type == "summarize"
        assert match.name == "Summarize Agent"
        assert match.description == "Summarizes text"
        assert match.domain == "content"
        assert match.tags == ["text", "nlp"]
        assert match.similarity == 0.85
        assert match.match_type == "semantic"
        assert match.is_system is True
        assert match.inputs_schema == {"text": {"type": "string"}}
        assert match.outputs_schema == {"summary": {"type": "string"}}
        assert match.usage_count == 100
        assert match.success_rate == 0.95

    def test_create_match_zero_usage(self, recommender):
        """Test creating a match with zero usage."""
        capability = MagicMock()
        capability.id = "cap-456"
        capability.agent_type = "new_agent"
        capability.name = "New Agent"
        capability.description = "A new agent"
        capability.domain = "general"
        capability.tags = []
        capability.is_system = False
        capability.inputs_schema = {}
        capability.outputs_schema = {}
        capability.usage_count = 0
        capability.success_count = 0

        match = recommender._create_match(capability, similarity=0.5, match_type="keyword")

        assert match.usage_count == 0
        assert match.success_rate == 0.0  # 0/0 = 0

    def test_create_match_null_values(self, recommender):
        """Test creating a match with null/None values."""
        capability = MagicMock()
        capability.id = "cap-789"
        capability.agent_type = "basic"
        capability.name = None
        capability.description = None
        capability.domain = None
        capability.tags = None
        capability.is_system = True
        capability.inputs_schema = None
        capability.outputs_schema = None
        capability.usage_count = None
        capability.success_count = None

        match = recommender._create_match(capability, similarity=0.3, match_type="keyword")

        assert match.name == "basic"  # Falls back to agent_type
        assert match.description == ""
        assert match.domain == ""
        assert match.tags == []
        assert match.inputs_schema == {}
        assert match.outputs_schema == {}
        assert match.usage_count == 0
        assert match.success_rate == 0.0


class TestSearchAndRank:
    """Test suite for search_and_rank method."""

    @pytest.mark.asyncio
    async def test_search_and_rank_uses_semantic_search_first(self, recommender, mock_database):
        """Test that semantic search is tried first."""
        # Mock the database session
        mock_session = AsyncMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock()

        # Mock semantic search to return results
        mock_capability = MagicMock()
        mock_capability.id = "cap-1"
        mock_capability.agent_type = "summarize"
        mock_capability.name = "Summarize"
        mock_capability.description = "Summarizes"
        mock_capability.domain = "content"
        mock_capability.tags = []
        mock_capability.is_system = True
        mock_capability.inputs_schema = {}
        mock_capability.outputs_schema = {}
        mock_capability.usage_count = 10
        mock_capability.success_count = 9

        with patch.object(recommender, '_semantic_search', return_value=[
            CapabilityMatch(
                id="cap-1",
                agent_type="summarize",
                name="Summarize",
                description="Summarizes",
                domain="content",
                tags=[],
                similarity=0.9,
                match_type="semantic",
                is_system=True,
                inputs_schema={},
                outputs_schema={},
                usage_count=10,
                success_rate=0.9
            )
        ]) as mock_semantic:
            with patch.object(recommender, '_keyword_search') as mock_keyword:
                results = await recommender.search_and_rank(query="summarize text")

                # Semantic search was called
                mock_semantic.assert_called_once()
                # Keyword search was NOT called (semantic returned results)
                mock_keyword.assert_not_called()

                assert len(results) == 1
                assert results[0].match_type == "semantic"

    @pytest.mark.asyncio
    async def test_search_and_rank_falls_back_to_keyword(self, recommender, mock_database):
        """Test that keyword search is used when semantic fails."""
        mock_session = AsyncMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock()

        with patch.object(recommender, '_semantic_search', return_value=[]) as mock_semantic:
            with patch.object(recommender, '_keyword_search', return_value=[
                CapabilityMatch(
                    id="cap-2",
                    agent_type="text_processor",
                    name="Text Processor",
                    description="Processes text",
                    domain="content",
                    tags=["text"],
                    similarity=0.7,
                    match_type="keyword",
                    is_system=True,
                    inputs_schema={},
                    outputs_schema={},
                    usage_count=5,
                    success_rate=0.8
                )
            ]) as mock_keyword:
                results = await recommender.search_and_rank(query="process text")

                # Semantic search was called but returned empty
                mock_semantic.assert_called_once()
                # Keyword search was called as fallback
                mock_keyword.assert_called_once()

                assert len(results) == 1
                assert results[0].match_type == "keyword"

    @pytest.mark.asyncio
    async def test_search_and_rank_passes_filters(self, recommender, mock_database):
        """Test that filters are passed to search methods."""
        mock_session = AsyncMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock()

        with patch.object(recommender, '_semantic_search', return_value=[]) as mock_semantic:
            with patch.object(recommender, '_keyword_search', return_value=[]) as mock_keyword:
                await recommender.search_and_rank(
                    query="test",
                    domain="content",
                    tags=["text"],
                    organization_id="org-123",
                    include_system=False,
                    limit=5
                )

                # Verify semantic search received all filters
                mock_semantic.assert_called_once()
                call_args = mock_semantic.call_args
                assert call_args.kwargs["domain"] == "content"
                assert call_args.kwargs["tags"] == ["text"]
                assert call_args.kwargs["organization_id"] == "org-123"
                assert call_args.kwargs["include_system"] is False
                assert call_args.kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_search_and_rank_empty_results(self, recommender, mock_database):
        """Test handling of no results."""
        mock_session = AsyncMock()
        mock_database.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_database.get_session.return_value.__aexit__ = AsyncMock()

        with patch.object(recommender, '_semantic_search', return_value=[]):
            with patch.object(recommender, '_keyword_search', return_value=[]):
                results = await recommender.search_and_rank(query="nonexistent")

                assert results == []


class TestGenerateQueryEmbedding:
    """Test suite for _generate_query_embedding method."""

    @pytest.mark.asyncio
    async def test_generate_query_embedding_success(self, recommender):
        """Test successful embedding generation."""
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]

        # Create mock context manager client
        mock_client_instance = AsyncMock()
        mock_client_instance.embeddings.create = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.llm.get_embedding_client", return_value=mock_client):
            embedding = await recommender._generate_query_embedding("test query")

            assert embedding == [0.1, 0.2, 0.3]
            mock_client_instance.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small",
                input="test query",
                dimensions=1536
            )

    @pytest.mark.asyncio
    async def test_generate_query_embedding_no_client(self, recommender):
        """Test behavior when no embedding client is available."""
        with patch("src.llm.get_embedding_client", return_value=None):
            embedding = await recommender._generate_query_embedding("test query")
            assert embedding is None

    @pytest.mark.asyncio
    async def test_generate_query_embedding_not_configured(self, recommender):
        """Test behavior when embedding client is not configured."""
        mock_client = MagicMock()
        mock_client.is_configured = False

        with patch("src.llm.get_embedding_client", return_value=mock_client):
            embedding = await recommender._generate_query_embedding("test query")
            assert embedding is None

    @pytest.mark.asyncio
    async def test_generate_query_embedding_error(self, recommender):
        """Test handling of embedding generation errors."""
        mock_client_instance = AsyncMock()
        mock_client_instance.embeddings.create = AsyncMock(side_effect=Exception("API error"))

        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.llm.get_embedding_client", return_value=mock_client):
            embedding = await recommender._generate_query_embedding("test query")
            assert embedding is None  # Returns None on error, doesn't raise
