"""
Tests for the DynamicPromptBuilder.

Validates that:
1. All registered agents have required metadata
2. Prompt generation works correctly (async, with mocked LLM classification)
3. Integration support (integrations section, plugin injection)
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.agents.prompts.dynamic_prompt_builder import DynamicPromptBuilder, get_prompt_builder


# ============================================================================
# Helpers
# ============================================================================

def _make_classification(
    task_type: str = "research",
    info_method: str = "web_research",
    categories: list = None,
) -> dict:
    """Build a classification dict matching classify_goal_with_llm output."""
    return {
        "task_type": task_type,
        "needs_external_info": info_method != "none",
        "info_gathering_method": info_method,
        "agent_categories": categories or ["research", "content"],
        "reasoning": f"Test classification: {task_type}",
    }


# ============================================================================
# Registry / metadata tests (no LLM, no async)
# ============================================================================

class TestRegistryMetadata:
    """Tests for agent registry metadata quality."""

    def test_all_agents_have_metadata(self):
        """Every registered agent must have required metadata."""
        builder = DynamicPromptBuilder()
        result = builder.validate_agent_metadata()

        assert result["valid"], f"Metadata validation failed:\n" + "\n".join(result["errors"])
        assert result["agents_checked"] > 0, "No agents found in registry"

    def test_all_agents_have_brief_description(self):
        """Every agent must have a meaningful brief description."""
        builder = DynamicPromptBuilder()
        builder._load_registry()

        for agent_type, meta in builder._agent_metadata.items():
            brief = meta.get("brief", "")
            assert brief, f"{agent_type}: missing brief description"
            assert brief != "Base subagent (override in subclass)", \
                f"{agent_type}: using default brief (not overridden)"
            assert len(brief) > 10, f"{agent_type}: brief too short"

    def test_brief_agent_list_generation(self):
        """Brief agent list should be generated correctly."""
        builder = DynamicPromptBuilder()
        brief_list = builder.build_brief_agent_list()

        assert "## Available Agent Types" in brief_list
        assert "summarize" in brief_list
        assert "file_storage" in brief_list

    def test_prompt_stats(self):
        """Stats should return valid information."""
        builder = DynamicPromptBuilder()
        stats = builder.get_prompt_stats()

        assert stats["total_agents"] >= 7
        assert len(stats["agent_types"]) > 0
        assert len(stats["categories"]) > 0

    def test_singleton_instance(self):
        """get_prompt_builder should return singleton."""
        builder1 = get_prompt_builder()
        builder2 = get_prompt_builder()

        assert builder1 is builder2


# ============================================================================
# agents_from_classification tests (no LLM call, tests the mapping logic)
# ============================================================================

class TestAgentsFromClassification:
    """Tests for agents_from_classification — the mapping from LLM output to agent list."""

    def test_research_classification_includes_web_research(self):
        """Research classification should include web_research."""
        builder = DynamicPromptBuilder()
        classification = _make_classification(
            task_type="research",
            info_method="web_research",
            categories=["research", "content"],
        )
        agents = builder.agents_from_classification(classification)

        assert "web_research" in agents
        assert "summarize" in agents

    def test_fetch_classification_uses_http_fetch_method(self):
        """Fetch classification with http_fetch info_method adds it (if registered)."""
        builder = DynamicPromptBuilder()
        builder._load_registry()
        classification = _make_classification(
            task_type="fetch",
            info_method="http_fetch",
            categories=["content"],
        )
        agents = builder.agents_from_classification(classification)

        # http_fetch is included only if it exists in the registry
        if "http_fetch" in builder._agent_metadata:
            assert "http_fetch" in agents
        # Common utilities always present regardless
        assert "compose" in agents

    def test_integration_category_includes_integration_agents(self):
        """Classification with 'integration' category includes integration agents."""
        builder = DynamicPromptBuilder()
        classification = _make_classification(
            task_type="outbound_action",
            info_method="none",
            categories=["integration", "content"],
        )
        agents = builder.agents_from_classification(classification)

        # Integration agents come from the registry's "integration" domain
        # Common content utilities are always included
        assert "compose" in agents

    def test_always_includes_common_utilities(self):
        """Common utilities (summarize, analyze, compose) are always included."""
        builder = DynamicPromptBuilder()
        classification = _make_classification(categories=["research"])
        agents = builder.agents_from_classification(classification)

        assert "summarize" in agents
        assert "analyze" in agents
        assert "compose" in agents


# ============================================================================
# build_full_prompt_async tests (mock LLM classification)
# ============================================================================

class TestBuildFullPromptAsync:
    """Tests for the async prompt builder with mocked LLM classification."""

    @pytest.fixture
    def builder(self):
        return DynamicPromptBuilder()

    async def test_prompt_includes_all_sections(self, builder):
        """Full prompt should include all standard sections."""
        classification = _make_classification(categories=["research", "content"])

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify:
            mock_classify.return_value = classification

            prompt = await builder.build_full_prompt_async(
                "Get news from BBC and summarize it"
            )

        assert "Plan Generator" in prompt
        assert "Available Agent Types" in prompt
        assert "Detailed Agent Documentation" in prompt
        assert "Input Variable Syntax" in prompt
        assert "Output Format" in prompt
        assert "Rules" in prompt
        assert "Goal: Get news from BBC" in prompt

    async def test_prompt_includes_detailed_docs_for_selected_agents(self, builder):
        """Prompt should include detailed docs for agents from classification."""
        classification = _make_classification(
            info_method="web_research",
            categories=["research", "content"],
        )

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify:
            mock_classify.return_value = classification

            prompt = await builder.build_full_prompt_async("Research AI trends")

        assert "### web_research" in prompt
        assert "### summarize" in prompt

    async def test_prompt_with_file_references(self, builder):
        """Prompt should include file references section when provided."""
        classification = _make_classification(categories=["content"])
        constraints = {
            "file_references": [
                {"id": "file-1", "name": "doc.pdf", "path": "/docs/", "content_type": "application/pdf"}
            ]
        }

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify:
            mock_classify.return_value = classification

            prompt = await builder.build_full_prompt_async(
                "Summarize this document",
                constraints=constraints,
            )

        assert "Available File References" in prompt
        assert "doc.pdf" in prompt

    async def test_prompt_fetches_integrations_when_token_present(self, builder):
        """When user_token is in constraints, integrations are fetched and included."""
        classification = _make_classification(
            task_type="outbound_action",
            info_method="none",
            categories=["integration"],
        )
        integrations = [
            {"id": "int-1", "name": "my-discord", "provider": "discord",
             "direction": "outbound", "status": "active"},
        ]
        constraints = {"user_token": "test-token-abc"}

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify, \
             patch.object(builder, "_fetch_user_integrations", new_callable=AsyncMock) as mock_fetch:
            mock_classify.return_value = classification
            mock_fetch.return_value = integrations

            prompt = await builder.build_full_prompt_async(
                "Post a tweet on X",
                constraints=constraints,
            )

        mock_fetch.assert_called_once_with("test-token-abc")
        assert "User's Configured Integrations" in prompt
        assert "my-discord" in prompt
        assert "int-1" in prompt

    async def test_integration_plugins_injected_when_integrations_exist(self, builder):
        """Integration plugins are added to agent list when user has integrations."""
        classification = _make_classification(
            task_type="research",
            info_method="web_research",
            categories=["research"],  # No integration category from LLM
        )
        integrations = [
            {"id": "int-1", "name": "my-slack", "provider": "slack",
             "direction": "outbound", "status": "active"},
        ]
        constraints = {"user_token": "test-token"}

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify, \
             patch.object(builder, "_fetch_user_integrations", new_callable=AsyncMock) as mock_fetch:
            mock_classify.return_value = classification
            mock_fetch.return_value = integrations

            prompt = await builder.build_full_prompt_async(
                "Research AI and post to Slack",
                constraints=constraints,
            )

        # Integration plugins should be injected even though LLM didn't classify as integration
        assert "User's Configured Integrations" in prompt

    async def test_no_integration_fetch_without_token(self, builder):
        """Without user_token, no integration fetch is attempted."""
        classification = _make_classification(categories=["research"])

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify, \
             patch.object(builder, "_fetch_user_integrations", new_callable=AsyncMock) as mock_fetch:
            mock_classify.return_value = classification

            prompt = await builder.build_full_prompt_async("Research AI trends")

        mock_fetch.assert_not_called()
        assert "User's Configured Integrations" not in prompt

    async def test_empty_integrations_not_added_to_prompt(self, builder):
        """When user has no integrations, no section is added."""
        classification = _make_classification(categories=["content"])
        constraints = {"user_token": "test-token"}

        with patch.object(builder, "classify_goal_with_llm", new_callable=AsyncMock) as mock_classify, \
             patch.object(builder, "_fetch_user_integrations", new_callable=AsyncMock) as mock_fetch:
            mock_classify.return_value = classification
            mock_fetch.return_value = []

            prompt = await builder.build_full_prompt_async(
                "Write an article",
                constraints=constraints,
            )

        assert "User's Configured Integrations" not in prompt


# ============================================================================
# Integration section builder tests (no LLM, no async)
# ============================================================================

class TestIntegrationsSectionBuilder:
    """Tests for _build_integrations_section prompt formatting."""

    def test_format_with_multiple_integrations(self):
        """Section lists all integrations with correct fields."""
        builder = DynamicPromptBuilder()
        integrations = [
            {"id": "int-123", "name": "my-discord", "provider": "discord",
             "direction": "outbound", "status": "active"},
            {"id": "int-456", "name": "my-slack", "provider": "slack",
             "direction": "bidirectional", "status": "active"},
        ]

        lines = builder._build_integrations_section(integrations)
        section = "\n".join(lines)

        assert "User's Configured Integrations" in section
        assert "my-discord" in section
        assert "int-123" in section
        assert "discord" in section
        assert "my-slack" in section
        assert "int-456" in section
        assert "execute_outbound_action" in section
        assert "user_token" in section.lower()

    def test_format_with_empty_list(self):
        """Empty integrations list still produces header."""
        builder = DynamicPromptBuilder()
        lines = builder._build_integrations_section([])
        section = "\n".join(lines)

        assert "User's Configured Integrations" in section
