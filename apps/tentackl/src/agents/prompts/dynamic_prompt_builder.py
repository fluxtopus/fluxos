"""
Dynamic Prompt Builder for Delegation Planning

Generates prompts dynamically from the SubagentFactory registry,
avoiding the need for manually maintained prompt files that can drift
out of sync with actual capabilities.

Two-stage LLM approach:
1. Stage 1 (Goal Classification): Fast LLM classifies intent and selects agents
2. Stage 2 (Plan Generation): Full planning with selected agent documentation
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import json
import structlog

logger = structlog.get_logger(__name__)

# Prompt file directory
PROMPTS_DIR = Path(__file__).parent

# JSON Schema for goal classification - enforces structured output
GOAL_CLASSIFICATION_SCHEMA = {
    "name": "goal_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "required": ["task_type", "needs_external_info", "info_gathering_method", "agent_categories", "reasoning"],
        "additionalProperties": False,
        "properties": {
            "task_type": {
                "type": "string",
                "description": "Primary task type",
            },
            "needs_external_info": {
                "type": "boolean",
                "description": "Whether external information gathering is needed",
            },
            "info_gathering_method": {
                "type": "string",
                "description": "Method for gathering info: web_research, http_fetch, or none",
            },
            "agent_categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of agent category/domain names from the registry",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the classification",
            },
        },
    },
}


def _load_prompt(filename: str) -> str:
    """Load prompt content from a markdown file."""
    prompt_path = PROMPTS_DIR / filename
    return prompt_path.read_text()


# Domain descriptions for the goal classifier
# These describe WHEN to use each domain, not which agents are in them
DOMAIN_DESCRIPTIONS = {
    "research": "for gathering information from the web",
    "content": "for processing, analyzing, and creating content",
    "workspace": "for calendar events, contacts, and workspace data (DEFAULT for calendar)",
    "scheduling": "for scheduled/recurring tasks",
    "support": "for notifications and communication",
    "google": "ONLY for explicit Google integrations (user says 'Google Calendar', 'Gmail')",
    "cms": "for publishing content",
    "analytics": "for data analysis",
    "strategy": "for strategic planning",
    "finance": "for financial analysis",
    "file_io": "for saving documents, stories, reports, and generated content as files in workspace",
    "integration": "for sending messages to external services (Discord, Slack, X/Twitter, GitHub, etc.) via configured integrations",
    "memory": "for storing and retrieving organizational knowledge across tasks",
}

# Deterministic fallback metadata for core agents expected by planner/tests.
_FALLBACK_AGENT_METADATA: Dict[str, Dict[str, Any]] = {
    "summarize": {
        "agent_type": "summarize",
        "brief": "Summarize long content into concise key points.",
        "category": "content",
        "keywords": ["summarize", "summary"],
        "inputs_schema": {"text": {"type": "string", "description": "Content to summarize", "required": True}},
        "outputs_schema": {"summary": {"type": "string", "description": "Summary result"}},
        "example_use_cases": ["Summarize research notes"],
        "requires_checkpoint": False,
    },
    "analyze": {
        "agent_type": "analyze",
        "brief": "Analyze inputs and extract structured insights.",
        "category": "content",
        "keywords": ["analyze", "analysis"],
        "inputs_schema": {"data": {"type": "object", "description": "Data to analyze", "required": True}},
        "outputs_schema": {"insights": {"type": "array", "description": "Key insights"}},
        "example_use_cases": ["Analyze trends in records"],
        "requires_checkpoint": False,
    },
    "compose": {
        "agent_type": "compose",
        "brief": "Compose polished text from structured inputs.",
        "category": "content",
        "keywords": ["compose", "write"],
        "inputs_schema": {"instructions": {"type": "string", "description": "Writing instructions", "required": True}},
        "outputs_schema": {"content": {"type": "string", "description": "Generated content"}},
        "example_use_cases": ["Draft a report"],
        "requires_checkpoint": False,
    },
    "web_research": {
        "agent_type": "web_research",
        "brief": "Gather and synthesize information from the web.",
        "category": "research",
        "keywords": ["research", "web"],
        "inputs_schema": {"query": {"type": "string", "description": "Research query", "required": True}},
        "outputs_schema": {"findings": {"type": "array", "description": "Collected findings"}},
        "example_use_cases": ["Research a new topic"],
        "requires_checkpoint": False,
    },
    "file_storage": {
        "agent_type": "file_storage",
        "brief": "Save files and artifacts to workspace storage.",
        "category": "file_io",
        "keywords": ["file", "storage"],
        "inputs_schema": {"content": {"type": "string", "description": "File content", "required": True}},
        "outputs_schema": {"file_path": {"type": "string", "description": "Stored file path"}},
        "example_use_cases": ["Store generated report"],
        "requires_checkpoint": False,
    },
    "http_fetch": {
        "agent_type": "http_fetch",
        "brief": "Fetch raw content from HTTP endpoints.",
        "category": "research",
        "keywords": ["http", "fetch"],
        "inputs_schema": {"url": {"type": "string", "description": "URL to fetch", "required": True}},
        "outputs_schema": {"body": {"type": "string", "description": "Fetched content"}},
        "example_use_cases": ["Fetch data from an API endpoint"],
        "requires_checkpoint": False,
    },
    "list_integrations": {
        "agent_type": "list_integrations",
        "brief": "List user integrations available for outbound actions.",
        "category": "integration",
        "keywords": ["integrations", "list"],
        "inputs_schema": {"user_token": {"type": "string", "description": "Auth token", "required": True}},
        "outputs_schema": {"integrations": {"type": "array", "description": "Configured integrations"}},
        "example_use_cases": ["Discover available integrations"],
        "requires_checkpoint": False,
    },
    "execute_outbound_action": {
        "agent_type": "execute_outbound_action",
        "brief": "Send outbound messages/actions through an integration.",
        "category": "integration",
        "keywords": ["integration", "outbound"],
        "inputs_schema": {
            "integration_id": {"type": "string", "description": "Integration id", "required": True},
            "action_type": {"type": "string", "description": "Action to perform", "required": True},
        },
        "outputs_schema": {"result": {"type": "object", "description": "Action result"}},
        "example_use_cases": ["Send a Slack notification"],
        "requires_checkpoint": False,
    },
}


class DynamicPromptBuilder:
    """
    Builds delegation planning prompts dynamically from agent metadata.

    Uses a two-stage LLM approach:
    1. Fast classifier LLM determines intent and selects agent categories
    2. Main planner LLM generates the detailed plan

    This is more robust than keyword matching and adapts to natural language.
    """

    # NOTE: Category-to-agent mapping is now built dynamically from the registry
    # in agents_from_classification(). Each agent's "domain" field in the DB
    # determines its category. This ensures the registry is the single source of truth.

    def __init__(self):
        self._registry = None
        self._agent_metadata: Dict[str, Dict[str, Any]] = {}

    def _build_dynamic_agent_categories(self) -> str:
        """
        Build the agent categories section dynamically from the registry.

        This ensures the goal classifier always has accurate, up-to-date
        information about which agents exist in each domain.
        """
        self._load_registry()

        # Group agents by domain
        by_domain: Dict[str, List[str]] = {}
        for agent_type, meta in self._agent_metadata.items():
            domain = meta.get("category", "general")
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(agent_type)

        # Build the section
        lines = []
        for domain in sorted(by_domain.keys()):
            agents = sorted(by_domain[domain])
            description = DOMAIN_DESCRIPTIONS.get(domain, f"for {domain} tasks")
            lines.append(f"- **{domain}**: {', '.join(agents)} - {description}")

        return "\n".join(lines)

    async def classify_goal_with_llm(self, goal: str) -> Dict[str, Any]:
        """
        Use a fast LLM to classify the goal and determine agent selection.

        This replaces keyword matching with intelligent classification.

        Args:
            goal: The user's natural language goal

        Returns:
            Classification result with task_type, agent categories, etc.
        """
        from src.interfaces.llm import LLMMessage
        from src.llm.openrouter_client import OpenRouterClient

        # Load template and inject dynamic agent categories
        classifier_template = _load_prompt("goal_classifier_prompt.md")
        dynamic_categories = self._build_dynamic_agent_categories()
        classifier_prompt = classifier_template.replace(
            "{{DYNAMIC_AGENT_CATEGORIES}}", dynamic_categories
        )
        messages = [
            LLMMessage(role="system", content=classifier_prompt),
            LLMMessage(role="user", content=f"Classify this goal: {goal}"),
        ]

        try:
            # Use OpenRouterClient as async context manager
            async with OpenRouterClient() as client:
                response = await client.create_completion(
                    messages=messages,
                    model="x-ai/grok-3-mini",  # Fast xAI model for classification
                    temperature=0.1,  # Low temp for consistent classification
                    max_tokens=500,
                    response_format={
                        "type": "json_schema",
                        "json_schema": GOAL_CLASSIFICATION_SCHEMA,
                    },
                )

                if response and response.content:
                    result = json.loads(response.content)
                    logger.info(
                        "LLM classified goal",
                        goal_preview=goal[:50],
                        task_type=result.get("task_type"),
                        info_method=result.get("info_gathering_method"),
                        categories=result.get("agent_categories"),
                    )
                    return result

        except Exception as e:
            logger.warning(
                "LLM classification failed, using fallback",
                error=str(e),
                goal_preview=goal[:50],
            )

        # Fallback to safe defaults using registry domain names
        return {
            "task_type": "research",
            "needs_external_info": True,
            "info_gathering_method": "web_research",
            "agent_categories": ["research", "content", "support"],
            "reasoning": "Fallback classification - defaulting to research with web_research",
        }

    def agents_from_classification(self, classification: Dict[str, Any]) -> List[str]:
        """
        Convert LLM classification result into list of agent types.

        Uses agent categories/domains from the registry (single source of truth)
        rather than hardcoded mappings.

        Args:
            classification: Result from classify_goal_with_llm

        Returns:
            List of agent types to include in the prompt
        """
        self._load_registry()
        agents = set()

        # Handle information gathering FIRST and EXPLICITLY
        info_method = classification.get("info_gathering_method", "web_research")

        if info_method == "web_research":
            # CRITICAL: Always add web_research for research tasks
            agents.add("web_research")
            # CRITICAL: Do NOT add http_fetch - forces LLM to use web_research
        elif info_method == "http_fetch":
            agents.add("http_fetch")
        # If "none", neither is added

        # Build dynamic category-to-agents mapping from registry
        # This replaces the hardcoded CATEGORY_TO_AGENTS
        category_to_agents: Dict[str, List[str]] = {}
        for agent_type, meta in self._agent_metadata.items():
            category = meta.get("category", "general")
            if category not in category_to_agents:
                category_to_agents[category] = []
            category_to_agents[category].append(agent_type)

        # Add agents based on categories from classification
        for category in classification.get("agent_categories", []):
            if category == "information_gathering":
                continue  # Already handled above
            # Look up agents by category from registry (dynamic)
            category_agents = category_to_agents.get(category, [])
            agents.update(category_agents)

        # Always include common content utilities if they exist
        for common_agent in ["summarize", "analyze", "compose"]:
            if common_agent in self._agent_metadata:
                agents.add(common_agent)

        # Filter to only agents that exist in registry
        valid_agents = [a for a in agents if a in self._agent_metadata]

        logger.info(
            "Selected agents from classification",
            classification_type=classification.get("task_type"),
            info_method=info_method,
            requested_categories=classification.get("agent_categories", []),
            all_agents=list(agents),
            valid_agents=valid_agents,
        )

        return valid_agents

    def _load_registry(self) -> None:
        """Load agents from UnifiedCapabilityRegistry (DB-backed, single source of truth)."""
        if self._registry is not None:
            return

        import asyncio
        from src.capabilities.unified_registry import get_registry

        async def _load_from_unified():
            registry = await get_registry()
            return registry.list_agents(), registry.list_plugins()

        agents = []
        plugins = []

        # Handle both sync and async contexts properly. If the unified registry
        # can't be loaded (e.g., DB not migrated/available), fall back to a
        # deterministic in-memory set so unit tests and local usage still work.
        try:
            try:
                # Check if we're in an async context
                asyncio.get_running_loop()
                # We're in async context - use thread to avoid blocking
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _load_from_unified())
                    agents, plugins = future.result()
            except RuntimeError:
                # No running loop - safe to use asyncio.run directly
                agents, plugins = asyncio.run(_load_from_unified())
        except Exception as e:
            logger.warning(
                "Failed to load UnifiedCapabilityRegistry; using fallback metadata",
                error=str(e),
            )

        self._registry = {}
        for agent in agents:
            agent_type = agent["agent_type"]
            self._registry[agent_type] = agent  # Store metadata directly
            self._agent_metadata[agent_type] = {
                "agent_type": agent_type,
                "brief": agent.get("description", "").split("\n")[0] if agent.get("description") else f"{agent_type} agent",
                "category": agent.get("domain", "general"),
                "keywords": [agent_type.replace("_", " ")],
                "inputs_schema": agent.get("inputs_schema", {}),
                "outputs_schema": agent.get("outputs_schema", {}),
                "example_use_cases": agent.get("examples", []),
                "requires_checkpoint": agent.get("requires_checkpoint", False),
            }

        # Also load plugins that have rich metadata (inputs/outputs schemas)
        # so the planner can discover capabilities like generate_image, file_storage, etc.
        for plugin in plugins:
            ns = plugin["namespace"]
            if ns in self._agent_metadata:
                continue  # Agent takes precedence over plugin with same name
            config = plugin.get("config") or {}
            # Only include plugins with schema info — those from PluginRegistry
            # have category + inputs/outputs. PLUGIN_REGISTRY-only entries just
            # have module/handler and lack the metadata the planner needs.
            if not config.get("inputs_schema"):
                continue
            self._registry[ns] = {
                "agent_type": ns,
                "description": plugin.get("description", ""),
                "domain": config.get("category", "plugin"),
                "inputs_schema": config.get("inputs_schema", {}),
                "outputs_schema": config.get("outputs_schema", {}),
            }
            self._agent_metadata[ns] = {
                "agent_type": ns,
                "brief": (plugin.get("description") or "").split("\n")[0] or f"{ns} plugin",
                "category": config.get("category", "plugin"),
                "keywords": [ns.replace("_", " ")],
                "inputs_schema": config.get("inputs_schema", {}),
                "outputs_schema": config.get("outputs_schema", {}),
                "example_use_cases": [],
                "requires_checkpoint": False,
            }

        # Ensure a stable core metadata set even when DB registry is sparse.
        for agent_type, fallback in _FALLBACK_AGENT_METADATA.items():
            if agent_type not in self._agent_metadata:
                self._agent_metadata[agent_type] = dict(fallback)
                self._registry[agent_type] = {
                    "agent_type": agent_type,
                    "description": fallback["brief"],
                    "domain": fallback["category"],
                    "inputs_schema": fallback["inputs_schema"],
                    "outputs_schema": fallback["outputs_schema"],
                }

        logger.info(
            "Loaded agents from UnifiedCapabilityRegistry",
            agent_count=len(self._agent_metadata),
            agent_types=list(self._agent_metadata.keys()),
        )

    def get_all_agent_types(self) -> List[str]:
        """Get list of all registered agent types."""
        self._load_registry()
        return list(self._agent_metadata.keys())

    def get_agent_metadata(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific agent type."""
        self._load_registry()
        return self._agent_metadata.get(agent_type)

    def build_brief_agent_list(self) -> str:
        """
        Build Stage 1 prompt section with brief agent descriptions.

        This is always included and provides minimal context for
        the LLM to understand available capabilities.
        """
        self._load_registry()

        lines = ["## Available Agent Types\n"]

        # Group by category
        by_category: Dict[str, List[tuple]] = {}
        for agent_type, meta in self._agent_metadata.items():
            category = meta.get("category", "uncategorized")
            if category not in by_category:
                by_category[category] = []
            by_category[category].append((agent_type, meta))

        for category, agents in sorted(by_category.items()):
            lines.append(f"### {category.replace('_', ' ').title()}")
            for agent_type, meta in agents:
                brief = meta.get("brief", "No description")
                checkpoint = " ⚠️ requires approval" if meta.get("requires_checkpoint") else ""
                lines.append(f"- **{agent_type}**: {brief}{checkpoint}")
            lines.append("")

        return "\n".join(lines)

    def build_detailed_agent_docs(self, agent_types: List[str]) -> str:
        """
        Build Stage 2 prompt section with full documentation for selected agents.

        Args:
            agent_types: List of agent types to include full docs for

        Returns:
            Detailed documentation for the specified agents
        """
        self._load_registry()

        lines = [
            "## Detailed Agent Documentation",
            "",
            "**CRITICAL: Use EXACT field names from this documentation.**",
            "- Input field names must match exactly (e.g., use `data` not `events`)",
            "- Output field names must match exactly (e.g., use `results` not `search_results`)",
            "- Template syntax: `{{step_X.outputs.<field_name>}}`",
            "",
        ]

        for agent_type in agent_types:
            meta = self._agent_metadata.get(agent_type)
            if not meta:
                continue

            lines.append(f"### {agent_type}")
            lines.append(f"**{meta.get('brief', 'No description')}**\n")

            # Inputs - with REQUIRED prominently marked
            inputs_schema = meta.get("inputs_schema", {})
            if inputs_schema:
                # Normalize JSON Schema format: if schema has "properties" key,
                # use the properties dict and check top-level "required" array
                if "properties" in inputs_schema and isinstance(inputs_schema.get("properties"), dict):
                    schema_required = inputs_schema.get("required", [])
                    field_map = {}
                    for param, spec in inputs_schema["properties"].items():
                        field_spec = dict(spec) if isinstance(spec, dict) else {"type": str(spec)}
                        if param in schema_required:
                            field_spec["required"] = True
                        field_map[param] = field_spec
                    inputs_schema = field_map

                # Separate required and optional for clarity
                required_inputs = []
                optional_inputs = []
                for param, spec in inputs_schema.items():
                    if not isinstance(spec, dict):
                        continue
                    if spec.get("required"):
                        required_inputs.append((param, spec))
                    else:
                        optional_inputs.append((param, spec))

                lines.append("**Inputs:**")
                # Required inputs first, clearly marked
                for param, spec in required_inputs:
                    desc = spec.get("description", "")
                    field_type = spec.get("type", "any")
                    lines.append(f"- `{param}` ({field_type}) **(REQUIRED)**: {desc}")

                # Optional inputs
                for param, spec in optional_inputs:
                    desc = spec.get("description", "")
                    field_type = spec.get("type", "any")
                    default = f", default: {spec['default']}" if "default" in spec else ""
                    lines.append(f"- `{param}` ({field_type}, optional): {desc}{default}")
                lines.append("")

            # Outputs - critical for correct step chaining
            outputs_schema = meta.get("outputs_schema", {})
            if outputs_schema:
                # Normalize JSON Schema format for outputs too
                if "properties" in outputs_schema and isinstance(outputs_schema.get("properties"), dict):
                    outputs_schema = outputs_schema["properties"]

                output_fields = list(outputs_schema.keys())
                lines.append(f"**Outputs** (valid field names: `{', '.join(output_fields)}`):")
                for field, spec in outputs_schema.items():
                    if not isinstance(spec, dict):
                        continue
                    field_type = spec.get("type", "any")
                    desc = spec.get("description", "")
                    lines.append(f"- `{field}` ({field_type}): {desc}")

                # Add template example
                if output_fields:
                    example_field = output_fields[0]
                    lines.append(f"  - Template example: `{{{{step_X.outputs.{example_field}}}}}`")
                lines.append("")

            # Use cases
            use_cases = meta.get("example_use_cases", [])
            if use_cases:
                lines.append("**Use for:**")
                for case in use_cases:
                    lines.append(f"- {case}")
                lines.append("")

            # Checkpoint note
            if meta.get("requires_checkpoint"):
                lines.append("⚠️ **NOTE**: Always requires checkpoint for user approval\n")

        return "\n".join(lines)

    async def build_full_prompt_async(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build the complete delegation planning prompt using LLM classification.

        This is the preferred method - uses an LLM to intelligently classify
        the goal and select appropriate agents.

        Args:
            goal: The user's natural language goal
            constraints: Optional constraints including file_references, user_token

        Returns:
            Complete prompt string
        """
        # Use LLM to classify goal and select agents
        classification = await self.classify_goal_with_llm(goal)
        agents_to_detail = self.agents_from_classification(classification)

        # Fetch user integrations if we have a token
        integrations = []
        if constraints and constraints.get("user_token"):
            integrations = await self._fetch_user_integrations(constraints["user_token"])
            # If user has integrations, ensure integration plugins are in the agent list
            if integrations:
                for plugin in ["list_integrations", "execute_outbound_action"]:
                    if plugin not in agents_to_detail:
                        agents_to_detail.append(plugin)

        logger.info(
            "Building LLM-classified prompt",
            goal_preview=goal[:50],
            task_type=classification.get("task_type"),
            agents_included=agents_to_detail,
            integrations_count=len(integrations),
        )

        return self._build_prompt_sections(goal, agents_to_detail, constraints, classification, integrations)

    def _build_prompt_sections(
        self,
        goal: str,
        agents_to_detail: List[str],
        constraints: Optional[Dict[str, Any]] = None,
        classification: Optional[Dict[str, Any]] = None,
        integrations: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build the actual prompt sections by injecting dynamic content into placeholders."""
        self._load_registry()

        # Load the plan generator prompt template
        plan_generator_prompt = _load_prompt("plan_generator_prompt.md")

        # Inject dynamic content into placeholders
        # This keeps all agent information dynamic from the registry
        plan_generator_prompt = plan_generator_prompt.replace(
            "{{AVAILABLE_AGENTS}}", self.build_brief_agent_list()
        )
        plan_generator_prompt = plan_generator_prompt.replace(
            "{{AGENT_DOCUMENTATION}}", self.build_detailed_agent_docs(agents_to_detail)
        )

        # Build the final prompt
        sections = [plan_generator_prompt]

        # Add file references context if provided
        if constraints and constraints.get("file_references"):
            sections.extend(self._build_file_references_section(constraints["file_references"]))

        # Add integrations context if available
        if integrations:
            sections.extend(self._build_integrations_section(integrations))

        sections.extend([
            "",
            "Now generate a plan for the following goal:",
            "",
            f"Goal: {goal}",
        ])

        return "\n".join(sections)

    def _build_file_references_section(self, file_references: List[Dict[str, Any]]) -> List[str]:
        """
        Build the section explaining available file references.

        Referenced files are automatically downloaded and injected into each
        LLM step at runtime — no separate download step is needed.

        Args:
            file_references: List of file reference dicts with id, name, path, content_type

        Returns:
            List of prompt lines for file references
        """
        lines = [
            "## Available File References",
            "",
            "The user has referenced the following files from their storage:",
            "",
        ]

        for ref in file_references:
            name = ref.get("name", "unknown")
            content_type = ref.get("content_type", "unknown")
            lines.append(f"- **{name}** (type: `{content_type}`)")

        lines.extend([
            "",
            "**File access:**",
            "- Referenced files are automatically downloaded and injected into each LLM step.",
            "- You do NOT need to create a separate download step.",
            "- Image files will be sent as vision attachments to LLM agents.",
            "- Text/CSV/JSON files will be inlined into the agent's prompt.",
            "- Simply reference the file by name in your step descriptions.",
            "",
            "**IMPORTANT**: The user expects you to use these referenced files. "
            "Reference them by name in the relevant step's goal or description.",
            "",
        ])

        return lines

    async def _fetch_user_integrations(self, user_token: str) -> List[Dict[str, Any]]:
        """
        Fetch the user's configured integrations from Mimic.

        Args:
            user_token: Bearer token for authentication

        Returns:
            List of integration dicts, or empty list on failure
        """
        try:
            from src.application.integrations import IntegrationUseCases
            from src.infrastructure.integrations import MimicIntegrationAdapter

            use_cases = IntegrationUseCases(integration_ops=MimicIntegrationAdapter())
            result = await use_cases.list_integrations(token=user_token)

            integrations = []
            for item in result.items:
                integrations.append({
                    "id": item.id,
                    "name": item.name,
                    "provider": item.provider,
                    "direction": item.direction,
                    "status": item.status,
                })

            logger.info(
                "Fetched user integrations for planner",
                count=len(integrations),
            )
            return integrations

        except Exception as e:
            logger.warning(
                "Failed to fetch user integrations (non-blocking)",
                error=str(e),
            )
            return []

    def _build_integrations_section(self, integrations: List[Dict[str, Any]]) -> List[str]:
        """
        Build the prompt section listing the user's configured integrations.

        Args:
            integrations: List of integration dicts from Mimic

        Returns:
            List of prompt lines for integrations context
        """
        lines = [
            "## User's Configured Integrations",
            "",
            "The user has the following integrations configured. Use these to send messages or perform actions on external services:",
            "",
        ]

        for integration in integrations:
            int_id = integration.get("id", "unknown")
            name = integration.get("name", "unknown")
            provider = integration.get("provider", "unknown")
            direction = integration.get("direction", "unknown")
            int_status = integration.get("status", "unknown")
            lines.append(f"- **{name}** (id: `{int_id}`, provider: `{provider}`, direction: `{direction}`, status: `{int_status}`)")

        lines.extend([
            "",
            "**How to use integrations in your plan:**",
            "1. Use `list_integrations` to discover available integrations (if you need fresh data)",
            "2. Use `execute_outbound_action` with the `integration_id` to send messages or perform actions",
            "",
            "**Example steps for sending a message via an integration:**",
            "```json",
            '{"id": "send_message", "agent_type": "execute_outbound_action", "inputs": {"integration_id": "<id>", "action_type": "send_message", "content": "Hello from aios!"}}',
            "```",
            "",
            "**IMPORTANT**: The `user_token` will be injected automatically — do NOT include it in step inputs.",
            "",
        ])

        return lines

    def get_prompt_stats(self) -> Dict[str, Any]:
        """Get statistics about the prompt builder state."""
        self._load_registry()

        return {
            "total_agents": len(self._agent_metadata),
            "agent_types": list(self._agent_metadata.keys()),
            "categories": list(set(
                m.get("category", "uncategorized")
                for m in self._agent_metadata.values()
            )),
        }

    def validate_agent_metadata(self) -> Dict[str, Any]:
        """
        Validate that all registered agents have required metadata.

        Returns:
            Dict with 'valid' bool and 'errors' list
        """
        self._load_registry()

        errors = []
        warnings = []

        required_fields = ["brief", "category", "inputs_schema"]
        recommended_fields = ["keywords", "example_use_cases"]

        for agent_type, meta in self._agent_metadata.items():
            # Check required fields
            for field in required_fields:
                value = meta.get(field)
                if not value or (field == "brief" and value == "Base subagent (override in subclass)"):
                    errors.append(f"{agent_type}: missing required field '{field}'")

            # Check recommended fields
            for field in recommended_fields:
                value = meta.get(field)
                if not value:
                    warnings.append(f"{agent_type}: missing recommended field '{field}'")

            # Validate inputs_schema structure
            inputs_schema = meta.get("inputs_schema", {})
            if inputs_schema:
                # Support JSON Schema format (has "type", "properties" at top level)
                if "type" in inputs_schema and "properties" in inputs_schema:
                    params = inputs_schema["properties"]
                elif "type" in inputs_schema:
                    # JSON Schema with no properties defined — valid but empty
                    params = {}
                else:
                    # Flat parameter-dict format: {param_name: {description: ...}}
                    params = inputs_schema

                for param, spec in params.items():
                    if not isinstance(spec, dict):
                        errors.append(f"{agent_type}.inputs_schema.{param}: must be a dict")
                    elif "description" not in spec:
                        warnings.append(f"{agent_type}.inputs_schema.{param}: missing description")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "agents_checked": len(self._agent_metadata),
        }


# Singleton instance for convenience
_builder: Optional[DynamicPromptBuilder] = None


def get_prompt_builder() -> DynamicPromptBuilder:
    """Get the singleton DynamicPromptBuilder instance."""
    global _builder
    if _builder is None:
        _builder = DynamicPromptBuilder()
    return _builder
