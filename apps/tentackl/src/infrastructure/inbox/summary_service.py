# REVIEW: Summary generation hard-codes model/temperature and uses raw status
# REVIEW: strings rather than TaskStatus enum. Consider moving model settings
# REVIEW: into config and standardizing status handling to avoid drift.
"""
Summary Generation Service for Agent Inbox.

Generates human-readable outcome summaries when tasks complete, fail,
or hit checkpoints. Uses LLM for rich summaries with a template-based
fallback for reliability.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse
from src.llm.model_selector import TASK_ROUTING_CONFIGS, TaskType

logger = structlog.get_logger()

# Use the primary model from the QUICK_RESPONSE routing config
DEFAULT_SUMMARY_MODEL = TASK_ROUTING_CONFIGS[TaskType.QUICK_RESPONSE].models[0]
DEFAULT_SUMMARY_MAX_TOKENS = 300
DEFAULT_SUMMARY_TEMPERATURE = 0.3

SUMMARY_SYSTEM_PROMPT = """You are summarizing what an AI agent accomplished for the user.

Write a 1-3 sentence message that:
- Leads with the outcome (what was accomplished or what went wrong)
- Includes key data points the user would care about
- Ends with a suggested next action if applicable
- Uses first person ("I found...", "I completed...")"""


def _build_summary_user_prompt(
    goal: str,
    status: str,
    steps_completed: int,
    total_steps: int,
    key_outputs: Dict[str, Any],
    findings: List[Any],
    error: Optional[str] = None,
) -> str:
    """Build the user prompt for LLM summary generation."""
    parts = [
        f"Task goal: {goal}",
        f"Status: {status}",
        f"Steps completed: {steps_completed}/{total_steps}",
    ]

    if key_outputs:
        outputs_str = "\n".join(f"  - {k}: {v}" for k, v in key_outputs.items())
        parts.append(f"Key outputs:\n{outputs_str}")

    if findings:
        findings_str = "\n".join(f"  - {f}" for f in findings[:10])
        parts.append(f"Findings:\n{findings_str}")

    if error:
        parts.append(f"Error: {error}")

    return "\n".join(parts)


MAX_FALLBACK_RESULT_LENGTH = 2000


def _extract_result_text(
    key_outputs: Optional[Dict[str, Any]] = None,
    findings: Optional[List[Any]] = None,
) -> Optional[str]:
    """Extract a human-readable result from step outputs or findings.

    Looks for a ``result`` key in the last step's output dict, then falls
    back to stringifying the last output value, then to findings.
    Returns ``None`` when no meaningful text can be extracted.
    """
    if key_outputs:
        # Use the last step's output (most likely the final result)
        last_output = list(key_outputs.values())[-1]
        if isinstance(last_output, dict):
            # Prefer explicit "result" key
            for key in ("result", "output", "text", "description", "content"):
                if key in last_output and last_output[key]:
                    text = str(last_output[key])
                    if len(text) > MAX_FALLBACK_RESULT_LENGTH:
                        text = text[:MAX_FALLBACK_RESULT_LENGTH] + "..."
                    return text
            # Fallback: stringify the whole dict
            text = str(last_output)
            if len(text) > MAX_FALLBACK_RESULT_LENGTH:
                text = text[:MAX_FALLBACK_RESULT_LENGTH] + "..."
            return text
        elif isinstance(last_output, str) and last_output.strip():
            text = last_output.strip()
            if len(text) > MAX_FALLBACK_RESULT_LENGTH:
                text = text[:MAX_FALLBACK_RESULT_LENGTH] + "..."
            return text

    if findings:
        # Join the last few findings as result text
        recent = findings[-3:]
        parts = []
        for f in recent:
            if isinstance(f, dict):
                parts.append(str(f.get("content", f.get("text", str(f)))))
            else:
                parts.append(str(f))
        text = "\n".join(parts)
        if text.strip():
            if len(text) > MAX_FALLBACK_RESULT_LENGTH:
                text = text[:MAX_FALLBACK_RESULT_LENGTH] + "..."
            return text

    return None


class SummaryGenerationService:
    """Generates human-readable summaries for task outcomes.

    Uses an LLM client for rich summaries with a synchronous template-based
    fallback that never fails.
    """

    def __init__(self, llm_client: Optional[LLMInterface] = None) -> None:
        self._llm_client = llm_client

    async def generate_summary(
        self,
        goal: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        key_outputs: Dict[str, Any],
        findings: List[Any],
        error: Optional[str] = None,
    ) -> str:
        """Generate an LLM-powered summary of the task outcome.

        Args:
            goal: The task's original goal.
            status: Current status (completed, failed, checkpoint).
            steps_completed: Number of steps finished.
            total_steps: Total number of steps in the plan.
            key_outputs: Structured outputs from completed steps.
            findings: Accumulated findings from the task.
            error: Error message if the task failed.

        Returns:
            A concise 1-3 sentence summary string.

        Raises:
            RuntimeError: If no LLM client is configured.
            Exception: Any error from the LLM call.
        """
        if self._llm_client is None:
            raise RuntimeError("No LLM client configured for summary generation")

        user_prompt = _build_summary_user_prompt(
            goal=goal,
            status=status,
            steps_completed=steps_completed,
            total_steps=total_steps,
            key_outputs=key_outputs,
            findings=findings,
            error=error,
        )

        messages = [
            LLMMessage(role="system", content=SUMMARY_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        response: LLMResponse = await self._llm_client.create_completion(
            messages=messages,
            model=DEFAULT_SUMMARY_MODEL,
            temperature=DEFAULT_SUMMARY_TEMPERATURE,
            max_tokens=DEFAULT_SUMMARY_MAX_TOKENS,
        )

        return response.content.strip()

    def generate_fallback_summary(
        self,
        goal: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        key_outputs: Optional[Dict[str, Any]] = None,
        findings: Optional[List[Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        """Generate a template-based fallback summary.

        Synchronous and guaranteed to never raise. Used when LLM is
        unavailable or as immediate placeholder text.

        Args:
            goal: The task's original goal.
            status: Current status (completed, failed, checkpoint).
            steps_completed: Number of steps finished.
            total_steps: Total number of steps in the plan.
            key_outputs: Structured outputs from completed steps.
            findings: Accumulated findings from the task.
            error: Error message if the task failed.

        Returns:
            A template-based summary string.
        """
        if status == "completed":
            result_text = _extract_result_text(key_outputs, findings)
            if result_text:
                return result_text
            return f"Completed: {goal}. {steps_completed}/{total_steps} steps executed."
        elif status == "failed":
            error_part = f" Error: {error}." if error else ""
            return (
                f"Failed: {goal}.{error_part} "
                f"{steps_completed}/{total_steps} steps completed before failure."
            )
        elif status == "checkpoint":
            return (
                f"Awaiting approval: {goal}. "
                f"{steps_completed}/{total_steps} steps completed so far."
            )
        else:
            return f"{goal}. Status: {status}. {steps_completed}/{total_steps} steps."

    async def generate_summary_safe(
        self,
        goal: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        key_outputs: Dict[str, Any],
        findings: List[Any],
        error: Optional[str] = None,
    ) -> str:
        """Generate a summary, falling back to template on any error.

        Wraps generate_summary in try/except and returns the fallback
        on any error. Never raises.

        Args:
            goal: The task's original goal.
            status: Current status (completed, failed, checkpoint).
            steps_completed: Number of steps finished.
            total_steps: Total number of steps in the plan.
            key_outputs: Structured outputs from completed steps.
            findings: Accumulated findings from the task.
            error: Error message if the task failed.

        Returns:
            LLM-generated summary or template-based fallback.
        """
        try:
            return await self.generate_summary(
                goal=goal,
                status=status,
                steps_completed=steps_completed,
                total_steps=total_steps,
                key_outputs=key_outputs,
                findings=findings,
                error=error,
            )
        except Exception as exc:
            logger.warning(
                "LLM summary generation failed, using fallback",
                error=str(exc),
                goal=goal,
                status=status,
            )
            return self.generate_fallback_summary(
                goal=goal,
                status=status,
                steps_completed=steps_completed,
                total_steps=total_steps,
                key_outputs=key_outputs,
                findings=findings,
                error=error,
            )
