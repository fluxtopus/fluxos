"""Unit tests for SearchAgentsTool.

Updated for CAP-015 to use CapabilityRecommender instead of AgentRecommender.
"""

from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.arrow.tools.search_agents import SearchAgentsTool
from src.infrastructure.flux_runtime.tools.base import ToolResult
from src.infrastructure.flux_runtime.capability_recommender import CapabilityMatch


@pytest.fixture
def search_tool():
    """Create a SearchAgentsTool instance."""
    return SearchAgentsTool()


@pytest.fixture
def mock_capability_match():
    """Create a mock CapabilityMatch."""
    return CapabilityMatch(
        id="08417f68-9365-46d3-a4d6-504c9cfc9d67",
        agent_type="summarize",
        name="Summarize Agent",
        description="Summarizes text content using advanced NLP",
        domain="content",
        tags=["text", "nlp", "summarization"],
        similarity=0.92,
        match_type="semantic",
        is_system=True,
        inputs_schema={"text": {"type": "string", "required": True}},
        outputs_schema={"summary": {"type": "string"}},
        usage_count=150,
        success_rate=0.95
    )


class TestSearchAgentsTool:
    """Test suite for SearchAgentsTool."""

    def test_name(self, search_tool):
        """Test that tool has correct name."""
        assert search_tool.name == "search_agents"

    def test_description(self, search_tool):
        """Test that tool has descriptive text."""
        assert "Search the capability registry" in search_tool.description
        assert "BEFORE creating tasks or agents" in search_tool.description
        assert "custom capabilities" in search_tool.description

    def test_get_definition(self, search_tool):
        """Test that tool definition is correctly formatted."""
        definition = search_tool.get_definition()

        assert definition.name == "search_agents"
        assert definition.description == search_tool.description

        # Check parameters
        params = definition.parameters
        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "domain" in params["properties"]  # Changed from category
        assert "tags" in params["properties"]
        assert "limit" in params["properties"]
        assert "include_system" in params["properties"]  # New parameter
        assert params["required"] == ["query"]

    @pytest.mark.asyncio
    async def test_execute_missing_query(self, search_tool):
        """Test that execute fails when query is missing."""
        result = await search_tool.execute(
            arguments={},
            context={}
        )

        assert result.success is False
        assert "query parameter is required" in result.error

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, search_tool):
        """Test that execute fails when query is empty."""
        result = await search_tool.execute(
            arguments={"query": "   "},
            context={}
        )

        assert result.success is False
        assert "query parameter is required" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_matches(self, search_tool):
        """Test execute when no capabilities match."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[])

        result = await search_tool.execute(
            arguments={"query": "nonexistent functionality"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert result.data["capabilities"] == []
        assert result.data["count"] == 0
        assert "No capabilities found" in result.message
        assert "custom capability" in result.message

    @pytest.mark.asyncio
    async def test_execute_single_excellent_match(self, search_tool, mock_capability_match):
        """Test execute with a single excellent match."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[mock_capability_match])

        result = await search_tool.execute(
            arguments={"query": "summarize text"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert len(result.data["capabilities"]) == 1
        assert result.data["count"] == 1

        cap_data = result.data["capabilities"][0]
        assert cap_data["agent_type"] == "summarize"
        assert cap_data["name"] == "Summarize Agent"
        assert cap_data["similarity"] == 0.92
        assert cap_data["match_type"] == "semantic"
        assert cap_data["is_system"] is True
        assert cap_data["is_custom"] is False
        assert cap_data["inputs_schema"] == {"text": {"type": "string", "required": True}}
        assert cap_data["outputs_schema"] == {"summary": {"type": "string"}}
        assert cap_data["usage_count"] == 150
        assert cap_data["success_rate"] == 0.95

        assert "excellent match" in result.message.lower()
        assert "summarize" in result.message

    @pytest.mark.asyncio
    async def test_execute_multiple_matches(self, search_tool, mock_capability_match):
        """Test execute with multiple matches."""
        # Create multiple matches with different similarity scores
        matches = [
            mock_capability_match,
            CapabilityMatch(
                id="another-id",
                agent_type="text_transformer",
                name="Text Transformer",
                description="Transforms text content",
                domain="content",
                tags=["text", "transformation"],
                similarity=0.75,
                match_type="keyword",
                is_system=True,
                inputs_schema={"text": {"type": "string"}},
                outputs_schema={"result": {"type": "string"}},
                usage_count=50,
                success_rate=0.90
            ),
            CapabilityMatch(
                id="third-id",
                agent_type="custom_summarizer",
                name="Custom Summarizer",
                description="Organization-specific summarizer",
                domain="content",
                tags=["custom", "summarization"],
                similarity=0.60,
                match_type="keyword",
                is_system=False,  # Custom capability
                inputs_schema={"input": {"type": "string"}},
                outputs_schema={"output": {"type": "string"}},
                usage_count=10,
                success_rate=0.80
            )
        ]

        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=matches)

        result = await search_tool.execute(
            arguments={"query": "summarize", "limit": 5},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert len(result.data["capabilities"]) == 3
        assert result.data["count"] == 3
        assert "summarize" in result.message

        # Verify custom capability is marked correctly
        custom_cap = next(c for c in result.data["capabilities"] if c["agent_type"] == "custom_summarizer")
        assert custom_cap["is_system"] is False
        assert custom_cap["is_custom"] is True

    @pytest.mark.asyncio
    async def test_execute_low_similarity_match(self, search_tool):
        """Test execute with low similarity matches."""
        low_similarity_match = CapabilityMatch(
            id="low-sim-id",
            agent_type="generic_processor",
            name="Generic Processor",
            description="Generic data processor",
            domain="analytics",
            tags=["generic"],
            similarity=0.35,
            match_type="keyword",
            is_system=True,
            inputs_schema={"data": {"type": "object"}},
            outputs_schema={"result": {"type": "object"}},
            usage_count=5,
            success_rate=0.50
        )

        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[low_similarity_match])

        result = await search_tool.execute(
            arguments={"query": "specific task"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert "similarity is low" in result.message.lower()
        assert "specialized capability" in result.message.lower()

    @pytest.mark.asyncio
    async def test_execute_with_filters(self, search_tool, mock_capability_match):
        """Test execute with domain and tag filters."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[mock_capability_match])

        result = await search_tool.execute(
            arguments={
                "query": "summarize",
                "domain": "content",
                "tags": ["text", "nlp"],
                "limit": 5,
                "include_system": True
            },
            context={
                "capability_recommender": mock_recommender,
                "organization_id": "org-123"
            }
        )

        # Verify recommender was called with correct arguments
        mock_recommender.search_and_rank.assert_called_once_with(
            query="summarize",
            domain="content",
            tags=["text", "nlp"],
            organization_id="org-123",
            include_system=True,
            limit=5
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_creates_recommender_when_missing(self, search_tool, mock_capability_match):
        """Test that execute creates a recommender if not in context."""
        # Patch at the source module paths (where they're imported from inside execute())
        with patch("src.infrastructure.flux_runtime.capability_recommender.CapabilityRecommender") as mock_recommender_class:
            mock_recommender_instance = AsyncMock()
            mock_recommender_instance.search_and_rank = AsyncMock(return_value=[mock_capability_match])
            mock_recommender_class.return_value = mock_recommender_instance

            # Mock the database getter (from api.app)
            mock_database = MagicMock()
            with patch("src.api.app.get_database", return_value=mock_database):
                result = await search_tool.execute(
                    arguments={"query": "test"},
                    context={}  # No recommender in context
                )

                # Verify recommender was created
                mock_recommender_class.assert_called_once_with(mock_database)

                assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_uses_database_from_context(self, search_tool, mock_capability_match):
        """Test that execute uses database from context when available."""
        # Patch at the source module path
        with patch("src.infrastructure.flux_runtime.capability_recommender.CapabilityRecommender") as mock_recommender_class:
            mock_recommender_instance = AsyncMock()
            mock_recommender_instance.search_and_rank = AsyncMock(return_value=[mock_capability_match])
            mock_recommender_class.return_value = mock_recommender_instance

            mock_database = MagicMock()

            result = await search_tool.execute(
                arguments={"query": "test"},
                context={"database": mock_database}  # Database in context
            )

            # Verify recommender was created with context database
            mock_recommender_class.assert_called_once_with(mock_database)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_handles_errors(self, search_tool):
        """Test that execute handles errors gracefully."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(side_effect=Exception("Database connection failed"))

        result = await search_tool.execute(
            arguments={"query": "test"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is False
        assert "Capability search error" in result.error
        assert "Database connection failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_respects_limit(self, search_tool):
        """Test that limit parameter is passed correctly."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[])

        await search_tool.execute(
            arguments={"query": "test", "limit": 3},
            context={"capability_recommender": mock_recommender}
        )

        mock_recommender.search_and_rank.assert_called_once_with(
            query="test",
            domain=None,
            tags=[],
            organization_id=None,
            include_system=True,
            limit=3
        )

    @pytest.mark.asyncio
    async def test_execute_default_limit(self, search_tool):
        """Test that default limit is 10."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[])

        await search_tool.execute(
            arguments={"query": "test"},
            context={"capability_recommender": mock_recommender}
        )

        mock_recommender.search_and_rank.assert_called_once_with(
            query="test",
            domain=None,
            tags=[],
            organization_id=None,
            include_system=True,
            limit=10
        )

    @pytest.mark.asyncio
    async def test_execute_passes_organization_id(self, search_tool):
        """Test that organization_id from context is passed to recommender."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[])

        await search_tool.execute(
            arguments={"query": "test"},
            context={
                "capability_recommender": mock_recommender,
                "organization_id": "org-456"
            }
        )

        mock_recommender.search_and_rank.assert_called_once_with(
            query="test",
            domain=None,
            tags=[],
            organization_id="org-456",
            include_system=True,
            limit=10
        )

    @pytest.mark.asyncio
    async def test_execute_exclude_system_capabilities(self, search_tool, mock_capability_match):
        """Test that include_system=false excludes system capabilities."""
        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[mock_capability_match])

        await search_tool.execute(
            arguments={"query": "test", "include_system": False},
            context={
                "capability_recommender": mock_recommender,
                "organization_id": "org-789"
            }
        )

        mock_recommender.search_and_rank.assert_called_once_with(
            query="test",
            domain=None,
            tags=[],
            organization_id="org-789",
            include_system=False,
            limit=10
        )

    @pytest.mark.asyncio
    async def test_execute_custom_capability_marked_in_message(self, search_tool):
        """Test that custom capabilities are marked with [custom] in message."""
        custom_match = CapabilityMatch(
            id="custom-id",
            agent_type="my_custom_agent",
            name="My Custom Agent",
            description="Custom agent for my organization",
            domain="custom",
            tags=["custom"],
            similarity=0.88,
            match_type="keyword",
            is_system=False,  # Custom capability
            inputs_schema={},
            outputs_schema={},
            usage_count=5,
            success_rate=1.0
        )

        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[custom_match])

        result = await search_tool.execute(
            arguments={"query": "custom task"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert "[custom]" in result.message

    @pytest.mark.asyncio
    async def test_execute_moderate_similarity_message(self, search_tool):
        """Test message for moderate similarity (0.5-0.8)."""
        moderate_match = CapabilityMatch(
            id="mod-id",
            agent_type="moderate_match",
            name="Moderate Match",
            description="Moderate match capability",
            domain="general",
            tags=[],
            similarity=0.65,
            match_type="keyword",
            is_system=True,
            inputs_schema={},
            outputs_schema={},
            usage_count=10,
            success_rate=0.70
        )

        mock_recommender = AsyncMock()
        mock_recommender.search_and_rank = AsyncMock(return_value=[moderate_match])

        result = await search_tool.execute(
            arguments={"query": "test"},
            context={"capability_recommender": mock_recommender}
        )

        assert result.success is True
        assert "potential matches" in result.message.lower()
        assert "0.65" in result.message  # Similarity shown
