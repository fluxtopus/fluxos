"""
# REVIEW:
# - Couples agent behavior tightly to DB schema; no caching strategy for capability config reloads.
# - Strict input validation but lenient output validation may still allow inconsistent downstream behavior.

DatabaseConfiguredAgent - Single runtime class for all LLM-powered agents.

This is the unified agent class that loads behavior from database configuration
(capabilities_agents table). All agents are now DB-configured.

Key benefits:
- Single source of truth (database)
- User-defined agents work identically to system agents
- No code changes needed to add new agent types
- Consistent execution and error handling
- Automatic contract validation

Usage:
    config = await get_agent_capability("summarize")
    agent = DatabaseConfiguredAgent(config)
    await agent.initialize()
    result = await agent.execute(step)
"""

import json
import re
import time
import structlog
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING

from src.agents.llm_subagent import LLMSubagent, SubagentResult
from src.database.capability_models import AgentCapability

if TYPE_CHECKING:
    from src.domain.tasks.models import TaskStep
    from src.infrastructure.execution_runtime.file_resolver import StepFileContext
    from src.llm.openrouter_client import OpenRouterClient, ModelRouting

logger = structlog.get_logger(__name__)


class DatabaseConfiguredAgent(LLMSubagent):
    """
    Single runtime class for all LLM-powered agents.

    Loads behavior from database configuration (capabilities_agents table).
    Includes automatic contract validation for inputs and outputs.

    Usage:
        config = await get_agent_capability("summarize")
        agent = DatabaseConfiguredAgent(config)
        await agent.initialize()
        result = await agent.execute(step)
    """

    def __init__(
        self,
        config: AgentCapability,
        llm_client: Optional["OpenRouterClient"] = None,
        model: Optional[str] = None,
        routing: Optional["ModelRouting"] = None,
    ):
        super().__init__(llm_client=llm_client, model=model, routing=routing)

        # Load configuration from database model
        self.config = config
        self.agent_type = config.agent_type
        self.task_type = config.task_type
        self.domain = getattr(config, 'domain', None) or 'general'

        # Core configuration
        self._system_prompt = config.system_prompt
        self._inputs_schema = config.inputs_schema or {}
        self._outputs_schema = config.outputs_schema or {}
        self._examples = config.examples or []
        self._execution_hints = config.execution_hints or {}

        logger.debug(
            "DatabaseConfiguredAgent initialized",
            agent_type=self.agent_type,
            task_type=self.task_type,
        )

    async def execute(self, step: "TaskStep", file_context: "Optional[StepFileContext]" = None) -> SubagentResult:
        """
        Execute the agent's task with automatic contract validation.

        Contract enforcement ensures:
        1. Bad inputs are blocked BEFORE execution
        2. Bad outputs are blocked AFTER execution (don't propagate to next step)

        Process:
        1. Validate inputs against schema (ContractValidator)
        2. Build prompt from inputs
        3. Call LLM with system prompt
        4. Parse output
        5. Validate outputs against schema (ContractValidator)
        6. Return SubagentResult or validation error
        """
        from src.contracts.validator import ContractValidator

        start_time = time.time()

        try:
            # 1. Extract inputs with defaults applied
            inputs = self._extract_inputs(step)

            # 2. CONTRACT ENFORCEMENT: Validate inputs
            if self._inputs_schema:
                input_validation = ContractValidator.validate_inputs(
                    inputs,
                    self._inputs_schema,
                    strict=True,  # Block on input errors
                )

                if not input_validation.valid:
                    error_msg = f"Input contract violation: {input_validation.error_summary()}"
                    logger.warning(
                        "contract_input_validation_failed",
                        agent_type=self.agent_type,
                        step_id=step.id,
                        errors=input_validation.error_summary(),
                    )
                    return SubagentResult(
                        success=False,
                        output={},
                        error=error_msg,
                        metadata={
                            "validation_errors": [e.to_dict() for e in input_validation.errors],
                            "validation_phase": "input",
                        },
                        execution_time_ms=int((time.time() - start_time) * 1000),
                    )

                # Log warnings but continue
                if input_validation.warnings:
                    logger.info(
                        "contract_input_validation_warnings",
                        agent_type=self.agent_type,
                        warnings=[w.to_dict() for w in input_validation.warnings],
                    )

            logger.info(
                "Executing database-configured agent",
                agent_type=self.agent_type,
                inputs=list(inputs.keys()),
            )

            # 3. Build the user prompt from inputs (may return multimodal list)
            user_prompt = self._build_prompt(inputs, step, file_context=file_context)

            # 4. Call LLM
            response = await self._llm_process(
                user_prompt,
                self._system_prompt,
                temperature=self._get_temperature(),
                max_tokens=self._get_max_tokens(),
            )

            # 5. Parse output
            output = self._parse_output(response, inputs)

            # 6. CONTRACT ENFORCEMENT: Validate outputs
            if self._outputs_schema:
                output_validation = ContractValidator.validate_outputs(
                    output,
                    self._outputs_schema,
                    strict=False,  # Warn on output errors (LLMs are fuzzy)
                )

                if not output_validation.valid:
                    # Output validation failed - block bad output from propagating
                    error_msg = f"Output contract violation: {output_validation.error_summary()}"
                    logger.warning(
                        "contract_output_validation_failed",
                        agent_type=self.agent_type,
                        step_id=step.id,
                        errors=output_validation.error_summary(),
                    )
                    return SubagentResult(
                        success=False,
                        output={},
                        error=error_msg,
                        metadata={
                            "validation_errors": [e.to_dict() for e in output_validation.errors],
                            "validation_phase": "output",
                            "original_output": output,  # Keep for debugging
                        },
                        execution_time_ms=int((time.time() - start_time) * 1000),
                    )

                # Include warnings in metadata
                if output_validation.warnings:
                    logger.info(
                        "contract_output_validation_warnings",
                        agent_type=self.agent_type,
                        warnings=[w.to_dict() for w in output_validation.warnings],
                    )

            execution_time_ms = int((time.time() - start_time) * 1000)

            return SubagentResult(
                success=True,
                output=output,
                execution_time_ms=execution_time_ms,
                metadata={
                    "agent_type": self.agent_type,
                    "domain": self.domain,
                    "response_length": len(response),
                    "contract_validated": True,
                },
            )

        except Exception as e:
            error_str = str(e) or repr(e)
            logger.error(
                "DatabaseConfiguredAgent execution failed",
                agent_type=self.agent_type,
                error=error_str,
            )
            return SubagentResult(
                success=False,
                output={},
                error=f"Agent execution failed: {error_str}",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def _extract_inputs(self, step: "TaskStep") -> Dict[str, Any]:
        """Extract inputs from step, applying defaults from schema using ContractValidator."""
        from src.contracts.validator import ContractValidator

        # Start with step inputs
        step_inputs = step.inputs or {}

        # Apply defaults from schema using ContractValidator
        if self._inputs_schema:
            inputs = ContractValidator.apply_defaults(step_inputs, self._inputs_schema)
        else:
            inputs = step_inputs.copy()

        # Also include any extra inputs not in schema (for flexibility)
        for key, value in step_inputs.items():
            if key not in inputs:
                inputs[key] = value

        return inputs

    def _build_prompt(
        self,
        inputs: Dict[str, Any],
        step: "TaskStep",
        file_context: "Optional[StepFileContext]" = None,
    ) -> Union[str, List[Dict[str, Any]]]:
        """Build the user prompt from inputs.

        Returns a plain string for text-only prompts, or a list of
        content parts (OpenAI vision format) when images are attached.
        """
        parts = []

        if step.name:
            parts.append(f"Task: {step.name}")

        # Add each input as a section
        for key, value in inputs.items():
            # Get field description from schema
            field_schema = self._inputs_schema.get(key, {})
            if isinstance(field_schema, dict):
                description = field_schema.get("description", key)
            else:
                description = key

            # Format the value
            if isinstance(value, (dict, list)):
                formatted_value = json.dumps(value, indent=2)
            else:
                formatted_value = str(value)

            parts.append(f"{description}:\n{formatted_value}")

        text_prompt = "\n\n".join(parts)

        # Inject resolved files if present
        if file_context and file_context.resolved_files:
            image_files = [f for f in file_context.resolved_files if f.is_image]
            text_files = [f for f in file_context.resolved_files if not f.is_image]

            # Inline text files into the prompt
            for tf in text_files:
                text_prompt += f"\n\n--- File: {tf.name} ---\n{tf.content_bytes.decode('utf-8', errors='replace')}"

            # Build multimodal content for images
            if image_files:
                import base64

                content_parts: List[Dict[str, Any]] = [{"type": "text", "text": text_prompt}]
                for img in image_files:
                    b64 = base64.b64encode(img.content_bytes).decode("ascii")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.content_type};base64,{b64}"},
                    })
                return content_parts

        return text_prompt

    def _parse_output(self, response: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response into structured output based on schema."""
        output = {}

        # Try to extract JSON if the response contains it
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Only use if it matches expected output fields
                if any(key in parsed for key in self._outputs_schema.keys()):
                    output = parsed
            except json.JSONDecodeError:
                pass

        # Fix empty title: extract from markdown heading in content if available
        if output and not output.get("title") and "title" in self._outputs_schema:
            content_value = output.get("content", "")
            if isinstance(content_value, str):
                heading_match = re.search(r'^#\s+(.+)$', content_value, re.MULTILINE)
                if heading_match:
                    output["title"] = heading_match.group(1).strip()

        # If no JSON extracted, create output from schema
        if not output:
            for field_name, field_schema in self._outputs_schema.items():
                if isinstance(field_schema, dict):
                    field_type = field_schema.get("type", "string")
                else:
                    field_type = "string"

                if field_type == "string":
                    # Use the full response for the main content field
                    if field_name in ("content", "result", "output", "summary", "draft", "synthesis", "findings"):
                        output[field_name] = response
                    else:
                        # Try to extract specific fields
                        extracted = self._extract_field(response, field_name)
                        output[field_name] = extracted if extracted else ""

                elif field_type == "array":
                    output[field_name] = self._extract_list(response, field_name)

                elif field_type == "integer":
                    output[field_name] = self._extract_number(response, field_name)

                elif field_type == "object":
                    output[field_name] = {}

        # Include relevant input values in output for context
        for key in ("topic", "query", "purpose"):
            if key in inputs and key not in output:
                output[key] = inputs[key]

        return output

    def _extract_field(self, text: str, field_name: str) -> str:
        """Try to extract a specific field from text."""
        patterns = [
            rf'{field_name}\s*:\s*(.+?)(?:\n\n|\n[A-Z]|\Z)',
            rf'\*\*{field_name}\*\*\s*:\s*(.+?)(?:\n\n|\n[A-Z]|\Z)',
            rf'#{1,3}\s*{field_name}\s*\n(.+?)(?:\n\n|\n#|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return ""

    def _extract_list(self, text: str, field_name: str) -> List[str]:
        """Extract list items from text."""
        items = []

        list_patterns = [
            r'[-•*]\s*(.+?)(?:\n|$)',
            r'\d+\.\s*(.+?)(?:\n|$)',
        ]

        for pattern in list_patterns:
            matches = re.findall(pattern, text)
            if matches:
                items.extend([m.strip() for m in matches if m.strip()])

        return items[:20]  # Limit to 20 items

    def _extract_number(self, text: str, field_name: str) -> int:
        """Extract a number associated with a field."""
        pattern = rf'{field_name}\s*[:\s]+(\d+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        numbers = re.findall(r'\b(\d+)\b', text)
        if numbers:
            return int(numbers[0])

        return 0

    def _get_temperature(self) -> float:
        """Get temperature setting based on task type and hints."""
        if self.task_type in ("creative", "content_writing"):
            return 0.7
        if self.task_type in ("reasoning", "analysis"):
            return 0.2
        return 0.3

    def _get_max_tokens(self) -> int:
        """Get max tokens based on execution hints."""
        return self._execution_hints.get("max_tokens", 2000)


class DatabaseConfiguredAgentFactory:
    """
    Factory for creating DatabaseConfiguredAgent instances from database.

    Caches loaded configurations for performance.
    """

    _cache: Dict[str, AgentCapability] = {}

    @classmethod
    async def create(
        cls,
        agent_type: str,
        llm_client: Optional["OpenRouterClient"] = None,
        model: Optional[str] = None,
        routing: Optional["ModelRouting"] = None,
        organization_id: Optional[str] = None,
    ) -> DatabaseConfiguredAgent:
        """
        Create a DatabaseConfiguredAgent by loading config from database.

        Args:
            agent_type: The agent type to load (e.g., "summarize", "draft")
            llm_client: OpenRouter client for LLM operations
            model: Explicit model (bypasses task-based routing)
            routing: Custom routing configuration
            organization_id: Optional org ID for user-defined agents

        Returns:
            DatabaseConfiguredAgent instance ready for execution
        """
        config = await cls._load_config(agent_type, organization_id)
        if not config:
            raise ValueError(
                f"Agent type '{agent_type}' not found in database. "
                f"Ensure it's registered in the capabilities_agents table."
            )

        agent = DatabaseConfiguredAgent(
            config=config,
            llm_client=llm_client,
            model=model,
            routing=routing,
        )

        await agent.initialize()
        return agent

    @classmethod
    async def _load_config(
        cls,
        agent_type: str,
        organization_id: Optional[str] = None,
    ) -> Optional[AgentCapability]:
        """Load agent configuration from database."""
        cache_key = f"{organization_id or 'system'}:{agent_type}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        from src.interfaces.database import Database
        from sqlalchemy import select, or_

        db = Database()
        async with db.get_session() as session:
            if organization_id:
                # Query for org-specific or system agent
                query = select(AgentCapability).where(
                    AgentCapability.agent_type == agent_type,
                    AgentCapability.is_active == True,
                    or_(
                        AgentCapability.organization_id == organization_id,
                        AgentCapability.is_system == True,
                    ),
                ).order_by(
                    # Prefer org-specific over system
                    AgentCapability.is_system.asc()
                ).limit(1)
            else:
                # Query for system agent only
                query = select(AgentCapability).where(
                    AgentCapability.agent_type == agent_type,
                    AgentCapability.is_active == True,
                    AgentCapability.is_system == True,
                ).limit(1)

            result = await session.execute(query)
            config = result.scalar_one_or_none()

            if config:
                cls._cache[cache_key] = config

            return config

    @classmethod
    async def exists(cls, agent_type: str, organization_id: Optional[str] = None) -> bool:
        """Check if an agent type exists in the database."""
        config = await cls._load_config(agent_type, organization_id)
        return config is not None

    @classmethod
    def clear_cache(cls):
        """Clear the configuration cache."""
        cls._cache.clear()

    @classmethod
    async def list_available(cls, organization_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available agent types."""
        from src.interfaces.database import Database
        from sqlalchemy import select, or_

        db = Database()
        async with db.get_session() as session:
            if organization_id:
                query = select(
                    AgentCapability.agent_type,
                    AgentCapability.name,
                    AgentCapability.domain,
                    AgentCapability.description,
                    AgentCapability.is_system,
                ).where(
                    AgentCapability.is_active == True,
                    or_(
                        AgentCapability.organization_id == organization_id,
                        AgentCapability.is_system == True,
                    ),
                )
            else:
                query = select(
                    AgentCapability.agent_type,
                    AgentCapability.name,
                    AgentCapability.domain,
                    AgentCapability.description,
                    AgentCapability.is_system,
                ).where(
                    AgentCapability.is_active == True,
                    AgentCapability.is_system == True,
                )

            result = await session.execute(query)
            return [
                {
                    "agent_type": row.agent_type,
                    "name": row.name,
                    "domain": row.domain,
                    "description": row.description,
                    "is_system": row.is_system,
                }
                for row in result.fetchall()
            ]
