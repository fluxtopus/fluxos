# REVIEW: LLM client lifecycle created in _get_llm_client but never closed;
# REVIEW: leaks connections.
# REVIEW: Model and capabilities are hard-coded; no config-driven overrides.
"""
Agent Generator Service for Tentackl Agent Memory System.

This service enables dynamic agent creation from natural language descriptions.
Uses LLM to generate YAML agent specifications that can be validated and published.

Workflow:
1. ideate(description) - Analyze description, suggest type/capabilities
2. generate(description, type, capabilities) - Generate full YAML spec
3. refine(yaml_spec, feedback) - Iterate on spec based on feedback
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import json
import yaml
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)


@dataclass
class IdeationResult:
    """Result from agent ideation step."""
    suggested_name: str
    suggested_type: str
    suggested_category: str
    suggested_capabilities: List[str]
    suggested_keywords: List[str]
    brief: str
    reasoning: str


@dataclass
class GenerationResult:
    """Result from agent generation step."""
    yaml_spec: str
    parsed_spec: Dict[str, Any]
    name: str
    version: str
    validation_warnings: List[str]


class AgentGeneratorService:
    """
    Service for generating agent specifications from natural language.

    Uses LLM to analyze descriptions and generate valid YAML agent specs.
    Works with the dynamic agent system to enable code-free agent creation.

    Usage:
        service = AgentGeneratorService(llm_client)

        # Step 1: Ideate
        ideation = await service.ideate("An agent that creates weekly meal plans")

        # Step 2: Generate
        result = await service.generate(
            description="An agent that creates weekly meal plans",
            agent_type=ideation.suggested_type,
            capabilities=ideation.suggested_capabilities
        )

        # Step 3 (optional): Refine
        refined = await service.refine(
            yaml_spec=result.yaml_spec,
            feedback="Add support for dietary restrictions"
        )
    """

    # Available agent types
    AGENT_TYPES = [
        "compose",      # Content generation
        "analyze",      # Data analysis
        "transform",    # Data transformation
        "notify",       # Notifications/alerts
        "http_fetch",   # HTTP API calls
        "file_storage", # File operations
        "document_db",  # Document storage
        "agent_storage",# Agent namespace storage
        "custom",       # Custom behavior
    ]

    # Available capabilities
    CAPABILITIES = [
        "http_fetch",       # Make HTTP requests
        "file_storage",     # Store files in Den
        "document_db",      # Document collections
        "agent_storage",    # Agent namespace files
        "notify",           # Send notifications
        "generate_image",   # Image generation
        "schedule_job",     # Schedule recurring tasks
        "html_to_pdf",      # Convert HTML to PDF
    ]

    # Agent categories
    CATEGORIES = [
        "automation",      # Automated workflows
        "content",         # Content creation
        "data",            # Data processing
        "communication",   # Messaging/notifications
        "utility",         # Utility functions
        "integration",     # External integrations
        "persistence",     # Data storage
    ]

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "anthropic/claude-3.5-sonnet",
    ):
        """
        Initialize generator service.

        Args:
            llm_client: OpenRouter client for LLM calls
            model: Model to use for generation
        """
        self.llm_client = llm_client
        self.model = model

    async def _get_llm_client(self):
        """Get or create LLM client."""
        if self.llm_client is None:
            from src.llm.openrouter_client import OpenRouterClient
            self.llm_client = OpenRouterClient()
            await self.llm_client.__aenter__()
        return self.llm_client

    async def ideate(
        self,
        description: str,
        context: Optional[str] = None,
    ) -> IdeationResult:
        """
        Analyze a natural language description and suggest agent structure.

        Args:
            description: Natural language description of desired agent
            context: Optional additional context about use case

        Returns:
            IdeationResult with suggested type, capabilities, keywords
        """
        prompt = f"""Analyze this agent description and suggest the best structure for it.

Description: {description}
{f'Additional context: {context}' if context else ''}

Available agent types: {json.dumps(self.AGENT_TYPES)}
Available capabilities: {json.dumps(self.CAPABILITIES)}
Available categories: {json.dumps(self.CATEGORIES)}

Respond with JSON in this exact format:
{{
    "suggested_name": "snake_case_name",
    "suggested_type": "one of the agent types",
    "suggested_category": "one of the categories",
    "suggested_capabilities": ["list", "of", "capabilities"],
    "suggested_keywords": ["search", "keywords", "for", "discovery"],
    "brief": "One line description (max 100 chars)",
    "reasoning": "Brief explanation of why these choices were made"
}}

