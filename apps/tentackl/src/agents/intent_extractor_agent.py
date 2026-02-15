"""
# REVIEW:
# - Large prompt hard-coded here; not versioned or configurable.
# - LLM output parsing falls back to regex extraction; can be brittle and silently accept partial JSON.

Intent Extractor Agent

Fast, lightweight agent that uses Claude Haiku to extract task intent
from natural language. Designed for speed (~300-500ms) to provide immediate
feedback before full plan generation.

This is Phase 1 of the two-phase planning approach:
1. Intent extraction (this agent) - fast, shows user what we understood
2. Plan generation (TaskPlannerAgent) - slower, produces TaskSteps JSON
"""

import json
from typing import Dict, Any, Optional
import structlog

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.llm.openrouter_client import OpenRouterClient
from src.llm.model_selector import ModelSelector, TaskType

logger = structlog.get_logger(__name__)


INTENT_SYSTEM_PROMPT = """You extract task intent from user requests. Be fast and concise.

Output ONLY valid JSON (no markdown, no explanation):
{
  "intent_type": "data_retrieval|workflow|scheduling",
  "rephrased_intent": "Clear 1-2 sentence description of what user wants to accomplish",
  "one_shot_goal": "The core action WITHOUT any scheduling/frequency language (e.g. 'Check the weather for Walnut Creek' instead of 'Check the weather for Walnut Creek every 5 minutes'). Only set when has_schedule=true, otherwise null.",
  "workflow_steps": ["step1_verb_noun", "step2_verb_noun", "step3_verb_noun"],
  "has_loops": true/false,
  "requires_user_input": true/false,
  "complexity": "simple|medium|complex",
  "apis_needed": ["api_name1", "api_name2"],
  "has_schedule": true/false,
  "schedule": {"cron": "0 9 * * *", "timezone": "UTC", "execute_at": null} or null,
  "data_query": {
    "object_type": "event|contact|<custom_type>",
    "date_range": {"start": "ISO8601", "end": "ISO8601"} or null,
    "search_text": "string" or null,
    "where": {"field": {"$op": "value"}} or null,
    "limit": 100,
    "order_by": "field" or null
  } or null
}

Rules for intent_type:
- "data_retrieval": Simple queries to get/list/show/find/fetch existing data from workspace
  Examples: "get events today", "show contacts", "list meetings this week", "find events about standup"
- "workflow": Complex operations requiring LLM processing (summarize, analyze, create, compare, research)
  Examples: "summarize HN stories", "analyze calendar", "create report", "research competitors"
- "scheduling": Recurring OR one-time scheduled tasks (has schedule trigger)
  Examples: "every day fetch news", "daily at 9am send digest", "search AI news in 5 minutes", "run this at 3pm today"

Rules for data_query (ONLY for data_retrieval intent):
- object_type: The type of object to query (event, contact, or custom type)
- date_range: For time-based queries like "today", "this week", "yesterday":
  - "today" -> start/end of current day in ISO8601 format
  - "this week" -> start of week (Monday) to end of week (Sunday)
  - "yesterday" -> start/end of yesterday
  - Use relative dates from user's perspective
- search_text: Keywords to search for (for queries like "find events about standup")
- where: MongoDB-style query operators for filtering ($eq, $gt, $lt, $gte, $lte, $in, $contains)
- limit: Max results (default 100)
- order_by: Field to sort by (e.g., "data.start_time", "created_at")

Other rules:
- workflow_steps should be 2-5 short step names (verb_noun format like "fetch_data", "analyze_results")
- has_loops is true if the workflow needs to iterate over data (for_each)
- requires_user_input is true if the workflow needs parameters like city name, repo URL, etc.
- complexity: simple=2 nodes, medium=3-4 nodes, complex=5+ nodes
- apis_needed: list short API names (hackernews, github, weather, pokemon, etc.)
- has_schedule is true if user mentions: "every day", "daily", "weekly", "every morning", "at 9am", "every hour", "in 5 minutes", "in an hour", "at 3pm today", "tomorrow at noon", etc.
- schedule: Extract cron expression OR execute_at for one-time scheduling. Examples:
  Recurring (use cron, execute_at=null):
  - "every morning at 9am" -> {"cron": "0 9 * * *", "timezone": "UTC", "execute_at": null}
  - "every Monday at 10am" -> {"cron": "0 10 * * 1", "timezone": "UTC", "execute_at": null}
  - "daily at noon" -> {"cron": "0 12 * * *", "timezone": "UTC", "execute_at": null}
  - "every hour" -> {"cron": "0 * * * *", "timezone": "UTC", "execute_at": null}
  - "weekdays at 8am EST" -> {"cron": "0 8 * * 1-5", "timezone": "America/New_York", "execute_at": null}
  One-time (use execute_at as ISO8601 offset from now, cron=null):
  - "in 3 minutes" -> {"cron": null, "timezone": "UTC", "execute_at": "+3m"}
  - "in 1 hour" -> {"cron": null, "timezone": "UTC", "execute_at": "+1h"}
  - "in 30 seconds" -> {"cron": null, "timezone": "UTC", "execute_at": "+30s"}
  - "in 2 hours and 30 minutes" -> {"cron": null, "timezone": "UTC", "execute_at": "+150m"}
  For execute_at, use relative offset format: +Nm (minutes), +Nh (hours), +Ns (seconds).
  If no scheduling mentioned, set has_schedule=false and schedule=null

IMPORTANT: Output ONLY the JSON object. No other text."""


