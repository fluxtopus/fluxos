"""
# REVIEW:
# - Supports both legacy and new spec formats, increasing complexity and paths to test.
# - Jinja2 rendering with StrictUndefined can throw at runtime; error handling is best-effort.

Dynamic Agent Runtime for Tentackl Agent Memory System.

This module provides a runtime wrapper for YAML-defined agents. Dynamic agents
are created from YAML specifications and interpreted at execution time,
allowing agents to be created without writing Python code.

A DynamicAgent wraps an AgentCapability from the database and provides the same
interface as BaseSubagent, making it interchangeable with hardcoded agents.

Key features:
- Interprets prompt_template with Jinja2
- Executes capabilities via CapabilityExecutor
- Validates inputs/outputs against JSON schemas
- Supports checkpoints defined in YAML

Note: As of CAP-023, this module uses capabilities_agents table (AgentCapability model)
instead of the deprecated agent_specs table.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import yaml
import structlog
from jinja2 import Template, Environment, BaseLoader, StrictUndefined

from src.domain.tasks.models import TaskStep, CheckpointConfig, CheckpointType, ApprovalType
from src.infrastructure.execution_runtime.capability_executor import CapabilityExecutor

logger = structlog.get_logger(__name__)


class DynamicAgentError(Exception):
    """Raised when dynamic agent execution fails."""
    pass


class DynamicAgent:
    """
    Runtime wrapper for YAML-defined agents.

    A DynamicAgent interprets an AgentCapability from the database and provides
    execution capabilities without requiring Python code.

    Usage:
        from src.database.capability_models import AgentCapability

        cap = await registry.get_capability(name="meal_planner")
        agent = DynamicAgent(cap)
        result = await agent.execute(step, context)
    """

    def __init__(
        self,
        agent_spec: Any,  # AgentCapability model (or legacy AgentSpec)
        llm_client: Optional[Any] = None,
        plugin_registry: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ):
        """
        Initialize dynamic agent from capability.

        Args:
            agent_spec: AgentCapability database model (also supports legacy AgentSpec)
            llm_client: LLM client for prompt execution
            plugin_registry: Available plugin handlers for capabilities (deprecated)
            org_id: Organization ID for capability execution
            workflow_id: Workflow ID for capability execution
        """
        self.spec = agent_spec
        self.llm_client = llm_client
        self.plugin_registry = plugin_registry or {}  # Kept for backwards compatibility
        self.org_id = org_id
        self.workflow_id = workflow_id

        # Detect capability model type and extract config
        # AgentCapability uses spec_yaml (parsed), AgentSpec uses spec_compiled
        if hasattr(agent_spec, 'spec_compiled') and agent_spec.spec_compiled:
            # Legacy AgentSpec format
            self.spec_compiled = agent_spec.spec_compiled
            self.agent_config = self.spec_compiled.get("agent", {})
            self.name = self.agent_config.get("name", agent_spec.name)
            self.agent_type = self.agent_config.get("type", agent_spec.agent_type)
            self.version = self.agent_config.get("version", getattr(agent_spec, 'version', '1.0.0'))
            self.prompt_template = self.agent_config.get("prompt_template", "")
            self.system_prompt = self.agent_config.get("system_prompt", "")
        else:
            # New AgentCapability format
            self.spec_compiled = {}
            self.agent_config = {}
            self.name = agent_spec.name
            self.agent_type = agent_spec.agent_type
            self.version = str(getattr(agent_spec, 'version', 1))
            self.prompt_template = ""
            self.system_prompt = agent_spec.system_prompt or ""

        # Schema configuration - support both formats
        if hasattr(agent_spec, 'inputs_schema') and agent_spec.inputs_schema:
            # New AgentCapability format
            self.input_schema = agent_spec.inputs_schema
            self.output_schema = agent_spec.outputs_schema or {}
        else:
            # Legacy AgentSpec format
            self.input_schema = self.agent_config.get("input_schema", {})
            self.output_schema = self.agent_config.get("output_schema", {})

        # Capabilities this agent can use
        self.capabilities = self.agent_config.get("capabilities", [])

        # Initialize capability executor if org_id is provided
        self.capability_executor: Optional[CapabilityExecutor] = None
        if org_id:
            self.capability_executor = CapabilityExecutor(
                org_id=org_id,
                agent_id=self.name,
                workflow_id=workflow_id,
                enabled_capabilities=self.capabilities,
            )

        # Checkpoint configuration
        self.checkpoint_configs = self.agent_config.get("checkpoints", [])

        # Jinja2 environment
        self.jinja_env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
        )

        logger.debug(
            "dynamic_agent_initialized",
            name=self.name,
            type=self.agent_type,
            capabilities=self.capabilities,
        )

    def _render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """Render a Jinja2 template with context."""
        try:
            template = self.jinja_env.from_string(template_str)
            return template.render(**context)
        except Exception as e:
            logger.error("template_render_failed", error=str(e), template=template_str[:100])
            raise DynamicAgentError(f"Template render failed: {e}")

    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate inputs against input_schema."""
        if not self.input_schema:
            return True

        # Simple required field validation
        required = self.input_schema.get("required", [])
        for field in required:
            if field not in inputs:
                raise DynamicAgentError(f"Missing required input: {field}")

        # Type validation
        properties = self.input_schema.get("properties", {})
        for field, value in inputs.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type and not self._check_type(value, expected_type):
                    raise DynamicAgentError(
                        f"Invalid type for {field}: expected {expected_type}"
                    )

        return True

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON Schema type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected = type_map.get(expected_type)
        if expected is None:
            return True

        return isinstance(value, expected)

    def get_checkpoint_config(self, checkpoint_name: str) -> Optional[CheckpointConfig]:
        """Get checkpoint configuration by name."""
        for config in self.checkpoint_configs:
            if config.get("name") == checkpoint_name:
                # Convert YAML config to CheckpointConfig
                checkpoint_type = CheckpointType.APPROVAL
                if config.get("type"):
                    try:
                        checkpoint_type = CheckpointType(config["type"])
                    except ValueError:
                        pass

                return CheckpointConfig(
                    name=config.get("name", "checkpoint"),
                    description=config.get("description", ""),
                    approval_type=ApprovalType.EXPLICIT,
                    checkpoint_type=checkpoint_type,
                    input_schema=config.get("input_schema"),
                    questions=config.get("questions"),
                    alternatives=config.get("alternatives"),
                    modifiable_fields=config.get("modifiable_fields"),
                    context_data=config.get("context_data"),
                    preview_fields=config.get("preview_fields", []),
                    preference_key=config.get("preference_key"),
                )

        return None

    async def execute_capability(
        self,
        capability: str,
        operation: str,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a capability operation.

        Args:
            capability: Capability name (e.g., "file_storage", "document_db")
            operation: Operation name (e.g., "agent_save", "doc_insert")
            inputs: Inputs for the operation

        Returns:
            Operation outputs
        """
        # Use CapabilityExecutor if available
        if self.capability_executor:
            try:
                return await self.capability_executor.execute(
                    capability=capability,
                    operation=operation,
                    inputs=inputs,
                )
            except Exception as e:
                logger.error(
                    "capability_execution_failed",
                    capability=capability,
                    operation=operation,
                    error=str(e),
                )
                raise DynamicAgentError(f"Capability {capability}.{operation} failed: {e}")

        # Fallback to legacy plugin_registry for backwards compatibility
        if capability not in self.capabilities:
            raise DynamicAgentError(f"Capability not enabled: {capability}")

        handler = self.plugin_registry.get(operation) or self.plugin_registry.get(capability)
        if not handler:
            raise DynamicAgentError(f"No handler for: {operation}")

        try:
            result = await handler(inputs)
            return result
        except Exception as e:
            logger.error(
                "capability_execution_failed",
                capability=capability,
                operation=operation,
                error=str(e),
            )
            raise DynamicAgentError(f"Capability {capability}.{operation} failed: {e}")

    async def build_prompt(
        self,
        step: TaskStep,
        context: Dict[str, Any],
        user_preferences: Optional[str] = None,
    ) -> str:
        """
        Build the prompt for LLM execution.

        Args:
            step: Task step being executed
            context: Execution context (accumulated findings, etc.)
            user_preferences: Optional preferences section to inject

        Returns:
            Complete prompt for LLM
        """
        # Build template context
        template_context = {
            "step": step,
            "inputs": step.inputs,
            "context": context,
            "agent_name": self.name,
            "agent_type": self.agent_type,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Merge step inputs into context
        template_context.update(step.inputs)

        # Render prompt template
        prompt_parts = []

        # System prompt (if any)
        if self.system_prompt:
            system = self._render_template(self.system_prompt, template_context)
            prompt_parts.append(f"<system>\n{system}\n</system>")

        # User preferences section
        if user_preferences:
            prompt_parts.append(user_preferences)

        # Main prompt
        if self.prompt_template:
            main_prompt = self._render_template(self.prompt_template, template_context)
            prompt_parts.append(main_prompt)
        else:
            # Default prompt if none specified
            prompt_parts.append(
                f"Execute task step: {step.name}\n"
                f"Description: {step.description}\n"
                f"Inputs: {json.dumps(step.inputs, indent=2)}"
            )

        return "\n\n".join(prompt_parts)

    async def execute(
        self,
        step: TaskStep,
        context: Dict[str, Any],
        user_preferences: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the dynamic agent on a task step.

        Args:
            step: Task step to execute
            context: Execution context
            user_preferences: Optional preferences section for prompt

        Returns:
            Execution outputs
        """
        try:
            # Validate inputs
            self._validate_inputs(step.inputs)

            # Build prompt
            prompt = await self.build_prompt(step, context, user_preferences)

            # Execute via LLM
            if self.llm_client:
                response = await self.llm_client.complete(prompt)
                result = self._parse_llm_response(response)
            else:
                # No LLM client - return raw prompt for debugging
                result = {
                    "prompt": prompt,
                    "warning": "No LLM client configured, returning prompt only",
                }

            logger.info(
                "dynamic_agent_executed",
                agent=self.name,
                step_id=step.id,
            )

            return result

        except DynamicAgentError:
            raise
        except Exception as e:
            logger.error(
                "dynamic_agent_execution_failed",
                agent=self.name,
                step_id=step.id,
                error=str(e),
            )
            raise DynamicAgentError(f"Execution failed: {e}")

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response into structured output.

        Attempts to extract JSON from response, falls back to raw text.
        """
        # Try to extract JSON from response
        try:
            # Look for JSON block in response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
                return json.loads(json_str)

            # Try direct JSON parse
            return json.loads(response)

        except (json.JSONDecodeError, ValueError):
            # Return as text output
            return {"output": response}

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.agent_type,
            "version": self.version,
            "description": self.spec.description,
            "capabilities": self.capabilities,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "checkpoints": self.checkpoint_configs,
        }


class DynamicAgentFactory:
    """
    Factory for creating DynamicAgent instances from the capabilities registry.

    Usage:
        factory = DynamicAgentFactory(db_session, llm_client, org_id="...")
        agent = await factory.create("meal_planner")
        result = await agent.execute(step, context)

    Note: As of CAP-023, this factory uses capabilities_agents table (AgentCapability model)
    instead of the deprecated agent_specs table.
    """

    def __init__(
        self,
        db_session,
        llm_client: Optional[Any] = None,
        plugin_registry: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ):
        """
        Initialize factory.

        Args:
            db_session: Database session for registry lookups
            llm_client: LLM client for agent execution
            plugin_registry: Available plugin handlers (deprecated)
            org_id: Organization ID for capability execution
            workflow_id: Workflow ID for capability execution
        """
        self.db_session = db_session
        self.llm_client = llm_client
        self.plugin_registry = plugin_registry or {}
        self.org_id = org_id
        self.workflow_id = workflow_id

    async def create(
        self,
        agent_name: str,
        version: str = "latest",
    ) -> Optional[DynamicAgent]:
        """
        Create a DynamicAgent from the capabilities registry.

        Args:
            agent_name: Name of the agent (matched against agent_type or name)
            version: Version to use ("latest" for most recent, or specific version number)

        Returns:
            DynamicAgent instance or None if not found
        """
        try:
            from sqlalchemy import select, and_, or_, desc
            from src.database.capability_models import AgentCapability

            # Build query - search by agent_type or name
            conditions = [
                or_(
                    AgentCapability.agent_type == agent_name,
                    AgentCapability.name == agent_name,
                ),
                AgentCapability.is_active == True,
            ]

            if version != "latest":
                # Try to parse version as integer
                try:
                    version_int = int(version.split('.')[0]) if '.' in version else int(version)
                    conditions.append(AgentCapability.version == version_int)
                except ValueError:
                    pass  # Non-numeric version, ignore
            else:
                conditions.append(AgentCapability.is_latest == True)

            query = (
                select(AgentCapability)
                .where(and_(*conditions))
                .order_by(desc(AgentCapability.created_at))
                .limit(1)
            )

            result = await self.db_session.execute(query)
            capability = result.scalar_one_or_none()

            if not capability:
                logger.warning(
                    "dynamic_agent_not_found",
                    agent_name=agent_name,
                    version=version,
                )
                return None

            return DynamicAgent(
                agent_spec=capability,
                llm_client=self.llm_client,
                plugin_registry=self.plugin_registry,
                org_id=self.org_id,
                workflow_id=self.workflow_id,
            )

        except Exception as e:
            logger.error(
                "dynamic_agent_create_failed",
                agent_name=agent_name,
                error=str(e),
            )
            return None

    async def list_available(self) -> List[Dict[str, Any]]:
        """List all available dynamic agents from capabilities registry."""
        try:
            from sqlalchemy import select
            from src.database.capability_models import AgentCapability

            # Build query for org-scoped or system capabilities
            conditions = [
                AgentCapability.is_active == True,
                AgentCapability.is_latest == True,
            ]

            # If org_id is set, get both org and system capabilities
            if self.org_id:
                from sqlalchemy import or_
                conditions.append(
                    or_(
                        AgentCapability.organization_id == self.org_id,
                        AgentCapability.is_system == True,
                    )
                )

            query = select(AgentCapability).where(*conditions)

            result = await self.db_session.execute(query)
            capabilities = result.scalars().all()

            return [
                {
                    "name": c.name,
                    "version": str(c.version),
                    "type": c.agent_type,
                    "description": c.description,
                    "brief": c.description[:200] if c.description else None,
                    "category": c.domain,  # Map domain to category for backwards compatibility
                    "tags": c.tags or [],
                }
                for c in capabilities
            ]

        except Exception as e:
            logger.error("list_dynamic_agents_failed", error=str(e))
            return []