Guidelines:
- Name should be descriptive and snake_case (e.g., meal_planner, daily_digest)
- Only include capabilities the agent actually needs
- Keywords should help users find this agent via search
- Brief should complete: "This agent..."
"""

        try:
            client = await self._get_llm_client()
            messages = [{"role": "user", "content": prompt}]
            response = await client.complete(
                messages=messages,
                model=self.model,
                max_tokens=1000,
            )

            # Parse JSON from response (response has 'choices' with 'message' dict)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            result = self._extract_json(content)

            return IdeationResult(
                suggested_name=result.get("suggested_name", "custom_agent"),
                suggested_type=result.get("suggested_type", "compose"),
                suggested_category=result.get("suggested_category", "utility"),
                suggested_capabilities=result.get("suggested_capabilities", []),
                suggested_keywords=result.get("suggested_keywords", []),
                brief=result.get("brief", description[:100]),
                reasoning=result.get("reasoning", ""),
            )

        except Exception as e:
            logger.error("ideation_failed", error=str(e), description=description[:100])
            # Return sensible defaults on failure
            return IdeationResult(
                suggested_name="custom_agent",
                suggested_type="compose",
                suggested_category="utility",
                suggested_capabilities=[],
                suggested_keywords=[],
                brief=description[:100],
                reasoning=f"Ideation failed: {str(e)}",
            )

    async def generate(
        self,
        description: str,
        agent_type: str = "compose",
        capabilities: Optional[List[str]] = None,
        name: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        version: str = "1.0.0",
    ) -> GenerationResult:
        """
        Generate a complete YAML agent specification.

        Args:
            description: Natural language description
            agent_type: Agent type (from AGENT_TYPES)
            capabilities: List of capabilities to enable
            name: Agent name (auto-generated if not provided)
            category: Agent category
            keywords: Search keywords
            version: Semantic version

        Returns:
            GenerationResult with YAML spec and parsed dict
        """
        capabilities = capabilities or []
        keywords = keywords or []

        prompt = f"""Generate a complete YAML agent specification based on this description.

Description: {description}
Name: {name or 'auto-generate a descriptive snake_case name'}
Type: {agent_type}
Category: {category or 'auto-select appropriate category'}
Capabilities: {json.dumps(capabilities) if capabilities else 'auto-select based on description'}
Keywords: {json.dumps(keywords) if keywords else 'auto-generate 5-10 search keywords'}
Version: {version}

Generate a YAML spec following this FLAT structure (no wrapper key):

```yaml
name: {name or 'snake_case_name'}
type: {agent_type}
version: "{version}"

description: |
  Full multi-line description of what this agent does.
  Include use cases and examples.

# Capabilities as objects with 'tool' key
capabilities:
  - tool: http_fetch
    config: {{}}
  - tool: file_storage
    config: {{}}

prompt_template: |
  [Task-specific prompt template with Jinja2 variables]

  {{{{ inputs.field_name }}}}

  {{% if context.previous_result %}}
  Previous result: {{{{ context.previous_result }}}}
  {{% endif %}}

state_schema:
  required:
    - data
  output:
    - result

resources:
  model: gpt-4
  max_tokens: 2000
  timeout: 300

execution_strategy: sequential
```

IMPORTANT:
- NO "agent:" wrapper - fields must be at the TOP LEVEL
- Use Jinja2 template syntax with doubled braces: {{{{ and }}}}
- Include practical prompt_template
- capabilities MUST be list of objects with "tool" key (NOT simple strings)
- Only include capabilities from: {json.dumps(self.CAPABILITIES)}
- state_schema needs "required" and "output" arrays
- resources needs "model", "max_tokens", "timeout"
- execution_strategy must be: sequential, parallel, or conditional
- Only respond with the YAML block, no other text
"""

        try:
            client = await self._get_llm_client()
            messages = [{"role": "user", "content": prompt}]
            response = await client.complete(
                messages=messages,
                model=self.model,
                max_tokens=3000,
            )

            # Extract YAML from response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            yaml_spec = self._extract_yaml(content)
            parsed_spec = yaml.safe_load(yaml_spec)

            # Validate basic structure
            warnings = self._validate_spec_structure(parsed_spec)

            # Handle both flat structure (new) and wrapped structure (legacy)
            if "agent" in parsed_spec:
                agent_config = parsed_spec.get("agent", {})
            else:
                agent_config = parsed_spec

            return GenerationResult(
                yaml_spec=yaml_spec,
                parsed_spec=parsed_spec,
                name=agent_config.get("name", name or "custom_agent"),
                version=agent_config.get("version", version),
                validation_warnings=warnings,
            )

        except Exception as e:
            logger.error("generation_failed", error=str(e), description=description[:100])
            raise ValueError(f"Agent generation failed: {str(e)}")

    async def refine(
        self,
        yaml_spec: str,
        feedback: str,
    ) -> GenerationResult:
        """
        Refine an existing agent specification based on feedback.

        Args:
            yaml_spec: Existing YAML specification
            feedback: User feedback or requested changes

        Returns:
            GenerationResult with updated spec
        """
        prompt = f"""Refine this agent specification based on the feedback provided.

