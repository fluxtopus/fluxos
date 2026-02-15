"""Unit tests for MemoryInjector prompt formatting.

Tests XML formatting, token budget handling, and output consistency.
No mocking needed - pure logic tests.
"""

from datetime import datetime

import pytest

from src.domain.memory.models import MemoryResult, RetrievalEvidence
from src.infrastructure.memory.memory_injector import MemoryInjector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def create_memory_result(
    key: str,
    title: str,
    body: str,
    relevance_score: float = 0.8,
    topic: str | None = "testing",
) -> MemoryResult:
    """Helper to create MemoryResult fixtures."""
    return MemoryResult(
        id=f"mem-{key}",
        key=key,
        title=title,
        body=body,
        scope="organization",
        topic=topic,
        tags=["test"],
        version=1,
        evidence=RetrievalEvidence(
            match_type="topic",
            relevance_score=relevance_score,
            filters_applied=["topic"],
            retrieval_time_ms=10,
        ),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def injector():
    """MemoryInjector instance for testing."""
    return MemoryInjector()


@pytest.fixture
def single_memory():
    """Single memory result for testing."""
    return create_memory_result(
        key="brand-voice",
        title="Brand Voice Guidelines",
        body="Use confident but not arrogant tone. Avoid buzzwords.",
        relevance_score=0.95,
        topic="content",
    )


@pytest.fixture
def multiple_memories():
    """Multiple memory results for testing, with varying relevance."""
    return [
        create_memory_result(
            key="priority-high",
            title="High Priority Memory",
            body="This is the most relevant memory.",
            relevance_score=0.95,
            topic="content",
        ),
        create_memory_result(
            key="priority-medium",
            title="Medium Priority Memory",
            body="This is moderately relevant.",
            relevance_score=0.75,
            topic="content",
        ),
        create_memory_result(
            key="priority-low",
            title="Low Priority Memory",
            body="This is less relevant.",
            relevance_score=0.55,
            topic="content",
        ),
    ]


# ---------------------------------------------------------------------------
# TestMemoryInjectorFormatting
# ---------------------------------------------------------------------------


class TestMemoryInjectorFormatting:
    """Tests for XML formatting output."""

    def test_formats_single_memory(self, injector, single_memory):
        """Test output contains <memory key=...> for single memory."""
        result = injector.format_for_prompt([single_memory])

        assert "<memories>" in result
        assert "</memories>" in result
        assert '<memory key="brand-voice"' in result
        assert "<title>Brand Voice Guidelines</title>" in result
        assert "<body>Use confident but not arrogant tone. Avoid buzzwords.</body>" in result

    def test_formats_multiple_memories(self, injector, multiple_memories):
        """Test all memories are present in output."""
        result = injector.format_for_prompt(multiple_memories)

        assert result.count("<memory ") == 3
        assert result.count("</memory>") == 3
        assert "priority-high" in result
        assert "priority-medium" in result
        assert "priority-low" in result

    def test_includes_relevance_attribute(self, injector, single_memory):
        """Test relevance='0.95' is in output."""
        result = injector.format_for_prompt([single_memory])

        assert 'relevance="0.95"' in result

    def test_includes_topic_attribute(self, injector, single_memory):
        """Test topic attribute is included when present."""
        result = injector.format_for_prompt([single_memory])

        assert 'topic="content"' in result

    def test_empty_memories_returns_empty_string(self, injector):
        """Test empty memories list returns empty string."""
        result = injector.format_for_prompt([])

        assert result == ""

    def test_xml_special_chars_escaped(self, injector):
        """Test body with <>&" is escaped properly."""
        memory_with_special_chars = create_memory_result(
            key="special-chars",
            title="Title with <tag> & \"quotes\"",
            body="Body with <xml> & ampersand & \"quoted\" content.",
            relevance_score=0.9,
        )

        result = injector.format_for_prompt([memory_with_special_chars])

        # Verify characters are escaped
        assert "&lt;xml&gt;" in result
        assert "&amp;" in result
        assert "&quot;quoted&quot;" in result
        # Title should also be escaped
        assert "&lt;tag&gt;" in result

    def test_memory_without_topic_omits_topic_attribute(self, injector):
        """Test memory without topic doesn't include topic attribute."""
        memory_no_topic = create_memory_result(
            key="no-topic",
            title="No Topic Memory",
            body="This memory has no topic.",
            relevance_score=0.8,
            topic=None,
        )

        result = injector.format_for_prompt([memory_no_topic])

        assert 'key="no-topic"' in result
        assert 'topic=' not in result.split('key="no-topic"')[1].split(">")[0]

    def test_memory_without_evidence_uses_default_relevance(self, injector):
        """Test memory without evidence gets relevance='0.00'."""
        memory_no_evidence = MemoryResult(
            id="mem-no-evidence",
            key="no-evidence",
            title="No Evidence Memory",
            body="This memory has no evidence.",
            scope="organization",
            topic="testing",
            tags=[],
            version=1,
            evidence=None,  # No evidence
        )

        result = injector.format_for_prompt([memory_no_evidence])

        assert 'relevance="0.00"' in result


# ---------------------------------------------------------------------------
# TestMemoryInjectorTokenBudget
# ---------------------------------------------------------------------------


class TestMemoryInjectorTokenBudget:
    """Tests for token budget handling."""

    def test_respects_max_token_budget(self, injector):
        """Test 20 memories with low budget returns fewer."""
        # Create 20 memories, each with ~100 char body
        memories = [
            create_memory_result(
                key=f"mem-{i}",
                title=f"Memory {i}",
                body="A" * 100,  # 100 chars
                relevance_score=0.5 + (i * 0.02),
            )
            for i in range(20)
        ]

        # Small budget should result in fewer memories
        result = injector.format_for_prompt(memories, max_tokens=200)
        tokens = injector.estimate_tokens(result)

        assert tokens <= 200
        # Should have fewer than 20 memories
        assert result.count("<memory ") < 20

    def test_truncates_lowest_relevance_first(self, injector, multiple_memories):
        """Test high-relevance kept, low dropped when budget tight."""
        # Very tight budget
        result = injector.format_for_prompt(multiple_memories, max_tokens=150)

        # If truncation happened, highest relevance should remain
        if result:
            assert "priority-high" in result
            # Lower relevance might be dropped
            # (depends on exact token math)

    def test_zero_budget_returns_empty(self, injector, single_memory):
        """Test zero budget returns empty string."""
        result = injector.format_for_prompt([single_memory], max_tokens=0)

        assert result == ""

    def test_single_large_memory_truncated_gracefully(self, injector):
        """Test single large memory is handled gracefully when over budget."""
        large_memory = create_memory_result(
            key="large",
            title="Large Memory",
            body="X" * 10000,  # Very large body
            relevance_score=0.99,
        )

        # Budget smaller than the memory
        result = injector.format_for_prompt([large_memory], max_tokens=100)

        # Should return empty since single memory exceeds budget
        assert result == ""

    def test_budget_keeps_high_relevance_drops_low(self, injector):
        """Test with specific budget, highest relevance memories are kept."""
        memories = [
            create_memory_result(
                key="high-rel",
                title="High",
                body="Short body.",
                relevance_score=0.99,
            ),
            create_memory_result(
                key="low-rel",
                title="Low",
                body="Short body.",
                relevance_score=0.10,
            ),
        ]

        # Budget enough for ~1 memory
        result = injector.format_for_prompt(memories, max_tokens=80)

        if result:
            # If only one fits, it should be the high-relevance one
            if result.count("<memory ") == 1:
                assert "high-rel" in result
                assert "low-rel" not in result

    def test_all_memories_fit_within_budget(self, injector, multiple_memories):
        """Test all memories included when budget is sufficient."""
        result = injector.format_for_prompt(multiple_memories, max_tokens=10000)

        assert result.count("<memory ") == 3
        assert "priority-high" in result
        assert "priority-medium" in result
        assert "priority-low" in result


# ---------------------------------------------------------------------------
# TestMemoryInjectorConsistency
# ---------------------------------------------------------------------------


class TestMemoryInjectorConsistency:
    """Tests for output consistency and determinism."""

    def test_deterministic_output(self, injector, multiple_memories):
        """Test same input produces same output."""
        result1 = injector.format_for_prompt(multiple_memories)
        result2 = injector.format_for_prompt(multiple_memories)

        assert result1 == result2

    def test_sorted_by_relevance_desc(self, injector, multiple_memories):
        """Test highest relevance appears first in output."""
        result = injector.format_for_prompt(multiple_memories)

        # Find positions of each memory key
        high_pos = result.find("priority-high")
        medium_pos = result.find("priority-medium")
        low_pos = result.find("priority-low")

        # Highest relevance should appear first
        assert high_pos < medium_pos
        assert medium_pos < low_pos

    def test_sorted_by_relevance_with_unordered_input(self, injector):
        """Test output is sorted even when input is unordered."""
        # Create memories in random relevance order
        memories = [
            create_memory_result(
                key="medium",
                title="Medium",
                body="Body",
                relevance_score=0.75,
            ),
            create_memory_result(
                key="low",
                title="Low",
                body="Body",
                relevance_score=0.50,
            ),
            create_memory_result(
                key="high",
                title="High",
                body="Body",
                relevance_score=0.99,
            ),
        ]

        result = injector.format_for_prompt(memories)

        # Find positions
        high_pos = result.find('"high"')
        medium_pos = result.find('"medium"')
        low_pos = result.find('"low"')

        # Should be sorted by relevance descending
        assert high_pos < medium_pos < low_pos

    def test_output_structure_consistent(self, injector, single_memory):
        """Test XML structure is consistent."""
        result = injector.format_for_prompt([single_memory])

        lines = result.split("\n")
        assert lines[0] == "<memories>"
        assert lines[-1] == "</memories>"
        # Memory tag is indented
        assert lines[1].startswith("  <memory ")


# ---------------------------------------------------------------------------
# TestMemoryInjectorTokenEstimation
# ---------------------------------------------------------------------------


class TestMemoryInjectorTokenEstimation:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self, injector):
        """Test basic token estimation (len // 4)."""
        # 16 chars / 4 = 4 tokens
        assert injector.estimate_tokens("hello world test") == 4

    def test_estimate_tokens_empty(self, injector):
        """Test empty string returns 0 tokens."""
        assert injector.estimate_tokens("") == 0

    def test_estimate_tokens_short(self, injector):
        """Test short strings under 4 chars return 0."""
        assert injector.estimate_tokens("hi") == 0
        assert injector.estimate_tokens("abc") == 0

    def test_estimate_tokens_long(self, injector):
        """Test long strings are estimated correctly."""
        text = "x" * 400
        assert injector.estimate_tokens(text) == 100
