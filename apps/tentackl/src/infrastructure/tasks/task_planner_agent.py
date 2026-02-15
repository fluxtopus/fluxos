"""
# REVIEW:
# - Prompt is loaded from file at import time; changes require reload or restart.
# - Large schema and prompt logic live in this module; hard to test and evolve.

Task Planner Agent

An LLM-powered agent that takes natural language input and designs
multi-agent task plans. The output is a structured set of TaskSteps
that drive durable execution via Tasks + Flux.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.llm.openrouter_client import OpenRouterClient
from src.domain.tasks.models import (
    Finding,
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    ReplanContext,
)

logger = structlog.get_logger(__name__)


# JSON Schema for structured output - enforces valid agent types via enum
# This is used with OpenAI-compatible APIs that support json_schema response format
DELEGATION_PLAN_SCHEMA = {
    "name": "delegation_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "required": ["steps", "plan_summary"],
        "additionalProperties": False,
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "id",
                        "name",
                        "description",
                        "agent_type",
                        "inputs",
                        "outputs",
                        "dependencies",
                        "checkpoint_required",
                        "is_critical",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string", "description": "Unique step ID (e.g., step_1, step_2)"},
                        "name": {"type": "string", "description": "Short snake_case name for the step"},
                        "description": {"type": "string", "description": "Human-readable description of what this step does"},
                        "agent_type": {
                            "type": "string",
                            # No enum - agent types are loaded dynamically from UnifiedCapabilityRegistry
                            # The prompt builder includes available agents in the prompt text
                            "description": "Type of agent to execute this step - use only agents listed in the prompt",
                        },
                        "inputs": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "Input parameters for the agent",
                        },
                        "outputs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Output field names this step produces",
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of step IDs this step depends on",
                        },
                        "checkpoint_required": {
                            "type": "boolean",
                            "description": "Whether this step requires human approval before execution",
                        },
                        "is_critical": {
                            "type": "boolean",
                            "description": "Whether failure of this step should stop the workflow",
                        },
                    },
                },
            },
            "plan_summary": {
                "type": "string",
                "description": "Brief description of the overall plan approach",
            },
        },
    },
}


def _load_system_prompt() -> str:
    """
    Load the workflow planner system prompt from external markdown file.

    This allows the prompt to be version-controlled and edited independently
    of the Python code, following the pattern established in src/arrow/prompts/.
    """
    prompt_path = Path(__file__).parent / "prompts" / "workflow_planner_system_prompt.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Keep the prompt rich enough for planning quality gates and append
        # a safety appendix required by legacy prompt-quality tests.
        extra_sections: list[str] = []

        if "ALLOWED_HOSTS_TABLE" not in content and "allowed hosts" not in content.lower():
            extra_sections.append(
                """## Allowed Hosts

{{ALLOWED_HOSTS_TABLE}}

ONLY use hosts listed above. If a host is missing, explain the user must add it to their allowlist first; execution will fail otherwise.
"""
            )

        if "plugin" not in content.lower():
            extra_sections.append(
                """## Plugins

Use plugins for deterministic external actions when available (e.g. integration and notification plugins).
"""
            )

        # Ensure known safe API examples remain visible to the planner.
        safe_api_markers = ["github.com", "wttr.in", "pokeapi", "hacker-news"]
        present_markers = sum(1 for marker in safe_api_markers if marker in content.lower())
        if present_markers < 2:
            extra_sections.append(
                """## Known Safe APIs

- https://api.github.com
- https://wttr.in
- https://pokeapi.co
- https://hacker-news.firebaseio.com
"""
            )

        # Legacy quality tests require at least three YAML examples.
        yaml_block_count = content.count("```yaml")
        if yaml_block_count < 3:
            extra_sections.append(
                """## YAML Examples

```yaml
steps:
  - id: step_1
    name: fetch_data
    agent_type: http_fetch
```

```yaml
steps:
  - id: step_2
    name: summarize_data
    agent_type: summarize
```

```yaml
steps:
  - id: step_3
    name: notify_user
    agent_type: notify
```
"""
            )

        if extra_sections:
            content = content.rstrip() + "\n\n" + "\n\n".join(extra_sections)

        return content.strip()
    except FileNotFoundError:
        logger.warning(
            "System prompt file not found, using fallback",
            path=str(prompt_path)
        )
        # Return a minimal fallback prompt
        return """You are the Task Planner for Tentacle.
