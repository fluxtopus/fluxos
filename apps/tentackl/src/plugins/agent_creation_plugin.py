"""Agent creation plugin for task-driven agent generation.

This plugin exposes agent generation as a first-class task capability,
allowing the task planner to emit create_agent steps that use the
AgentGeneratorService to ideate, generate, validate, and register new agents.

This plugin uses the unified capabilities system (capabilities_agents table)
instead of the deprecated AgentRegistryManager.
"""

from typing import Dict, Any, Optional
import structlog
import yaml

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


async def create_agent_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Create and register a new agent from a natural language description.

    This handler uses the AgentGeneratorService to:
    1. Ideate the agent structure from the description
    2. Generate a complete YAML specification
    3. Validate the specification
    4. Register the agent in the capabilities_agents table (unified capabilities system)

    Inputs:
        agent_description: str - Natural language description of the desired agent
        agent_name: str (optional) - Desired agent name (auto-generated if not provided)
        category: str (optional) - Agent category/domain (default: "custom")
        tags: list[str] (optional) - Tags for discovery
        organization_id: str (optional) - Organization ID for the capability

    Returns:
        success: bool
        capability_id: str - The registered capability ID
        agent_name: str - The agent's name
        version: int - The capability version
        agent_type: str - The agent's type (compose, analyze, etc.)
        message: str - Human-readable status message
        error: str (only on failure)
    """
    description = inputs.get("agent_description")
    name = inputs.get("agent_name")
    category = inputs.get("category", "custom")
    tags = inputs.get("tags", [])
    organization_id = None
    user_id = None
    if context is not None:
        organization_id = getattr(context, "organization_id", None)
        user_id = getattr(context, "user_id", None)
        if organization_id is None and isinstance(context, dict):
            organization_id = context.get("organization_id")
        if user_id is None and isinstance(context, dict):
            user_id = context.get("user_id")
    if organization_id is None:
        organization_id = inputs.get("organization_id")
    if user_id is None:
        user_id = inputs.get("user_id")

    # Validate required inputs
    if not description:
        return {
            "success": False,
            "error": "agent_description is required",
        }

    if isinstance(tags, str):
        # Handle comma-separated string input
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not organization_id:
        return {
            "success": False,
            "error": "organization_id is required to create agents",
        }

    try:
        # Initialize the generator service
        generator = AgentGeneratorAdapter()

        # Step 1: Ideate the agent structure
        logger.info(
            "create_agent_ideating",
            description=description[:100],
            provided_name=name,
        )
        ideation = await generator.ideate(description)

        # Use provided name or suggested name
        agent_name = name or ideation.suggested_name
        agent_type = ideation.suggested_type

        logger.info(
            "create_agent_ideation_complete",
            agent_name=agent_name,
            agent_type=agent_type,
            suggested_capabilities=ideation.suggested_capabilities,
        )

        # Step 2: Generate the YAML specification
        generation_result = await generator.generate(
            description=description,
            agent_type=agent_type,
            capabilities=ideation.suggested_capabilities,
            name=agent_name,
            category=category or ideation.suggested_category,
            keywords=ideation.suggested_keywords,
        )

        logger.info(
            "create_agent_generation_complete",
            agent_name=agent_name,
            version=generation_result.version,
            warnings=generation_result.validation_warnings,
        )

        # Step 3: Parse the generated YAML to normalize fields
        raw_spec = yaml.safe_load(generation_result.yaml_spec)
        if not isinstance(raw_spec, dict):
            return {
                "success": False,
                "error": "Generated specification is not a valid YAML object.",
            }

        agent_type_name = (
            raw_spec.get("agent_type")
            or raw_spec.get("name")
            or generation_result.name
            or agent_name
        )

        raw_inputs = raw_spec.get("inputs")
        if isinstance(raw_inputs, dict):
            inputs_schema = raw_inputs
        elif isinstance(raw_inputs, list):
            inputs_schema = {f: {"type": "string", "description": f} for f in raw_inputs}
        else:
            state_req = raw_spec.get("state_schema", {}).get("required", [])
            if isinstance(state_req, list):
                inputs_schema = {f: {"type": "string", "description": f} for f in state_req}
            elif isinstance(state_req, dict):
                inputs_schema = state_req
            else:
                inputs_schema = {"input": {"type": "string", "description": "Primary input"}}

        raw_outputs = raw_spec.get("outputs")
        if isinstance(raw_outputs, dict):
            outputs_schema = raw_outputs
        elif isinstance(raw_outputs, list):
            outputs_schema = {f: {"type": "string", "description": f} for f in raw_outputs}
        else:
            state_out = raw_spec.get("state_schema", {}).get("output", [])
            if isinstance(state_out, list):
                outputs_schema = {f: {"type": "string", "description": f} for f in state_out}
            elif isinstance(state_out, dict):
                outputs_schema = state_out
            else:
                outputs_schema = {}

        spec = {
            "agent_type": agent_type_name,
            "name": raw_spec.get("name", generation_result.name or agent_name),
            "description": raw_spec.get("description", ideation.brief),
            "domain": raw_spec.get("domain", category or ideation.suggested_category),
            "task_type": raw_spec.get("task_type", "general"),
            "system_prompt": raw_spec.get("prompt_template")
            or raw_spec.get("system_prompt", ""),
            "inputs": inputs_schema,
            "outputs": outputs_schema,
            "examples": raw_spec.get("examples", []),
            "execution_hints": raw_spec.get("execution_hints") or raw_spec.get("resources", {}),
        }

        spec_yaml = yaml.safe_dump(spec, sort_keys=False)

        capability_use_cases = _get_capability_use_cases()
        result = await capability_use_cases.create_capability(
            spec_yaml=spec_yaml,
            tags=tags or ideation.suggested_keywords[:5],
            org_id=organization_id,
            user_id=user_id or "",
        )
        capability = result["capability"]

        logger.info(
            "create_agent_registered",
            capability_id=str(capability["id"]),
            agent_name=capability["name"],
            version=capability["version"],
        )

        return {
            "success": True,
            "capability_id": str(capability["id"]),
            "spec_id": str(capability["id"]),  # Backward compatibility
            "agent_name": capability["name"],
            "version": capability["version"],
            "agent_type": agent_type,
            "category": capability.get("domain"),
            "description": ideation.brief,
            "capabilities": ideation.suggested_capabilities,
            "yaml_spec": spec_yaml,
            "validation_warnings": generation_result.validation_warnings,
            "published": True,  # Capabilities are active immediately
            "message": f"Agent '{capability['name']}' v{capability['version']} created successfully",
        }

    except CapabilityConflict as e:
        logger.error("create_agent_conflict", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }
    except CapabilityValidationError as e:
        logger.error("create_agent_validation_error", error=str(e))
        return {
            "success": False,
            "error": f"Agent validation failed: {str(e)}",
        }
    except CapabilityForbidden as e:
        logger.error("create_agent_forbidden", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }
    except ValueError as e:
        logger.error(
            "create_agent_validation_error",
            error=str(e),
            description=description[:100],
        )
        return {
            "success": False,
            "error": f"Agent validation failed: {str(e)}",
        }
    except Exception as e:
        logger.error(
            "create_agent_failed",
            error=str(e),
            description=description[:100],
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Failed to create agent: {str(e)}",
        }


# Plugin definition for reference (used by UnifiedCapabilityRegistry)
CREATE_AGENT_PLUGIN_DEFINITION = {
    "name": "create_agent",
    "description": "Creates and registers a new agent from a natural language description. "
                   "Use this when the user wants to create a custom agent, automation, or specialized capability. "
                   "The agent will be generated using AI and registered in the capabilities system for future use.",
    "handler": create_agent_handler,
    "inputs_schema": {
        "type": "object",
        "properties": {
            "agent_description": {
                "type": "string",
                "description": "Natural language description of what the agent should do. "
                               "Be specific about inputs, outputs, and behavior.",
            },
            "agent_name": {
                "type": "string",
                "description": "Optional snake_case name for the agent (e.g., 'meal_planner'). "
                               "Auto-generated if not provided.",
            },
            "category": {
                "type": "string",
                "enum": ["automation", "content", "data", "communication", "utility", "integration", "persistence"],
                "description": "Agent category/domain for organization and discovery",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for agent discovery and filtering",
            },
            "organization_id": {
                "type": "string",
                "description": "Optional organization ID to scope the capability",
            },
        },
        "required": ["agent_description"],
    },
    "outputs_schema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "capability_id": {"type": "string", "description": "Unique ID of the registered capability"},
            "spec_id": {"type": "string", "description": "Unique ID (backward compatibility alias for capability_id)"},
            "agent_name": {"type": "string", "description": "The agent's name"},
            "version": {"type": "integer", "description": "Capability version number"},
            "agent_type": {"type": "string", "description": "Agent type (compose, analyze, etc.)"},
            "category": {"type": "string"},
            "description": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "yaml_spec": {"type": "string", "description": "The generated YAML specification"},
            "validation_warnings": {"type": "array", "items": {"type": "string"}},
            "published": {"type": "boolean"},
            "message": {"type": "string"},
            "error": {"type": "string"},
        },
    },
    "category": "automation",
    "execution_hints": {
        "speed": "medium",
        "cost": "medium",  # LLM calls for generation
        "requires_checkpoint": True,  # Important: creating agents should require approval
    },
}
