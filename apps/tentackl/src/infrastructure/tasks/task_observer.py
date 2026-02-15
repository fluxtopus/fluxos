"""
# REVIEW:
# - Prompt is loaded from a file at runtime, but fallback prompt is minimal; output quality may vary.
# - _get_plan_store opens Redis without explicit close; may leak connections.

Delegation Observer Agent

A passive monitoring agent that watches plan execution and reports anomalies.
The observer does NOT act - it only observes and proposes.

The observer:
1. Monitors plan progress
2. Detects anomalies
3. Proposes changes
4. Reports to orchestrator

IMPORTANT: The observer NEVER modifies the plan directly.
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import structlog

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    ObserverProposal,
    ProposalType,
    ReplanContext,
)
from src.interfaces.llm import LLMMessage
from src.llm.openrouter_client import ModelRouting
from src.domain.tasks.ports import TaskPlanStorePort
from src.llm.openrouter_client import OpenRouterClient
from src.eval.format_validators import validate_template_syntax_quick
from src.eval.models import AGENT_OUTPUT_FIELDS


logger = structlog.get_logger(__name__)


def _load_observer_prompt() -> str:
    """Load the observer system prompt from external file."""
    prompt_path = Path(__file__).parent / "prompts" / "task_observer_prompt.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip markdown title
        if content.startswith("# Delegation Observer"):
            lines = content.split("\n", 2)
            content = lines[2] if len(lines) > 2 else content
        return content.strip()
    except FileNotFoundError:
        logger.warning("Observer prompt not found, using fallback", path=str(prompt_path))
        return """<system>
You are the Delegation Observer. Monitor and report only - DO NOT take action.
You can only OBSERVE and PROPOSE - the orchestrator decides.
</system>"""


OBSERVER_PROMPT_TEMPLATE = _load_observer_prompt()


class ObservationReport:
    """Structured observation report from the observer agent."""

    def __init__(
        self,
        plan_id: str,
        progress_pct: float,
        steps_completed: int,
        steps_total: int,
        current_step: Optional[str],
        health_status: str,
        anomalies: List[Dict[str, Any]],
        proposals: List[Dict[str, Any]],
        recommendation: str,
        recommendation_reason: str,
        timestamp: datetime = None,
    ):
        self.plan_id = plan_id
        self.timestamp = timestamp or datetime.utcnow()
        self.progress_pct = progress_pct
        self.steps_completed = steps_completed
        self.steps_total = steps_total
        self.current_step = current_step
        self.health_status = health_status
        self.anomalies = anomalies
        self.proposals = proposals
        self.recommendation = recommendation
        self.recommendation_reason = recommendation_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "timestamp": self.timestamp.isoformat(),
            "progress": {
                "percentage": self.progress_pct,
                "steps_completed": self.steps_completed,
                "steps_total": self.steps_total,
                "current_step": self.current_step,
            },
            "health_status": self.health_status,
            "anomalies": self.anomalies,
            "proposals": self.proposals,
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
        }

    @property
    def has_anomalies(self) -> bool:
        return len(self.anomalies) > 0

    @property
    def has_critical_anomalies(self) -> bool:
        return any(a.get("severity") == "critical" for a in self.anomalies)

    @property
    def should_escalate(self) -> bool:
        return self.recommendation == "escalate"


class TaskObserverAgent(LLMAgent):
    """
    Passive observer that monitors plan execution.

    The observer:
    - Watches execution progress
    - Detects anomalies and risks
    - Proposes plan modifications
    - Reports to the orchestrator

    CRITICAL: The observer NEVER acts directly.
    It can only observe and propose.
    """

    def __init__(
        self,
        name: str = "delegation-observer",
        model: str = "x-ai/grok-4.1-fast",
        llm_client: Optional[OpenRouterClient] = None,
        plan_store: Optional[TaskPlanStorePort] = None,
        enable_conversation_tracking: bool = True,  # Track LLM calls for usage monitoring
    ):
        # Create config for the LLM agent
        config = AgentConfig(
            name=name,
            agent_type="task_observer",
            metadata={
                "model": model,
                "temperature": 0.1,  # Very low for consistent analysis
                "system_prompt": "",  # Set dynamically
            }
        )

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking,
        )

        self.model = model
        self._plan_store = plan_store

    async def _get_plan_store(self) -> TaskPlanStorePort:
        """Get or create plan store."""
        if not self._plan_store:
            raise RuntimeError("TaskObserverAgent requires a TaskPlanStorePort")
        await self._plan_store.connect()
        return self._plan_store

    def _build_prompt(
        self,
        plan: Task,
        execution_state: Dict[str, Any],
        recent_events: List[Dict[str, Any]],
    ) -> str:
        """Build the observer prompt with execution context."""
        prompt = OBSERVER_PROMPT_TEMPLATE

        # Replace placeholders
        prompt = prompt.replace("{{plan_document}}", plan.to_xml())
        prompt = prompt.replace("{{execution_state}}", json.dumps(execution_state, indent=2))
        prompt = prompt.replace("{{recent_events}}", json.dumps(recent_events, indent=2))
        prompt = prompt.replace("{{max_tokens}}", "1500")

        return prompt

    async def observe(
        self,
        plan_id: str,
        execution_state: Optional[Dict[str, Any]] = None,
        recent_events: Optional[List[Dict[str, Any]]] = None,
    ) -> ObservationReport:
        """
        Observe the current state of a plan and generate a report.

        Args:
            plan_id: The plan to observe
            execution_state: Optional execution state snapshot
            recent_events: Optional list of recent execution events

        Returns:
            ObservationReport with analysis and recommendations
        """
        logger.info("Observing plan execution", plan_id=plan_id, agent_id=self.agent_id)

        store = await self._get_plan_store()
        plan = await store.get_task(plan_id)

        if not plan:
            logger.error("Plan not found for observation", plan_id=plan_id)
            return self._create_error_report(plan_id, "Plan not found")

        # Build execution state if not provided
        if execution_state is None:
            execution_state = self._build_execution_state(plan)

        # Use empty events if not provided
        if recent_events is None:
            recent_events = []

        # Build prompt and analyze
        self.system_prompt = self._build_prompt(plan, execution_state, recent_events)

        task = {
            "prompt": f"""Analyze the current execution state of plan {plan_id}.

Plan goal: {plan.goal}
Current status: {plan.status.value}
Progress: {plan.get_progress_percentage():.1f}%