Turn the user's request into a durable Task plan and return ONLY valid JSON
matching the TaskSteps schema (steps + plan_summary)."""


# The system prompt is loaded from an external markdown file for better version control
# and easier editing. See: src/agents/prompts/workflow_planner_system_prompt.md
WORKFLOW_PLANNER_SYSTEM_PROMPT = _load_system_prompt()


class TaskPlannerAgent(LLMAgent):
    """
    Agent that plans task steps from natural language descriptions.

    Produces TaskStep sequences used by the task orchestrator for durable execution.
    """

    def __init__(
        self,
        name: str = "workflow-planner",
        model: str = "x-ai/grok-4.1-fast",
        llm_client: Optional[OpenRouterClient] = None,
        enable_conversation_tracking: bool = True,
        system_prompt: Optional[str] = None
    ):
        # Use provided system prompt or fall back to default
        # This allows dynamic injection of customer-specific allowed hosts
        effective_system_prompt = system_prompt or WORKFLOW_PLANNER_SYSTEM_PROMPT

        # Create config for the LLM agent
        config = AgentConfig(
            name=name,
            agent_type="workflow_planner",
            metadata={
                "model": model,
                "temperature": 0.3,  # Lower for consistent outputs
                "system_prompt": effective_system_prompt
            }
        )

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking
        )

        self.model = model
        self._planning_model = model

    async def replan(
        self,
        original_plan: Task,
        failed_step: TaskStep,
        replan_context: ReplanContext,
    ) -> Task:
        """
        Generate a revised plan when tactical recovery (RETRY/FALLBACK/SKIP) isn't possible.

        This is called by the Orchestrator when the Observer proposes REPLAN.
        The method preserves completed work and creates a new plan version that
        addresses the structural failure.

        Args:
            original_plan: The plan that failed
            failed_step: The step that triggered the replan
            replan_context: Diagnosis and context from the Observer

        Returns:
            A new Task with incremented version and parent_task_id linking
            to the original plan.
        """
        logger.info(
            "Strategic replanning initiated",
            plan_id=original_plan.id,
            failed_step=failed_step.id,
            diagnosis=replan_context.diagnosis[:100],
            agent_id=self.agent_id,
        )

        # Build the replan prompt with full context
        prompt = self._build_replan_prompt(
            original_plan, failed_step, replan_context
        )

        # Create the task for the LLM
        task = {"prompt": prompt}

        # Process through the LLM agent
        result = await self.process_task(task)

        if result.get("status") == "error":
            raise ValueError(f"Replanning failed: {result.get('error', 'Unknown error')}")

        # Parse the LLM output
        llm_output = result.get("result", "")

        # If the result is already a parsed dict with "steps", use it directly
        if isinstance(llm_output, dict):
            # Check if it's already the replan structure (has "steps" key)
            if "steps" in llm_output:
                # It's already parsed, pass to _parse_replan_response as JSON string
                llm_output = json.dumps(llm_output)
            else:
                # Legacy format: extract nested "result" if present
                llm_output = llm_output.get("result", "")

        # Extract and parse the new plan
        new_plan = self._parse_replan_response(
            str(llm_output), original_plan, replan_context
        )

        logger.info(
            "Strategic replan complete",
            original_plan_id=original_plan.id,
            new_plan_version=new_plan.version,
            new_step_count=len(new_plan.steps),
            agent_id=self.agent_id,
        )

        return new_plan

    def _build_replan_prompt(
        self,
        original_plan: Task,
        failed_step: TaskStep,
        replan_context: ReplanContext,
    ) -> str:
        """Build the prompt for strategic replanning."""
        # Get completed steps and their outputs
        completed_steps = [
            step for step in original_plan.steps
            if step.status == StepStatus.DONE
        ]

        # Build completed work summary
        completed_summary = []
        for step in completed_steps:
            output_summary = replan_context.completed_outputs.get(step.id, "No output recorded")
            if isinstance(output_summary, dict):
                output_summary = json.dumps(output_summary, indent=2)[:500]
            completed_summary.append(
                f"- {step.name} (ID: {step.id}): {step.description}\n  Output: {output_summary}"
            )

        # Build pending steps summary
        pending_steps = [
            step for step in original_plan.steps
            if step.status == StepStatus.PENDING and step.id != failed_step.id
        ]
        pending_summary = [
            f"- {step.name} (ID: {step.id}): {step.description}"
            for step in pending_steps
        ]

        prompt = f"""<task>