Current specification:
```yaml
{yaml_spec}
```

Feedback/Requested changes:
{feedback}

Guidelines:
- Preserve the overall structure
- Only modify what's needed to address the feedback
- Keep Jinja2 template syntax with doubled braces: {{{{ and }}}}
- Ensure the spec remains valid YAML

Respond with ONLY the updated YAML specification.
"""

        try:
            client = await self._get_llm_client()
            messages = [{"role": "user", "content": prompt}]
            response = await client.complete(
                messages=messages,
                model=self.model,
                max_tokens=3000,
            )

            # Extract YAML from response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            refined_yaml = self._extract_yaml(content)
            parsed_spec = yaml.safe_load(refined_yaml)

            warnings = self._validate_spec_structure(parsed_spec)

            # Handle both flat structure (new) and wrapped structure (legacy)
            if "agent" in parsed_spec:
                agent_config = parsed_spec.get("agent", {})
            else:
                agent_config = parsed_spec

            return GenerationResult(
                yaml_spec=refined_yaml,
                parsed_spec=parsed_spec,
                name=agent_config.get("name", "custom_agent"),
                version=agent_config.get("version", "1.0.0"),
                validation_warnings=warnings,
            )

        except Exception as e:
            logger.error("refinement_failed", error=str(e), feedback=feedback[:100])
            raise ValueError(f"Agent refinement failed: {str(e)}")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        # Try to find JSON block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            json_str = text[start:end].strip()
        elif "{" in text:
            # Find first { to last }
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
        else:
            raise ValueError("No JSON found in response")

        return json.loads(json_str)

    def _extract_yaml(self, text: str) -> str:
        """Extract YAML from LLM response."""
        # Try to find YAML block
        if "```yaml" in text:
            start = text.find("```yaml") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            # Generic code block
            start = text.find("```") + 3
            # Skip language identifier if present
            newline = text.find("\n", start)
            start = newline + 1
            end = text.find("```", start)
            return text[start:end].strip()
        else:
            # Assume entire response is YAML
            return text.strip()

    def _validate_spec_structure(self, spec: Dict[str, Any]) -> List[str]:
        """Validate basic spec structure and return warnings."""
        warnings = []

        # Handle both flat structure (new) and wrapped structure (legacy)
        if "agent" in spec:
            agent = spec["agent"]
        else:
            agent = spec

        required_fields = ["name", "type"]
        for field in required_fields:
            if field not in agent:
                warnings.append(f"Missing required field: {field}")

        if agent.get("type") and agent["type"] not in self.AGENT_TYPES:
            warnings.append(f"Unknown agent type: {agent['type']}")

        if agent.get("capabilities"):
            for cap in agent["capabilities"]:
                # Handle both object format (new) and string format (legacy)
                cap_name = cap.get("tool") if isinstance(cap, dict) else cap
                if cap_name and cap_name not in self.CAPABILITIES:
                    warnings.append(f"Unknown capability: {cap_name}")

        if agent.get("category") and agent["category"] not in self.CATEGORIES:
            warnings.append(f"Unknown category: {agent['category']}")

        return warnings

    async def generate_from_ideation(
        self,
        description: str,
        context: Optional[str] = None,
    ) -> GenerationResult:
        """
        Convenience method: ideate then generate in one call.

        Args:
            description: Natural language description
            context: Optional additional context

        Returns:
            GenerationResult with complete spec
        """
        # First ideate
        ideation = await self.ideate(description, context)

        # Then generate
        return await self.generate(
            description=description,
            agent_type=ideation.suggested_type,
            capabilities=ideation.suggested_capabilities,
            name=ideation.suggested_name,
            category=ideation.suggested_category,
            keywords=ideation.suggested_keywords,
        )