class IntentExtractorAgent(LLMAgent):
    """
    Fast intent extraction agent using Claude Haiku.

    Designed for speed - uses the fastest available model to provide
    immediate feedback about what the user wants to accomplish.
    """

    def __init__(
        self,
        name: str = "intent-extractor",
        model: Optional[str] = None,  # If None, uses ModelSelector.QUICK_RESPONSE
        llm_client: Optional[OpenRouterClient] = None,
    ):
        # Use ModelSelector for optimal model selection
        if model is None:
            routing = ModelSelector.get_routing(TaskType.QUICK_RESPONSE)
            model = routing.models[0]  # Use first model from QUICK_RESPONSE config
            logger.debug(
                "Using ModelSelector for intent extraction",
                task_type="QUICK_RESPONSE",
                model=model,
            )

        config = AgentConfig(
            name=name,
            agent_type="intent_extractor",
            metadata={
                "model": model,
                "temperature": 0.1,  # Very low for consistent output
                "max_tokens": 500,   # Short responses only
                "system_prompt": INTENT_SYSTEM_PROMPT
            }
        )

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=False  # No need to track conversation
        )

        self.model = model

    async def extract_intent(self, user_prompt: str) -> Dict[str, Any]:
        """
        Extract intent from user prompt.

        Args:
            user_prompt: Natural language description of what user wants

        Returns:
            Dict with:
                - rephrased_intent: Human-readable interpretation
                - workflow_steps: List of step names
                - has_loops: Whether iteration is needed
                - requires_user_input: Whether parameters are needed
                - complexity: simple/medium/complex
                - apis_needed: List of API names
        """
        logger.info(
            "Extracting intent",
            prompt_length=len(user_prompt),
            agent_id=self.agent_id
        )

        task = {
            "prompt": user_prompt
        }

        result = await self.process_task(task)

        if result.get("status") == "error":
            raise ValueError(f"Intent extraction failed: {result.get('error', 'Unknown error')}")

        # Parse the LLM output
        llm_output = result.get("result", "")

        # If llm_output is already a dict with expected keys, use it directly
        if isinstance(llm_output, dict) and "rephrased_intent" in llm_output:
            intent_data = llm_output
        else:
            # Extract JSON from response string
            intent_data = self._parse_intent_json(str(llm_output))

        logger.info(
            "Intent extracted",
            intent_type=intent_data.get("intent_type"),
            complexity=intent_data.get("complexity"),
            step_count=len(intent_data.get("workflow_steps", [])),
            has_schedule=intent_data.get("has_schedule", False),
            has_data_query=intent_data.get("data_query") is not None,
            agent_id=self.agent_id
        )

        return intent_data

    def _parse_intent_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        content = content.strip()

        # Try to find JSON in the response
        import re

        # Remove markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        # Try to find raw JSON object
        if not content.startswith('{'):
            brace_start = content.find('{')
            if brace_start != -1:
                # Find matching closing brace
                depth = 0
                for i, char in enumerate(content[brace_start:]):
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            content = content[brace_start:brace_start + i + 1]
                            break

        try:
            data = json.loads(content)

            # Validate and provide defaults
            return {
                "intent_type": data.get("intent_type", "workflow"),
                "rephrased_intent": data.get("rephrased_intent", "Unable to parse intent"),
                "workflow_steps": data.get("workflow_steps", ["unknown_step"]),
                "has_loops": data.get("has_loops", False),
                "requires_user_input": data.get("requires_user_input", False),
                "complexity": data.get("complexity", "medium"),
                "apis_needed": data.get("apis_needed", []),
                "has_schedule": data.get("has_schedule", False),
                "schedule": data.get("schedule"),
                "data_query": data.get("data_query"),
            }
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse intent JSON, using defaults",
                error=str(e),
                content=content[:200]
            )
            return {
                "intent_type": "workflow",
                "rephrased_intent": "Process user request",
                "workflow_steps": ["process_request"],
                "has_loops": False,
                "requires_user_input": False,
                "complexity": "simple",
                "apis_needed": [],
                "has_schedule": False,
                "schedule": None,
                "data_query": None,
            }

    def estimate_planning_time(self, complexity: str, has_loops: bool) -> int:
        """
        Estimate how long plan generation will take.

        Args:
            complexity: simple/medium/complex
            has_loops: Whether workflow has iterations

        Returns:
            Estimated time in milliseconds
        """
        base_times = {
            "simple": 2000,
            "medium": 4000,
            "complex": 7000
        }

        time_ms = base_times.get(complexity, 4000)

        if has_loops:
            time_ms += 1500  # Loops add complexity

        return time_ms
