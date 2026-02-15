# REVIEW: The tool still performs ideation + spec normalization inline. Consider
# REVIEW: a dedicated application use case for agent generation to consolidate
# REVIEW: generation, validation, and persistence logic in one layer.
"""Inbox tool: Create a new agent from a natural language description.

Reuses the existing AgentGeneratorService (ideate → generate → validate → register)
so Flux can create new agents conversationally without the user leaving the inbox.
"""

from typing import Any, Dict, Optional

import yaml
import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.application.capabilities import (
    CapabilityConflict,
    CapabilityForbidden,
    CapabilityUseCases,
    CapabilityValidationError,
)
from src.infrastructure.agents import AgentGeneratorAdapter
from src.infrastructure.capabilities.sql_repository import SqlCapabilityRepository
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)

_capability_use_cases: Optional[CapabilityUseCases] = None


def _get_capability_use_cases() -> CapabilityUseCases:
    global _capability_use_cases
    if _capability_use_cases is None:
        _capability_use_cases = CapabilityUseCases(
            repository=SqlCapabilityRepository(Database())
        )
    return _capability_use_cases


class CreateAgentTool(BaseTool):
    """Generate and register a new agent capability from a description."""

    @property
    def name(self) -> str:
        return "create_agent"

    @property
    def description(self) -> str:
        return (
            "Create a new agent capability from a natural language description. "
            "The agent is generated via AI (ideation + spec generation), validated, "
            "and registered to the user's organization — making it immediately "
            "available for tasks. Use task_capabilities first to confirm the "
            "agent doesn't already exist."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": (
                            "Natural language description of the agent to create. "
                            "Be specific about what it should do, what inputs it "
                            "takes, and what outputs it produces."
                        ),
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Optional additional context about the use case, "
                            "constraints, or integration requirements."
                        ),
                    },
                },
                "required": ["description"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        """Run the full agent generation pipeline."""
        description = arguments.get("description", "")
        extra_context = arguments.get("context")
        user_id = context.get("user_id")
        organization_id = context.get("organization_id")

        if not description:
            return ToolResult(success=False, error="Description is required.")

        if not organization_id:
            return ToolResult(
                success=False,
                error="User must belong to an organization to create agents.",
            )
        if not user_id:
            return ToolResult(
                success=False,
                error="Missing user_id in context.",
            )

        try:
            # --- Phase 1 & 2: Ideate + Generate ---
            generator = AgentGeneratorAdapter()
            ideation = await generator.ideate(description, extra_context)
            generation = await generator.generate(
                description=description,
                agent_type=ideation.suggested_type,
                capabilities=ideation.suggested_capabilities,
                name=ideation.suggested_name,
                category=ideation.suggested_category,
                keywords=ideation.suggested_keywords,
            )

            # --- Phase 3: Transform & Validate ---
            raw_spec = yaml.safe_load(generation.yaml_spec)
            if not isinstance(raw_spec, dict):
                return ToolResult(
                    success=False,
                    error="Generated specification is not a valid YAML object.",
                )

            agent_type_name = raw_spec.get("name", generation.name)

            # Normalise inputs
            raw_inputs = raw_spec.get("inputs")
            if isinstance(raw_inputs, dict):
                inputs = raw_inputs
            elif isinstance(raw_inputs, list):
                inputs = {f: {"type": "string", "description": f} for f in raw_inputs}
            else:
                state_req = raw_spec.get("state_schema", {}).get("required", [])
                if isinstance(state_req, list):
                    inputs = {f: {"type": "string", "description": f} for f in state_req}
                elif isinstance(state_req, dict):
                    inputs = state_req
                else:
                    inputs = {"input": {"type": "string", "description": "Primary input"}}

            # Normalise outputs
            raw_outputs = raw_spec.get("outputs")
            if isinstance(raw_outputs, dict):
                outputs = raw_outputs
            elif isinstance(raw_outputs, list):
                outputs = {f: {"type": "string", "description": f} for f in raw_outputs}
            else:
                state_out = raw_spec.get("state_schema", {}).get("output", [])
                if isinstance(state_out, list):
                    outputs = {f: {"type": "string", "description": f} for f in state_out}
                elif isinstance(state_out, dict):
                    outputs = state_out
                else:
                    outputs = {}

            spec = {
                "agent_type": agent_type_name,
                "name": raw_spec.get("name", generation.name),
                "description": raw_spec.get("description", ideation.brief),
                "domain": raw_spec.get("domain", ideation.suggested_category),
                "task_type": raw_spec.get("task_type", "general"),
                "system_prompt": raw_spec.get("prompt_template") or raw_spec.get("system_prompt", ""),
                "inputs": inputs,
                "outputs": outputs,
                "examples": raw_spec.get("examples", []),
                "execution_hints": raw_spec.get("execution_hints") or raw_spec.get("resources", {}),
            }

            spec_yaml = yaml.safe_dump(spec, sort_keys=False)

            capability_use_cases = _get_capability_use_cases()
            result = await capability_use_cases.create_capability(
                spec_yaml=spec_yaml,
                tags=ideation.suggested_keywords[:10],
                org_id=organization_id,
                user_id=user_id,
            )
            capability = result["capability"]

            return ToolResult(
                success=True,
                data={
                    "id": str(capability["id"]),
                    "agent_type": capability["agent_type"],
                    "name": capability["name"],
                    "description": (capability.get("description") or "")[:200],
                    "domain": capability.get("domain"),
                    "tags": capability.get("tags") or [],
                    "inputs": list((capability.get("inputs_schema") or {}).keys()),
                    "outputs": list((capability.get("outputs_schema") or {}).keys()),
                },
                message=(
                    f"Agent '{capability['name']}' ({capability['agent_type']}) "
                    "created and ready for use in tasks."
                ),
            )

        except CapabilityConflict as e:
            return ToolResult(
                success=False,
                error=str(e),
            )
        except CapabilityValidationError as e:
            return ToolResult(
                success=False,
                error=f"Validation failed: {str(e)}",
                data={"yaml_spec": generation.yaml_spec},
            )
        except CapabilityForbidden as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.error("create_agent tool failed", error=str(e))
            return ToolResult(
                success=False,
                error=f"Agent creation failed: {str(e)}",
            )