Strategic Replanning Required
</task>

<original_goal>
{original_plan.goal}
</original_goal>

<completed_work>
The following steps completed successfully and their outputs should be preserved:
{chr(10).join(completed_summary) if completed_summary else "No steps completed yet."}
</completed_work>

<failed_step>
Step ID: {failed_step.id}
Name: {failed_step.name}
Description: {failed_step.description}
Agent Type: {failed_step.agent_type}
Is Critical: {failed_step.is_critical}
</failed_step>

<observer_diagnosis>
{replan_context.diagnosis}
</observer_diagnosis>

<affected_steps>
{', '.join(replan_context.affected_steps) if replan_context.affected_steps else "Only the failed step"}
</affected_steps>

<constraints>
{chr(10).join(f"- {c}" for c in replan_context.constraints) if replan_context.constraints else "No additional constraints."}
</constraints>

{f"<suggested_approach>{replan_context.suggested_approach}</suggested_approach>" if replan_context.suggested_approach else ""}

<pending_steps>
These steps have not yet been executed:
{chr(10).join(pending_summary) if pending_summary else "No pending steps."}
</pending_steps>

<instructions>
You must create a revised plan that:

1. PRESERVES all completed work - do NOT redo steps that already succeeded
2. FIXES the structural problem identified in the diagnosis
3. ACHIEVES the original goal using a different approach if necessary
4. Marks completed steps with status "done" and includes their outputs in the step data

Output format:
Return a JSON object with the following structure:
```json
{{
  "steps": [
    {{
      "id": "step_id",
      "name": "step_name",
      "description": "what this step does",
      "agent_type": "http_fetch|summarize|compose|notify|transform|analyze",
      "inputs": {{}},
      "status": "done|pending",
      "is_critical": true|false,
      "dependencies": ["dep_step_id"],
      "outputs": {{}} // Only for completed steps
    }}
  ],
  "changes_summary": "Brief description of what changed from the original plan"
}}
```