Provide your observation report in the specified XML format."""
        }

        result = await self.process_task(task)

        # Parse the response
        if result.get("status") == "error":
            return self._create_error_report(plan_id, result.get("error", "Analysis failed"))

        llm_output = result.get("result", "")
        if isinstance(llm_output, dict):
            llm_output = llm_output.get("result", str(llm_output))

        report = self._parse_observation_report(plan_id, plan, str(llm_output))

        logger.info(
            "Observation complete",
            plan_id=plan_id,
            progress=report.progress_pct,
            health=report.health_status,
            anomalies=len(report.anomalies),
            recommendation=report.recommendation,
        )

        return report

    def _is_content_filter_error(self, error_message: str) -> bool:
        """Detect if the error is from a content filter/moderation system."""
        if not error_message:
            return False

        content_filter_indicators = [
            "Derivative Works Filter",
            "Content Moderated",
            "Request Moderated",
            "content_policy",
            "content policy",
            "copyright",
            "trademark",
            "NSFW",
            "safety filter",
            "moderation",
            "blocked content",
            "violates",
            "not allowed",
        ]
        error_lower = error_message.lower()
        return any(indicator.lower() in error_lower for indicator in content_filter_indicators)

    def _is_modifiable_step(self, step: TaskStep) -> bool:
        """Check if step inputs can be meaningfully modified."""
        modifiable_types = ["generate_image", "compose", "llm", "api_caller"]
        return step.agent_type in modifiable_types

    def _has_template_syntax_errors(self, step: TaskStep) -> bool:
        """
        Check if step inputs contain invalid template syntax.

        Detects patterns like {{step_X.output}} that should be {{step_X.outputs.field}}.
        """
        if not step.inputs:
            return False

        inputs_str = json.dumps(step.inputs)
        is_valid, errors = validate_template_syntax_quick(inputs_str)
        return not is_valid

    def _get_template_syntax_errors(self, step: TaskStep) -> List[str]:
        """Get list of template syntax errors in step inputs."""
        if not step.inputs:
            return []

        inputs_str = json.dumps(step.inputs)
        is_valid, errors = validate_template_syntax_quick(inputs_str)
        return errors

    def _fix_template_syntax(self, plan: Task, step: TaskStep) -> Dict[str, Any]:
        """
        Fix invalid template syntax in step inputs.

        Converts patterns like:
        - {{step_X.output}} → {{step_X.outputs.field}}
        - {{step_X.outputs}} → {{step_X.outputs.field}}

        Uses AGENT_OUTPUT_FIELDS to determine correct field names based on
        the referenced step's agent_type.
        """
        if not step.inputs:
            return {}

        # Build a map of step_id -> agent_type for field name lookup
        step_agents: Dict[str, str] = {}
        step_outputs_map: Dict[str, Dict[str, Any]] = {}
        for s in plan.steps:
            step_agents[s.id] = s.agent_type
            if s.outputs:
                step_outputs_map[s.id] = s.outputs

        def get_default_field(step_id: str) -> str:
            """Get the default output field for a step based on its agent type."""
            agent_type = step_agents.get(step_id, "")

            # Check if we have actual outputs to inspect
            if step_id in step_outputs_map:
                outputs = step_outputs_map[step_id]
                if isinstance(outputs, dict) and outputs:
                    # Return the first field name from actual outputs
                    return list(outputs.keys())[0]

            # Fall back to AGENT_OUTPUT_FIELDS
            if agent_type in AGENT_OUTPUT_FIELDS:
                fields = AGENT_OUTPUT_FIELDS[agent_type]
                return fields[0] if fields else "result"

            # Generic fallbacks based on common patterns
            fallbacks = {
                "web_research": "findings",
                "research": "findings",
                "summarize": "summary",
                "compose": "content",
                "analyze": "analysis",
                "aggregate": "aggregated_content",
                "generate_image": "image_url",
                "file_storage": "file_url",
            }
            return fallbacks.get(agent_type, "result")

        def fix_template(value: Any) -> Any:
            """Recursively fix template patterns in a value."""
            if isinstance(value, str):
                # Pattern 1: {{step_X.output}} - missing 's' and field
                # Captures: step_id
                pattern1 = r'\{\{(\w+)\.output\}\}'

                def replace1(match):
                    step_id = match.group(1)
                    field = get_default_field(step_id)
                    return f"{{{{{step_id}.outputs.{field}}}}}"

                value = re.sub(pattern1, replace1, value)

                # Pattern 2: {{step_X.outputs}} - missing field name
                # Captures: step_id
                pattern2 = r'\{\{(\w+)\.outputs\}\}'

                def replace2(match):
                    step_id = match.group(1)
                    field = get_default_field(step_id)
                    return f"{{{{{step_id}.outputs.{field}}}}}"

                value = re.sub(pattern2, replace2, value)

                # Pattern 3: {{step_X.result}} - wrong accessor
                pattern3 = r'\{\{(\w+)\.result\}\}'

                def replace3(match):
                    step_id = match.group(1)
                    field = get_default_field(step_id)
                    return f"{{{{{step_id}.outputs.{field}}}}}"

                value = re.sub(pattern3, replace3, value)

                # Pattern 4: {{step_X.data}} - wrong accessor
                pattern4 = r'\{\{(\w+)\.data\}\}'

                def replace4(match):
                    step_id = match.group(1)
                    field = get_default_field(step_id)
                    return f"{{{{{step_id}.outputs.{field}}}}}"

                value = re.sub(pattern4, replace4, value)

                return value

            elif isinstance(value, list):
                return [fix_template(item) for item in value]

            elif isinstance(value, dict):
                return {k: fix_template(v) for k, v in value.items()}

            return value

        # Fix all inputs
        fixed_inputs = fix_template(step.inputs)
        return fixed_inputs

    def _is_template_related_error(self, error_message: str) -> bool:
        """
        Check if error message indicates a template-related failure.

        These errors often occur when invalid templates resolve to empty values.
        """
        if not error_message:
            return False

        template_error_indicators = [
            "no sources provided",
            "no data provided",
            "missing required",
            "empty input",
            "null input",
            "undefined",
            "cannot read property",
            "expected string",
            "expected array",
            "expected object",
            "invalid input",
            "input validation",
        ]
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in template_error_indicators)

    async def _generate_template_fix_proposal(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> ObserverProposal:
        """
        Generate a MODIFY proposal that fixes template syntax errors.

        This corrects patterns like {{step_X.output}} to {{step_X.outputs.field}}.
        """
        logger.info(
            "Generating template fix proposal",
            plan_id=plan.id,
            step_id=failed_step.id,
            step_name=failed_step.name,
        )

        # Get the syntax errors for logging
        errors = self._get_template_syntax_errors(failed_step)

        # Fix the templates
        fixed_inputs = self._fix_template_syntax(plan, failed_step)

        # Log the fix
        logger.info(
            "Template syntax fix generated",
            step_id=failed_step.id,
            original_inputs=failed_step.inputs,
            fixed_inputs=fixed_inputs,
            errors_fixed=errors,
        )

        return ObserverProposal(
            proposal_type=ProposalType.MODIFY,
            step_id=failed_step.id,
            reason=f"Template syntax error detected: {'; '.join(errors)}. Fixed to use correct {{{{step_X.outputs.field}}}} syntax.",
            confidence=0.95,  # High confidence - this is a deterministic fix
            modified_inputs=fixed_inputs,
        )

    # Mapping of invalid agent types to their correct equivalents
    AGENT_TYPE_CORRECTIONS = {
        # Strategy/marketing agents -> compose
        "marketing_strategist": "compose",
        "strategy_agent": "compose",
        "strategist": "compose",
        "marketing_agent": "compose",
        "content_strategist": "compose",
        "copywriter": "compose",
        "writer": "compose",
        # PDF/document agents -> html_to_pdf
        "pdf_composer": "html_to_pdf",
        "pdf_generator": "html_to_pdf",
        "pdf_creator": "html_to_pdf",
        "document_generator": "html_to_pdf",
        "report_generator": "compose",  # Text reports -> compose
        # Research agents -> web_research
        "researcher": "web_research",
        "research_agent": "web_research",
        "web_scraper": "http_fetch",
        # Analysis agents -> analyze
        "data_analyst": "analyze",
        "analyzer": "analyze",
        "insight_generator": "analyze",
        # Common misspellings/variations
        "summarizer": "summarize",
        "aggregator": "aggregate",
        "image_generator": "generate_image",
        "image_gen": "generate_image",
        "notification": "notify",
        "notifier": "notify",
        "email": "notify",
        "storage": "file_storage",
    }

    def _is_invalid_agent_type_error(self, error_message: str) -> bool:
        """Check if the error is due to an invalid/unknown agent type."""
        if not error_message:
            return False
        error_lower = error_message.lower()
        return "unknown subagent type" in error_lower or "unknown agent type" in error_lower

    def _get_suggested_agent_type(self, invalid_type: str) -> Optional[str]:
        """Get suggested correction for an invalid agent type."""
        # Check exact match first
        if invalid_type.lower() in self.AGENT_TYPE_CORRECTIONS:
            return self.AGENT_TYPE_CORRECTIONS[invalid_type.lower()]

        # Try fuzzy matching based on keywords
        invalid_lower = invalid_type.lower()
        if "strategy" in invalid_lower or "marketing" in invalid_lower:
            return "compose"
        if "pdf" in invalid_lower or "document" in invalid_lower:
            return "html_to_pdf"
        if "research" in invalid_lower or "search" in invalid_lower:
            return "web_research"
        if "analyze" in invalid_lower or "analysis" in invalid_lower:
            return "analyze"
        if "summary" in invalid_lower or "summarize" in invalid_lower:
            return "summarize"
        if "image" in invalid_lower or "picture" in invalid_lower:
            return "generate_image"
        if "notify" in invalid_lower or "email" in invalid_lower:
            return "notify"
        if "storage" in invalid_lower or "file" in invalid_lower:
            return "file_storage"
        if "aggregate" in invalid_lower or "combine" in invalid_lower:
            return "aggregate"

        return None

    def _extract_invalid_agent_type(self, error_message: str) -> Optional[str]:
        """Extract the invalid agent type from the error message."""
        # Pattern: "Unknown subagent type: {type}. Available: [...]"
        import re
        match = re.search(r"unknown subagent type:\s*([^\s.]+)", error_message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    async def _generate_agent_type_replan_proposal(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> ObserverProposal:
        """
        Generate a REPLAN proposal for invalid agent type errors.

        Since agent_type cannot be modified at runtime, we need a replan
        that corrects the agent type for the affected step(s).
        """
        invalid_type = self._extract_invalid_agent_type(failed_step.error_message)
        suggested_type = self._get_suggested_agent_type(invalid_type) if invalid_type else None

        # Build context for replan
        available_types = [
            "http_fetch", "summarize", "compose", "notify", "analyze",
            "transform", "file_storage", "generate_image", "html_to_pdf",
            "schedule_job", "document_db", "agent_storage", "web_research", "aggregate"
        ]

        diagnosis = f"Step '{failed_step.name}' uses invalid agent type '{invalid_type}'."
        if suggested_type:
            diagnosis += f" Suggested replacement: '{suggested_type}'."
        diagnosis += f" Valid types: {', '.join(available_types)}"

        # Collect completed step outputs for replan context
        completed_outputs = {}
        for step in plan.steps:
            if step.status == StepStatus.DONE and step.outputs:
                # Summarize outputs for context
                output_keys = list(step.outputs.keys()) if isinstance(step.outputs, dict) else []
                completed_outputs[step.id] = {
                    "name": step.name,
                    "agent_type": step.agent_type,
                    "output_keys": output_keys,
                }

        # Build suggested approach as single string
        suggestions = []
        if suggested_type:
            suggestions.append(f"Replace '{invalid_type}' with '{suggested_type}'")
        suggestions.extend([
            "For strategy/writing tasks, use 'compose' agent",
            "For PDF generation, use 'html_to_pdf' agent",
        ])
        suggested_approach = "; ".join(suggestions)

        replan_context = ReplanContext(
            diagnosis=diagnosis,
            affected_steps=[failed_step.id],  # The step that needs fixing
            completed_outputs=completed_outputs,
            constraints=[
                f"Must use valid agent types from: {', '.join(available_types)}",
                f"The step '{failed_step.name}' should use '{suggested_type}' instead of '{invalid_type}'" if suggested_type else "",
                "Do NOT use non-existent agent types like 'marketing_strategist', 'pdf_composer', etc.",
            ],
            suggested_approach=suggested_approach,
        )

        logger.info(
            "Generating REPLAN proposal for invalid agent type",
            plan_id=plan.id,
            step_id=failed_step.id,
            invalid_type=invalid_type,
            suggested_type=suggested_type,
        )

        return ObserverProposal(
            proposal_type=ProposalType.REPLAN,
            step_id=failed_step.id,
            reason=diagnosis,
            confidence=0.9,  # High confidence - this is a clear planning error
            replan_context=replan_context,
        )

    async def analyze_failure(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> ObserverProposal:
        """
        Analyze a step failure and propose a recovery action.

        Uses LLM reasoning to determine the best course of action:
        - MODIFY: Content filter/validation error, can fix inputs and retry
        - RETRY: Transient failure, retries available
        - FALLBACK: Permanent failure, fallback available
        - SKIP: Non-critical step
        - ABORT: Critical failure, no recovery

        Args:
            plan: The current plan document
            failed_step: The step that failed

        Returns:
            ObserverProposal with recommended action
        """
        logger.info(
            "Observer analyzing failure",
            plan_id=plan.id,
            step_id=failed_step.id,
            step_name=failed_step.name,
            error=failed_step.error_message,
        )

        # Check for template syntax errors FIRST - these are deterministic fixes
        # Template errors often manifest as "no data provided" or similar downstream errors
        has_template_errors = self._has_template_syntax_errors(failed_step)
        is_template_related = self._is_template_related_error(failed_step.error_message)

        if has_template_errors and failed_step.retry_count < 2:
            logger.info(
                "Template syntax errors detected in step inputs",
                step_id=failed_step.id,
                errors=self._get_template_syntax_errors(failed_step),
            )
            return await self._generate_template_fix_proposal(plan, failed_step)

        # Even if inputs look valid, the error might indicate a template issue
        # (e.g., templates resolved to empty values before this step ran)
        if is_template_related and failed_step.retry_count < 2:
            # Check if any dependency steps have template issues we can trace
            for dep_id in failed_step.dependencies:
                dep_step = next((s for s in plan.steps if s.id == dep_id), None)
                if dep_step and self._has_template_syntax_errors(dep_step):
                    logger.info(
                        "Template error traced to dependency step",
                        failed_step_id=failed_step.id,
                        dependency_step_id=dep_id,
                    )
                    # The issue is upstream - we can't fix it here
                    # Fall through to other analysis

        # Check for invalid agent type errors - these require REPLAN
        # Cannot fix agent type at runtime, need to regenerate the plan
        if self._is_invalid_agent_type_error(failed_step.error_message):
            logger.info(
                "Invalid agent type detected, proposing replan",
                step_id=failed_step.id,
                error=failed_step.error_message,
            )
            return await self._generate_agent_type_replan_proposal(plan, failed_step)

        # Check for content filter errors - these can be fixed with MODIFY
        is_content_filter = self._is_content_filter_error(failed_step.error_message)
        can_modify = self._is_modifiable_step(failed_step)

        if is_content_filter and can_modify and failed_step.retry_count < 2:
            # Use LLM to generate modified inputs
            return await self._generate_modify_proposal(plan, failed_step)

        # Build fallback info
        fallback_info = "No fallbacks available"
        if failed_step.fallback_config and failed_step.fallback_config.has_options():
            options = []
            if failed_step.fallback_config.models:
                options.append(f"Models: {', '.join(failed_step.fallback_config.models)}")
            if failed_step.fallback_config.apis:
                options.append(f"APIs: {', '.join(failed_step.fallback_config.apis)}")
            if options:
                fallback_info = "; ".join(options)

        # Build analysis prompt
        prompt = f"""<context>
