"""
MemoryInjector - Formats memories for system prompt injection.

This is pure formatting logic - no I/O, no async.
Formats memories as XML matching the existing Tentackl prompt style.
"""

from typing import List
from html import escape

from src.domain.memory.models import MemoryResult


class MemoryInjector:
    """
    Formats memories for injection into agent system prompts.

    Uses XML format to match the existing orchestrator prompt style
    (plan_document, current_step, accumulated_findings).
    """

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a given text.

        Uses rough chars-to-tokens approximation: 1 token ≈ 4 characters.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def format_for_prompt(
        self,
        memories: List[MemoryResult],
        max_tokens: int = 2000,
        format_style: str = "xml"
    ) -> str:
        """
        Format memories for system prompt injection.

        Formats as XML:
        <memories>
          <memory key="..." topic="..." relevance="0.95">
            <title>...</title>
            <body>...</body>
          </memory>
          ...
        </memories>

        Args:
            memories: List of memory results to format
            max_tokens: Maximum token budget for output
            format_style: Format style (currently only 'xml' supported)

        Returns:
            Formatted string for prompt injection, or empty string if no memories
        """
        if not memories:
            return ""

        # Sort by relevance score descending (highest first)
        sorted_memories = sorted(
            memories,
            key=lambda m: m.evidence.relevance_score if m.evidence else 0.0,
            reverse=True
        )

        # Build output, dropping lowest-relevance memories until under budget
        while sorted_memories:
            output = self._format_memories_xml(sorted_memories)
            if self.estimate_tokens(output) <= max_tokens:
                return output
            # Drop lowest-relevance memory (last in sorted list)
            sorted_memories = sorted_memories[:-1]

        # Edge case: even empty wrapper exceeds budget
        return ""

    def _format_memories_xml(self, memories: List[MemoryResult]) -> str:
        """
        Format a list of memories as XML.

        Args:
            memories: List of memories to format (already sorted by relevance)

        Returns:
            XML-formatted string
        """
        if not memories:
            return ""

        lines = ["<memories>"]
        for memory in memories:
            relevance = (
                f"{memory.evidence.relevance_score:.2f}"
                if memory.evidence
                else "0.00"
            )
            topic_attr = f' topic="{escape(memory.topic)}"' if memory.topic else ""

            lines.append(
                f'  <memory key="{escape(memory.key)}"{topic_attr} relevance="{relevance}">'
            )
            lines.append(f"    <title>{escape(memory.title)}</title>")
            lines.append(f"    <body>{escape(memory.body)}</body>")
            lines.append("  </memory>")
        lines.append("</memories>")

        return "\n".join(lines)
