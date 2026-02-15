"""Unit tests for SummaryGenerationService fallback with key_outputs."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.inbox.summary_service import (
    SummaryGenerationService,
    _extract_result_text,
)


class TestExtractResultText:
    def test_extracts_result_key_from_last_step(self):
        outputs = {
            "analyze": {"status": "ok"},
            "summarize": {"result": "The image shows a dashboard with charts."},
        }
        text = _extract_result_text(outputs)
        assert text == "The image shows a dashboard with charts."

    def test_extracts_output_key(self):
        outputs = {"step1": {"output": "Some output text"}}
        text = _extract_result_text(outputs)
        assert text == "Some output text"

    def test_extracts_text_key(self):
        outputs = {"step1": {"text": "Plain text result"}}
        text = _extract_result_text(outputs)
        assert text == "Plain text result"

    def test_extracts_string_output(self):
        outputs = {"step1": "Direct string result"}
        text = _extract_result_text(outputs)
        assert text == "Direct string result"

    def test_stringifies_dict_without_known_keys(self):
        outputs = {"step1": {"custom_field": "value123"}}
        text = _extract_result_text(outputs)
        assert "custom_field" in text
        assert "value123" in text

    def test_truncates_long_result(self):
        long_text = "x" * 3000
        outputs = {"step1": {"result": long_text}}
        text = _extract_result_text(outputs)
        assert len(text) <= 2003  # 2000 + "..."
        assert text.endswith("...")

    def test_returns_none_for_empty_outputs(self):
        assert _extract_result_text(None) is None
        assert _extract_result_text({}) is None

    def test_falls_back_to_findings(self):
        findings = [
            {"content": "First finding"},
            {"content": "Second finding"},
        ]
        text = _extract_result_text(None, findings)
        assert "First finding" in text
        assert "Second finding" in text

    def test_findings_with_text_key(self):
        findings = [{"text": "A finding via text key"}]
        text = _extract_result_text(None, findings)
        assert "A finding via text key" in text

    def test_prefers_outputs_over_findings(self):
        outputs = {"step1": {"result": "From outputs"}}
        findings = [{"content": "From findings"}]
        text = _extract_result_text(outputs, findings)
        assert text == "From outputs"

    def test_returns_none_for_empty_findings(self):
        assert _extract_result_text(None, []) is None

    def test_skips_empty_string_output(self):
        outputs = {"step1": "   "}
        # Empty/whitespace string should not be returned — fall through
        text = _extract_result_text(outputs)
        assert text is None


class TestFallbackSummaryWithOutputs:
    def setup_method(self):
        self.service = SummaryGenerationService()

    def test_completed_with_key_outputs_shows_result(self):
        result = self.service.generate_fallback_summary(
            goal="Analyze screenshot",
            status="completed",
            steps_completed=3,
            total_steps=3,
            key_outputs={"final_step": {"result": "The image shows a login page."}},
        )
        assert result == "The image shows a login page."

    def test_completed_without_outputs_uses_template(self):
        result = self.service.generate_fallback_summary(
            goal="Analyze screenshot",
            status="completed",
            steps_completed=3,
            total_steps=3,
        )
        assert result == "Completed: Analyze screenshot. 3/3 steps executed."

    def test_failed_ignores_key_outputs(self):
        result = self.service.generate_fallback_summary(
            goal="Deploy app",
            status="failed",
            steps_completed=1,
            total_steps=3,
            key_outputs={"step1": {"result": "partial"}},
            error="Timeout",
        )
        assert "Failed: Deploy app" in result
        assert "Timeout" in result

    def test_checkpoint_ignores_key_outputs(self):
        result = self.service.generate_fallback_summary(
            goal="Process data",
            status="checkpoint",
            steps_completed=2,
            total_steps=4,
            key_outputs={"step1": {"result": "partial"}},
        )
        assert "Awaiting approval" in result


class TestSummarySafeFallbackPassesOutputs:
    @pytest.mark.asyncio
    async def test_fallback_receives_key_outputs(self):
        """When LLM fails, fallback gets key_outputs and uses them."""
        service = SummaryGenerationService(llm_client=None)  # No LLM → RuntimeError

        result = await service.generate_summary_safe(
            goal="Analyze image",
            status="completed",
            steps_completed=2,
            total_steps=2,
            key_outputs={"describe": {"result": "A photo of a sunset over the ocean."}},
            findings=[],
        )
        assert result == "A photo of a sunset over the ocean."

    @pytest.mark.asyncio
    async def test_fallback_without_outputs_uses_template(self):
        """When LLM fails and no outputs, fallback uses template."""
        service = SummaryGenerationService(llm_client=None)

        result = await service.generate_summary_safe(
            goal="Process data",
            status="completed",
            steps_completed=3,
            total_steps=3,
            key_outputs={},
            findings=[],
        )
        assert result == "Completed: Process data. 3/3 steps executed."

    @pytest.mark.asyncio
    async def test_llm_success_skips_fallback(self):
        """When LLM succeeds, its response is returned directly."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "I analyzed the image and found a login page."
        mock_llm.create_completion = AsyncMock(return_value=mock_response)

        service = SummaryGenerationService(llm_client=mock_llm)

        result = await service.generate_summary_safe(
            goal="Analyze image",
            status="completed",
            steps_completed=2,
            total_steps=2,
            key_outputs={"step": {"result": "raw output"}},
            findings=[],
        )
        assert result == "I analyzed the image and found a login page."