You are monitoring a workflow execution. A step has failed.
</context>

<plan>
Goal: {plan.goal}
Status: {plan.status.value}
</plan>

<failed_step>
ID: {failed_step.id}
Name: {failed_step.name}
Description: {failed_step.description}
Agent Type: {failed_step.agent_type}
Error: {failed_step.error_message}
Is Critical: {failed_step.is_critical}
Retry Count: {failed_step.retry_count}/{failed_step.max_retries}
Fallback Options: {fallback_info}
</failed_step>

<decision_rules>
Choose ONE action:
- RETRY: Use when failure is transient (timeout, rate limit) and retries remain
- FALLBACK: Use when failure appears permanent but fallback exists
- SKIP: Use when step is non-critical (is_critical: false) and plan can continue
- ABORT: Use when step is critical, has no fallback, and retries exhausted
</decision_rules>

<task>
Choose ONE action and explain briefly.
Format:
ACTION: [RETRY|FALLBACK|SKIP|ABORT]
FALLBACK_TARGET: [target if FALLBACK, otherwise omit]
REASON: [Brief explanation]
</task>"""

        try:
            # Use LLM for analysis
            response = await self.llm_client.create_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                routing=ModelRouting.single(self.model),
                temperature=0.0,
                max_tokens=200,
            )

            proposal = self._parse_failure_analysis(response.content, failed_step)

            logger.info(
                "Observer proposal",
                step_id=failed_step.id,
                proposal_type=proposal.proposal_type.value,
                fallback_target=proposal.fallback_target,
                confidence=proposal.confidence,
            )

            return proposal

        except Exception as e:
            logger.error(
                "Observer analysis failed, using rule-based fallback",
                error=str(e),
            )
            return self._rule_based_proposal(failed_step)

    async def _generate_modify_proposal(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> ObserverProposal:
        """
        Generate a MODIFY proposal with rewritten inputs to avoid content filters.

        Uses LLM to intelligently rewrite problematic inputs (e.g., prompts that
        triggered copyright/trademark filters) while preserving the intent.
        """
        logger.info(
            "Generating MODIFY proposal for content filter error",
            plan_id=plan.id,
            step_id=failed_step.id,
            agent_type=failed_step.agent_type,
        )

        # Get current inputs to modify
        current_inputs = failed_step.inputs.copy()

        # Build prompt for input modification
        prompt = f"""<context>