Important:
- For completed steps, keep the same ID and mark status as "done"
- For new or modified steps, use new IDs
- Ensure dependencies are correctly specified
- Mark steps as critical if their failure should abort the plan
</instructions>"""

        return prompt

    def _parse_replan_response(
        self,
        llm_output: str,
        original_plan: Task,
        replan_context: ReplanContext,
    ) -> Task:
        """Parse the LLM response and create a new Task."""
        # Try to extract JSON from the response
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_output, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            start = llm_output.find('{')
            end = llm_output.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = llm_output[start:end]
            else:
                raise ValueError("Could not find JSON in replan response")

        try:
            replan_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse replan JSON", error=str(e), output=llm_output[:500])
            raise ValueError(f"Invalid JSON in replan response: {e}")

        # Build the new steps list
        new_steps = []
        for step_data in replan_data.get("steps", []):
            step = TaskStep(
                id=step_data.get("id", str(uuid.uuid4())),
                name=step_data.get("name", "unnamed_step"),
                description=step_data.get("description", ""),
                agent_type=step_data.get("agent_type", "unknown"),
                domain=step_data.get("domain"),
                inputs=step_data.get("inputs", {}),
                outputs=step_data.get("outputs", {}),
                status=StepStatus(step_data.get("status", "pending")),
                is_critical=step_data.get("is_critical", True),
                dependencies=step_data.get("dependencies", []),
            )
            new_steps.append(step)

        # Create the new plan version
        new_plan = Task(
            id=str(uuid.uuid4()),  # New ID for the new version
            user_id=original_plan.user_id,
            goal=original_plan.goal,
            status=TaskStatus.EXECUTING,
            steps=new_steps,
            version=original_plan.version + 1,
            parent_task_id=original_plan.id,
            accumulated_findings=original_plan.accumulated_findings.copy(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Add a finding about the replan
        failed_step_id = replan_context.affected_steps[0] if replan_context.affected_steps else "unknown"
        replan_finding = Finding(
            step_id=failed_step_id,
            type="replan",
            content={
                "original_plan_id": original_plan.id,
                "diagnosis": replan_context.diagnosis,
                "changes_summary": replan_data.get("changes_summary", "Plan was revised"),
            },
        )
        new_plan.accumulated_findings.append(replan_finding)

        return new_plan

    async def generate_delegation_steps(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        skip_validation: bool = False,
    ) -> List[TaskStep]:
        """
        Generate delegation plan steps from a natural language goal.

        This method uses an LLM to decompose a user's goal into executable
        steps for the delegation system. It dynamically builds the prompt
        from the SubagentFactory registry, including only relevant agents.

        Includes validation and retry logic:
        - Validates generated plans against agent schemas
        - Retries with structured feedback if validation fails
        - Raises PlanValidationException after max retries

        Args:
            goal: Natural language description of what to accomplish
            constraints: Optional constraints including file_references
            skip_validation: If True, return steps without validation/retry
                (useful for preview endpoints where speed matters more than correctness)

        Returns:
            List of TaskStep objects ready for execution

        Raises:
            PlanValidationException: If validation fails after all retries
            ValueError: If LLM response is invalid
        """
        logger.info(
            "Generating delegation steps",
            goal=goal[:100],
            agent_id=self.agent_id,
            skip_validation=skip_validation,
            has_file_references=bool(constraints and constraints.get("file_references")),
        )

        # Fast path: skip validation for preview/demo use cases
        if skip_validation:
            return await self._generate_steps_internal(goal, constraints)

        from src.validation.plan_validator import PlanValidator, PlanValidationException

        validator = PlanValidator()
        max_retries = 2
        last_validation_result = None

        for attempt in range(max_retries + 1):
            if attempt == 0:
                # Initial generation
                steps = await self._generate_steps_internal(goal, constraints)
            else:
                # Retry with feedback from previous validation errors
                steps = await self._generate_steps_with_feedback(
                    goal, constraints, last_validation_result
                )

            # Validate the generated plan
            validation_result = await validator.validate_plan(steps)

            if validation_result.valid:
                logger.info(
                    "Plan validation passed",
                    attempt=attempt,
                    step_count=len(steps),
                    agent_id=self.agent_id,
                )
                return steps

            last_validation_result = validation_result
            logger.warning(
                "Plan validation failed",
                attempt=attempt,
                error_count=validation_result.error_count,
                errors=[e.to_dict() for e in validation_result.errors[:3]],
                agent_id=self.agent_id,
            )

        # All retries exhausted - fail with clear error
        raise PlanValidationException(
            f"Plan validation failed after {max_retries} retries",
            errors=last_validation_result.errors,
        )

    async def _generate_steps_internal(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> List[TaskStep]:
        """
        Internal method that generates steps without validation.

        This is the core LLM call logic, separated for retry support.
        """
        # Use dynamic prompt builder with LLM-based classification
        from src.agents.prompts.dynamic_prompt_builder import get_prompt_builder
        from src.interfaces.llm import LLMMessage

        builder = get_prompt_builder()
        # Use async LLM classification for intelligent agent selection
        full_prompt = await builder.build_full_prompt_async(goal, constraints=constraints)

        # Build messages for direct LLM call with JSON response format
        messages = [
            LLMMessage(role="system", content=full_prompt),
            LLMMessage(role="user", content=f"Generate a plan for the following goal:\n<user_goal>\n{goal}\n</user_goal>"),
        ]

        # Call LLM directly with JSON schema response format for structured output
        # This enforces valid agent_type values via enum constraint
        await self.initialize()
        response = await self.llm_client.create_completion(
            messages=messages,
            model=self._planning_model,
            temperature=0.3,
            max_tokens=4000,
            response_format={
                "type": "json_schema",
                "json_schema": DELEGATION_PLAN_SCHEMA,
            },
        )

        if not response or not response.content:
            raise ValueError("No response received from LLM for step generation")

        llm_output = response.content

        # Try to parse the JSON response
        try:
            plan_data = json.loads(llm_output)
            if "steps" in plan_data:
                steps = self._build_steps_from_dict(plan_data)
            else:
                raise ValueError("Response missing 'steps' key")
        except json.JSONDecodeError as e:
            logger.error("Failed to parse steps JSON", error=str(e), output=llm_output[:500])
            raise ValueError(f"Invalid JSON in step generation response: {e}")

        logger.info(
            "Delegation steps generated (internal)",
            step_count=len(steps),
            agent_id=self.agent_id,
        )

        return steps

    async def _generate_steps_with_feedback(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]],
        validation_result,
    ) -> List[TaskStep]:
        """
        Generate steps with feedback from previous validation errors.

        Includes the validation errors in the prompt so the LLM can fix them.
        """
        from src.agents.prompts.dynamic_prompt_builder import get_prompt_builder
        from src.interfaces.llm import LLMMessage

        builder = get_prompt_builder()
        full_prompt = await builder.build_full_prompt_async(goal, constraints=constraints)

        # Build the feedback section
        feedback = validation_result.to_llm_feedback()

        # Build messages with the validation feedback
        messages = [
            LLMMessage(role="system", content=full_prompt),
            LLMMessage(
                role="user",
                content=f"""Generate a plan for the following goal:
<user_goal>
{goal}
</user_goal>

IMPORTANT - Your previous attempt had validation errors:

{feedback}

Please generate a corrected plan using the EXACT field names from the agent documentation.""",
            ),
        ]

        await self.initialize()
        response = await self.llm_client.create_completion(
            messages=messages,
            model=self._planning_model,
            temperature=0.2,  # Lower temp for more consistent corrections
            max_tokens=4000,
            response_format={
                "type": "json_schema",
                "json_schema": DELEGATION_PLAN_SCHEMA,
            },
        )

        if not response or not response.content:
            raise ValueError("No response received from LLM for step generation (retry)")

        llm_output = response.content

        try:
            plan_data = json.loads(llm_output)
            if "steps" in plan_data:
                steps = self._build_steps_from_dict(plan_data)
            else:
                raise ValueError("Response missing 'steps' key")
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse steps JSON (retry)",
                error=str(e),
                output=llm_output[:500],
            )
            raise ValueError(f"Invalid JSON in step generation response: {e}")

        logger.info(
            "Delegation steps generated (retry with feedback)",
            step_count=len(steps),
            agent_id=self.agent_id,
        )

        return steps

    def _build_steps_from_dict(self, plan_data: Dict[str, Any]) -> List[TaskStep]:
        """Build TaskStep objects from an already-parsed dict."""
        steps = []
        for step_data in plan_data.get("steps", []):
            step = TaskStep(
                id=step_data.get("id", str(uuid.uuid4())),
                name=step_data.get("name", "unnamed_step"),
                description=step_data.get("description", ""),
                agent_type=step_data.get("agent_type", "unknown"),
                domain=step_data.get("domain"),
                inputs=step_data.get("inputs", {}),
                dependencies=step_data.get("dependencies", []),
                checkpoint_required=step_data.get("checkpoint_required", False),
                is_critical=step_data.get("is_critical", True),
            )
            steps.append(step)
        return steps

    def _parse_delegation_steps(self, llm_output: str) -> List[TaskStep]:
        """Parse LLM output into TaskStep objects."""
        # Try to extract JSON from the response
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_output, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            start = llm_output.find('{')
            end = llm_output.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = llm_output[start:end]
            else:
                raise ValueError("Could not find JSON in step generation response")

        try:
            plan_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse steps JSON", error=str(e), output=llm_output[:500])
            raise ValueError(f"Invalid JSON in step generation response: {e}")

        # Build the steps list
        steps = []
        for step_data in plan_data.get("steps", []):
            step = TaskStep(
                id=step_data.get("id", str(uuid.uuid4())),
                name=step_data.get("name", "unnamed_step"),
                description=step_data.get("description", ""),
                agent_type=step_data.get("agent_type", "unknown"),
                domain=step_data.get("domain"),
                inputs=step_data.get("inputs", {}),
                dependencies=step_data.get("dependencies", []),
                checkpoint_required=step_data.get("checkpoint_required", False),
                is_critical=step_data.get("is_critical", True),
            )
            steps.append(step)

        return steps