A workflow step failed due to a content filter. You need to modify the inputs to avoid the filter while preserving the original intent.
</context>

<plan_goal>
{plan.goal}
</plan_goal>

<failed_step>
Name: {failed_step.name}
Type: {failed_step.agent_type}
Error: {failed_step.error_message}
</failed_step>

<current_inputs>
{json.dumps(current_inputs, indent=2)}
</current_inputs>

<task>
Rewrite the inputs to avoid content filters (copyright, trademark, derivative works).
Key strategies:
- Replace brand names with generic descriptions (e.g., "Polytopia" → "turn-based strategy game with tribes")
- Use descriptive language instead of copyrighted terms
- Keep the same intent and style
- For image prompts, describe the visual concept without referencing specific IP

Output ONLY the modified inputs as a valid JSON object.
If a "prompt" field exists, rewrite it. Preserve all other fields unchanged.
</task>

<output_format>
Return ONLY a JSON object with the modified inputs. Example:
{{"prompt": "A colorful turn-based strategy game map with different terrain types and tribal warriors"}}
</output_format>"""

        try:
            logger.debug(
                "Calling LLM for MODIFY proposal",
                step_id=failed_step.id,
                model=self.model,
            )
            # Use the LLM client as async context manager to ensure proper initialization
            async with self.llm_client as client:
                response = await client.create_completion(
                    messages=[LLMMessage(role="user", content=prompt)],
                    routing=ModelRouting.single(self.model),
                    temperature=0.3,  # Slightly creative for rewrites
                    max_tokens=500,
                )

            logger.debug(
                "LLM response received for MODIFY",
                step_id=failed_step.id,
                response_length=len(response.content) if response.content else 0,
                response_preview=response.content[:200] if response.content else "EMPTY",
            )

            # Parse JSON from response
            modified_inputs = self._parse_json_from_response(response.content)

            logger.debug(
                "JSON parsing result for MODIFY",
                step_id=failed_step.id,
                parsed_successfully=modified_inputs is not None,
                keys=list(modified_inputs.keys()) if modified_inputs else None,
            )

            if modified_inputs:
                # Merge with original inputs (modified values override)
                final_inputs = {**current_inputs, **modified_inputs}

                logger.info(
                    "MODIFY proposal generated",
                    step_id=failed_step.id,
                    original_prompt=current_inputs.get("prompt", "")[:100],
                    modified_prompt=final_inputs.get("prompt", "")[:100],
                )

                return ObserverProposal(
                    proposal_type=ProposalType.MODIFY,
                    step_id=failed_step.id,
                    reason="Content filter detected. Rewrote inputs to avoid copyright/trademark terms while preserving intent.",
                    confidence=0.85,
                    modified_inputs=final_inputs,
                )

        except Exception as e:
            import traceback
            logger.warning(
                "Failed to generate modified inputs, falling back to ABORT",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
            )

        # Fallback to ABORT if modification failed
        return ObserverProposal(
            proposal_type=ProposalType.ABORT,
            step_id=failed_step.id,
            reason=f"Content filter error and input modification failed: {failed_step.error_message}",
            confidence=0.6,
        )

    def _parse_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object from LLM response."""
        import re

        # Try to find JSON in the response
        # Look for content between { and } (including nested)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try the entire response as JSON
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        return None

    def _parse_failure_analysis(
        self,
        response: str,
        step: TaskStep,
    ) -> ObserverProposal:
        """Parse the LLM response into an ObserverProposal."""
        lines = response.strip().split('\n')
        action = ProposalType.ABORT
        fallback_target = None
        reason = response

        for line in lines:
            line_stripped = line.strip()
            line_upper = line_stripped.upper()

            # Parse ACTION line
            if line_upper.startswith("ACTION:"):
                action_str = line_upper.split("ACTION:")[1].strip().split()[0]
                if action_str == "RETRY":
                    action = ProposalType.RETRY
                elif action_str == "FALLBACK":
                    action = ProposalType.FALLBACK
                elif action_str == "SKIP":
                    action = ProposalType.SKIP
                elif action_str == "ABORT":
                    action = ProposalType.ABORT

            # Parse FALLBACK_TARGET line
            elif line_upper.startswith("FALLBACK_TARGET:"):
                fallback_target = line_stripped.split(":", 1)[1].strip()

            # Parse REASON line
            elif line_upper.startswith("REASON:"):
                reason = line_stripped.split(":", 1)[1].strip()

        # If FALLBACK but no target, use first available
        if action == ProposalType.FALLBACK and not fallback_target:
            if step.fallback_config:
                fallback_target = (
                    step.fallback_config.get_first_model() or
                    step.fallback_config.get_first_api()
                )

        confidence = 0.9 if action != ProposalType.ABORT else 0.7

        return ObserverProposal(
            proposal_type=action,
            step_id=step.id,
            reason=reason,
            confidence=confidence,
            fallback_target=fallback_target,
        )

    def _rule_based_proposal(self, step: TaskStep) -> ObserverProposal:
        """
        Generate a proposal using simple rules when LLM is unavailable.
        """
        # Rule 1: If retries remain and error looks transient, retry
        if step.retry_count < step.max_retries:
            transient_indicators = ["timeout", "rate limit", "temporary", "try again", "503", "429"]
            error_lower = (step.error_message or "").lower()
            if any(ind in error_lower for ind in transient_indicators):
                return ObserverProposal(
                    proposal_type=ProposalType.RETRY,
                    step_id=step.id,
                    reason="Error appears transient, retrying",
                    confidence=0.6,
                )

        # Rule 2: If fallback available, use it
        if step.fallback_config and step.fallback_config.has_options():
            target = step.fallback_config.get_first_model() or step.fallback_config.get_first_api()
            return ObserverProposal(
                proposal_type=ProposalType.FALLBACK,
                step_id=step.id,
                reason="Using fallback option",
                fallback_target=target,
                confidence=0.7,
            )

        # Rule 3: If non-critical, skip
        if not step.is_critical:
            return ObserverProposal(
                proposal_type=ProposalType.SKIP,
                step_id=step.id,
                reason="Non-critical step, skipping",
                confidence=0.8,
            )

        # Rule 4: Abort
        return ObserverProposal(
            proposal_type=ProposalType.ABORT,
            step_id=step.id,
            reason="Critical step failed with no recovery options",
            confidence=0.9,
        )

    async def analyze_for_replan(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> Optional[ObserverProposal]:
        """
        Analyze if strategic replanning is needed instead of tactical recovery.

        This method is called when tactical options (RETRY/FALLBACK/SKIP) are
        exhausted. It determines if the TaskPlannerAgent should be invoked
        to revise the plan.

        Triggers REPLAN when:
        - The failure indicates a structural problem (API changed, dependency broken)
        - Multiple related steps would fail
        - There's a better alternative approach

        Args:
            plan: The current plan document
            failed_step: The step that failed

        Returns:
            ObserverProposal with REPLAN if replanning is recommended, None otherwise
        """
        logger.info(
            "Analyzing for strategic replan",
            plan_id=plan.id,
            step_id=failed_step.id,
            step_name=failed_step.name,
            error=failed_step.error_message,
        )

        # Collect completed outputs for context
        completed_outputs = {}
        for step in plan.steps:
            if step.status == StepStatus.DONE and step.outputs:
                completed_outputs[step.id] = step.outputs

        # Build replan analysis prompt
        prompt = f"""<context>
You are analyzing whether a failed workflow step requires strategic replanning.
Tactical recovery (retry, fallback, skip) has been exhausted or is not applicable.
</context>

<plan>
Goal: {plan.goal}
Status: {plan.status.value}
Progress: {plan.get_progress_percentage():.1f}%
Completed steps: {len([s for s in plan.steps if s.status == StepStatus.DONE])}
Total steps: {len(plan.steps)}
</plan>

<failed_step>
ID: {failed_step.id}
Name: {failed_step.name}
Description: {failed_step.description}
Agent Type: {failed_step.agent_type}
Error: {failed_step.error_message}
Is Critical: {failed_step.is_critical}
Retry Count: {failed_step.retry_count}/{failed_step.max_retries}
</failed_step>

<accumulated_findings>
{json.dumps([f.to_dict() for f in plan.accumulated_findings[-5:]], indent=2)}
</accumulated_findings>

<remaining_steps>
{json.dumps([{"id": s.id, "name": s.name, "depends_on": s.dependencies} for s in plan.steps if s.status == StepStatus.PENDING], indent=2)}
</remaining_steps>

<task>
Determine if strategic replanning is needed.

REPLAN is appropriate when:
1. The error indicates a structural problem (API changed, endpoint deprecated, format changed)
2. The original approach won't work and needs a different strategy
3. Multiple downstream steps would be affected by this failure
4. There's a clear alternative approach that could achieve the goal

REPLAN is NOT appropriate when:
1. The failure is truly unrecoverable (goal is impossible)
2. The error is just bad data that no approach could fix
3. The plan has already been replanned multiple times for the same issue

Respond in this format:
NEEDS_REPLAN: [true|false]
DIAGNOSIS: [What went wrong and why tactical recovery won't work]
AFFECTED_STEPS: [Comma-separated step IDs that need revision]
CONSTRAINTS: [Any new constraints discovered, comma-separated]
SUGGESTED_APPROACH: [How the plan could be modified to succeed]
CONFIDENCE: [0.0-1.0]
</task>"""

        try:
            response = await self.llm_client.create_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                routing=ModelRouting.single(self.model),
                temperature=0.0,
                max_tokens=400,
            )

            result = self._parse_replan_analysis(
                response.content,
                plan,
                failed_step,
                completed_outputs,
            )

            if result:
                logger.info(
                    "Observer proposes REPLAN",
                    plan_id=plan.id,
                    step_id=failed_step.id,
                    diagnosis=result.replan_context.diagnosis if result.replan_context else None,
                    confidence=result.confidence,
                )

            return result

        except Exception as e:
            logger.error(
                "Replan analysis failed",
                error=str(e),
                plan_id=plan.id,
            )
            return None

    def _parse_replan_analysis(
        self,
        response: str,
        plan: Task,
        step: TaskStep,
        completed_outputs: Dict[str, Any],
    ) -> Optional[ObserverProposal]:
        """Parse the LLM replan analysis response."""
        lines = response.strip().split('\n')

        needs_replan = False
        diagnosis = ""
        affected_steps = []
        constraints = []
        suggested_approach = None
        confidence = 0.7

        for line in lines:
            line_stripped = line.strip()
            line_upper = line_stripped.upper()

            if line_upper.startswith("NEEDS_REPLAN:"):
                value = line_upper.split(":", 1)[1].strip()
                needs_replan = value == "TRUE"

            elif line_upper.startswith("DIAGNOSIS:"):
                diagnosis = line_stripped.split(":", 1)[1].strip()

            elif line_upper.startswith("AFFECTED_STEPS:"):
                steps_str = line_stripped.split(":", 1)[1].strip()
                affected_steps = [s.strip() for s in steps_str.split(",") if s.strip()]

            elif line_upper.startswith("CONSTRAINTS:"):
                constraints_str = line_stripped.split(":", 1)[1].strip()
                constraints = [c.strip() for c in constraints_str.split(",") if c.strip()]

            elif line_upper.startswith("SUGGESTED_APPROACH:"):
                suggested_approach = line_stripped.split(":", 1)[1].strip()

            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_stripped.split(":", 1)[1].strip())
                except ValueError:
                    confidence = 0.7

        if not needs_replan:
            return None

        # Ensure the failed step is in affected steps
        if step.id not in affected_steps:
            affected_steps.insert(0, step.id)

        replan_context = ReplanContext(
            diagnosis=diagnosis or f"Step {step.name} failed: {step.error_message}",
            affected_steps=affected_steps,
            completed_outputs=completed_outputs,
            constraints=constraints,
            suggested_approach=suggested_approach,
        )

        return ObserverProposal(
            proposal_type=ProposalType.REPLAN,
            step_id=step.id,
            reason=f"Strategic replanning needed: {diagnosis}",
            confidence=confidence,
            replan_context=replan_context,
        )

    def _build_execution_state(self, plan: Task) -> Dict[str, Any]:
        """Build execution state from plan."""
        completed_steps = [s for s in plan.steps if s.status == StepStatus.DONE]
        failed_steps = [s for s in plan.steps if s.status == StepStatus.FAILED]
        running_steps = [s for s in plan.steps if s.status == StepStatus.RUNNING]
        pending_steps = [s for s in plan.steps if s.status == StepStatus.PENDING]

        return {
            "plan_status": plan.status.value,
            "total_steps": len(plan.steps),
            "completed_steps": len(completed_steps),
            "failed_steps": len(failed_steps),
            "running_steps": len(running_steps),
            "pending_steps": len(pending_steps),
            "current_step_index": plan.current_step_index,
            "version": plan.version,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "status": s.status.value,
                    "agent_type": s.agent_type,
                    "retry_count": s.retry_count,
                    "error": s.error_message,
                }
                for s in plan.steps
            ],
        }

    def _parse_observation_report(
        self, plan_id: str, plan: Task, content: str
    ) -> ObservationReport:
        """Parse XML observation report from LLM response."""
        # Extract progress
        progress_match = re.search(r'<percentage>(\d+(?:\.\d+)?)</percentage>', content)
        progress_pct = float(progress_match.group(1)) if progress_match else plan.get_progress_percentage()

        completed_match = re.search(r'<steps_completed>(\d+)</steps_completed>', content)
        steps_completed = int(completed_match.group(1)) if completed_match else sum(
            1 for s in plan.steps if s.status == StepStatus.DONE
        )

        current_match = re.search(r'<current_step>([^<]+)</current_step>', content)
        current_step = current_match.group(1).strip() if current_match else None
        if current_step == "null":
            current_step = None

        # Extract health
        health_match = re.search(r'<status>(healthy|degraded|critical)</status>', content)
        health_status = health_match.group(1) if health_match else "healthy"

        # Extract anomalies
        anomalies = []
        anomaly_pattern = r'<anomaly[^>]*type="([^"]*)"[^>]*severity="([^"]*)"[^>]*>(.*?)</anomaly>'
        for match in re.finditer(anomaly_pattern, content, re.DOTALL):
            anomaly_type, severity, anomaly_content = match.groups()

            desc_match = re.search(r'<description>(.*?)</description>', anomaly_content, re.DOTALL)
            evidence_match = re.search(r'<evidence>(.*?)</evidence>', anomaly_content, re.DOTALL)
            impact_match = re.search(r'<impact>(.*?)</impact>', anomaly_content, re.DOTALL)

            anomalies.append({
                "type": anomaly_type,
                "severity": severity,
                "description": desc_match.group(1).strip() if desc_match else "",
                "evidence": evidence_match.group(1).strip() if evidence_match else "",
                "impact": impact_match.group(1).strip() if impact_match else "",
            })

        # Extract proposals
        proposals = []
        proposal_pattern = r'<proposal[^>]*priority="(\d+)"[^>]*>(.*?)</proposal>'
        for match in re.finditer(proposal_pattern, content, re.DOTALL):
            priority, proposal_content = match.groups()

            action_match = re.search(r'<action>(.*?)</action>', proposal_content, re.DOTALL)
            reason_match = re.search(r'<reason>(.*?)</reason>', proposal_content, re.DOTALL)
            risk_match = re.search(r'<risk>(.*?)</risk>', proposal_content, re.DOTALL)

            proposals.append({
                "priority": int(priority),
                "action": action_match.group(1).strip() if action_match else "",
                "reason": reason_match.group(1).strip() if reason_match else "",
                "risk": risk_match.group(1).strip() if risk_match else "",
            })

        # Sort proposals by priority
        proposals.sort(key=lambda p: p["priority"])

        # Extract recommendation
        rec_match = re.search(r'<recommendation>(continue|pause|escalate)</recommendation>', content)
        recommendation = rec_match.group(1) if rec_match else "continue"

        reason_match = re.search(r'<recommendation_reason>(.*?)</recommendation_reason>', content, re.DOTALL)
        recommendation_reason = reason_match.group(1).strip() if reason_match else ""

        return ObservationReport(
            plan_id=plan_id,
            progress_pct=progress_pct,
            steps_completed=steps_completed,
            steps_total=len(plan.steps),
            current_step=current_step,
            health_status=health_status,
            anomalies=anomalies,
            proposals=proposals,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
        )

    def _create_error_report(self, plan_id: str, error: str) -> ObservationReport:
        """Create an error observation report."""
        return ObservationReport(
            plan_id=plan_id,
            progress_pct=0,
            steps_completed=0,
            steps_total=0,
            current_step=None,
            health_status="critical",
            anomalies=[{
                "type": "error",
                "severity": "critical",
                "description": error,
                "evidence": "",
                "impact": "Cannot monitor plan execution",
            }],
            proposals=[],
            recommendation="escalate",
            recommendation_reason=f"Observation error: {error}",
        )

    async def continuous_observe(
        self,
        plan_id: str,
        interval_seconds: int = 30,
        max_observations: int = 100,
    ):
        """
        Generator that yields observations at regular intervals.

        Use this for continuous monitoring during long-running tasks.

        Args:
            plan_id: The plan to observe
            interval_seconds: Time between observations
            max_observations: Maximum number of observations

        Yields:
            ObservationReport objects
        """
        import asyncio

        for i in range(max_observations):
            report = await self.observe(plan_id)
            yield report

            # Stop if plan is complete or escalation needed
            if report.should_escalate:
                logger.warning(
                    "Observer recommending escalation",
                    plan_id=plan_id,
                    reason=report.recommendation_reason,
                )
                break

            # Check if plan is terminal
            store = await self._get_plan_store()
            plan = await store.get_task(plan_id)
            if plan and plan.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                break

            await asyncio.sleep(interval_seconds)

    async def analyze_blocked_dependencies(
        self,
        plan: Task,
        blocked_steps: List[TaskStep],
        failed_steps: List[TaskStep],
    ) -> Optional[ObserverProposal]:
        """
        Analyze when pending steps are blocked due to failed dependencies.

        This is called when the orchestrator finds no ready steps but the plan
        isn't complete - typically when parallel steps failed and downstream
        steps can't proceed.

        Args:
            plan: The current plan document
            blocked_steps: Pending steps that can't proceed
            failed_steps: Steps that failed and are blocking others

        Returns:
            ObserverProposal with REPLAN to use partial data, or None
        """
        logger.info(
            "Analyzing blocked dependencies",
            plan_id=plan.id,
            blocked_count=len(blocked_steps),
            failed_count=len(failed_steps),
            blocked_ids=[s.id for s in blocked_steps],
            failed_ids=[s.id for s in failed_steps],
        )

        # Collect completed outputs for context
        completed_outputs = {}
        completed_steps = []
        for step in plan.steps:
            if step.status == StepStatus.DONE and step.outputs:
                completed_outputs[step.id] = step.outputs
                completed_steps.append(step)

        # Build failure summary
        failures_summary = []
        for step in failed_steps:
            failures_summary.append({
                "id": step.id,
                "name": step.name,
                "error": step.error_message,
                "retry_count": step.retry_count,
            })

        # Build blocked summary
        blocked_summary = []
        for step in blocked_steps:
            failed_deps = [d for d in step.dependencies if any(f.id == d for f in failed_steps)]
            blocked_summary.append({
                "id": step.id,
                "name": step.name,
                "dependencies": step.dependencies,
                "failed_dependencies": failed_deps,
            })

        # Build prompt for LLM analysis
        prompt = f"""<context>
You are analyzing a workflow that is blocked because some parallel steps failed,
preventing downstream steps from executing. We have partial results from
successful steps that could still be used to achieve the goal.
</context>

<plan>
Goal: {plan.goal}
Status: {plan.status.value}
Progress: {plan.get_progress_percentage():.1f}%
</plan>

<completed_steps>
{json.dumps([{"id": s.id, "name": s.name, "outputs_preview": str(s.outputs)[:200] if s.outputs else "None"} for s in completed_steps], indent=2)}
</completed_steps>

<failed_steps>
{json.dumps(failures_summary, indent=2)}
</failed_steps>

<blocked_steps>
{json.dumps(blocked_summary, indent=2)}
</blocked_steps>

<task>
Determine if we should replan to use partial data from successful steps.

Key questions:
1. Can we achieve a useful result with the partial data we have?
2. Should we modify the goal to work with available data?
3. What's the best path forward?

REPLAN is appropriate when:
- We have useful partial results that can be synthesized
- The goal can be partially achieved with available data
- Retrying failed steps would likely fail again (e.g., website blocking)

ABORT is appropriate when:
- The partial data is insufficient for any useful output
- The goal fundamentally requires all data sources

Respond in this format:
NEEDS_REPLAN: [true|false]
DIAGNOSIS: [What went wrong and why we're blocked]
PARTIAL_DATA_VALUE: [What useful data we have from successful steps]
SUGGESTED_APPROACH: [How to modify the plan to use partial data]
CONFIDENCE: [0.0-1.0]
</task>"""

        try:
            response = await self.llm_client.create_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                routing=ModelRouting.single(self.model),
                temperature=0.0,
                max_tokens=400,
            )

            result = self._parse_blocked_analysis(
                response.content,
                plan,
                blocked_steps,
                failed_steps,
                completed_outputs,
            )

            if result:
                logger.info(
                    "Observer proposes REPLAN for blocked dependencies",
                    plan_id=plan.id,
                    diagnosis=result.replan_context.diagnosis if result.replan_context else None,
                    confidence=result.confidence,
                )
            else:
                logger.info(
                    "Observer does not recommend replan for blocked state",
                    plan_id=plan.id,
                )

            return result

        except Exception as e:
            logger.error(
                "Blocked dependency analysis failed",
                error=str(e),
                plan_id=plan.id,
            )
            # Conservative fallback: only suggest REPLAN if:
            # 1. A significant portion of remaining work is blocked (>50%)
            # 2. We have useful completed outputs to work with
            # 3. All failed steps are marked as critical
            #
            # Otherwise, return None to let the orchestrator handle it
            # (which will mark the plan as failed)
            total_remaining = len(blocked_steps) + len(failed_steps)
            blocked_ratio = len(blocked_steps) / max(total_remaining, 1)
            all_critical = all(s.is_critical for s in failed_steps)

            # Only suggest replan if we have significant completed work AND many steps are blocked
            if completed_outputs and blocked_ratio >= 0.5 and len(completed_outputs) >= 2:
                logger.info(
                    "Falling back to rule-based replan proposal (significant blockage)",
                    plan_id=plan.id,
                    completed_count=len(completed_outputs),
                    blocked_ratio=blocked_ratio,
                )
                return ObserverProposal(
                    proposal_type=ProposalType.REPLAN,
                    step_id=blocked_steps[0].id if blocked_steps else failed_steps[0].id,
                    reason=f"Blocked due to {len(failed_steps)} failed dependencies, but have {len(completed_outputs)} completed step outputs to use",
                    confidence=0.7,
                    replan_context=ReplanContext(
                        diagnosis=f"Workflow blocked: {len(failed_steps)} steps failed, blocking {len(blocked_steps)} downstream steps",
                        affected_steps=[s.id for s in blocked_steps] + [s.id for s in failed_steps],
                        completed_outputs=completed_outputs,
                        constraints=[f"Cannot access: {s.name}" for s in failed_steps],
                        suggested_approach="Replan to synthesize results from available data only",
                    ),
                )

            logger.info(
                "Not suggesting replan in fallback - insufficient data or blockage",
                plan_id=plan.id,
                completed_count=len(completed_outputs),
                blocked_ratio=blocked_ratio,
            )
            return None

    def _parse_blocked_analysis(
        self,
        response: str,
        plan: Task,
        blocked_steps: List[TaskStep],
        failed_steps: List[TaskStep],
        completed_outputs: Dict[str, Any],
    ) -> Optional[ObserverProposal]:
        """Parse the LLM blocked analysis response."""
        lines = response.strip().split('\n')

        needs_replan = False
        diagnosis = ""
        partial_data_value = ""
        suggested_approach = None
        confidence = 0.7

        for line in lines:
            line_stripped = line.strip()
            line_upper = line_stripped.upper()

            if line_upper.startswith("NEEDS_REPLAN:"):
                value = line_upper.split(":", 1)[1].strip()
                needs_replan = value == "TRUE"

            elif line_upper.startswith("DIAGNOSIS:"):
                diagnosis = line_stripped.split(":", 1)[1].strip()

            elif line_upper.startswith("PARTIAL_DATA_VALUE:"):
                partial_data_value = line_stripped.split(":", 1)[1].strip()

            elif line_upper.startswith("SUGGESTED_APPROACH:"):
                suggested_approach = line_stripped.split(":", 1)[1].strip()

            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line_stripped.split(":", 1)[1].strip())
                except ValueError:
                    confidence = 0.7

        if not needs_replan:
            return None

        # Build replan context with partial data info
        all_affected = [s.id for s in blocked_steps] + [s.id for s in failed_steps]
        constraints = [f"Cannot access: {s.name} ({s.error_message})" for s in failed_steps]

        replan_context = ReplanContext(
            diagnosis=diagnosis or f"Blocked due to {len(failed_steps)} failed dependencies",
            affected_steps=all_affected,
            completed_outputs=completed_outputs,
            constraints=constraints,
            suggested_approach=suggested_approach or f"Use partial data: {partial_data_value}",
        )

        return ObserverProposal(
            proposal_type=ProposalType.REPLAN,
            step_id=blocked_steps[0].id if blocked_steps else failed_steps[0].id,
            reason=f"Strategic replan with partial data: {diagnosis}",
            confidence=confidence,
            replan_context=replan_context,
        )

    async def cleanup(self) -> None:
        """Cleanup observer resources."""
        if self._plan_store:
            await self._plan_store.disconnect()
        await super().cleanup()
