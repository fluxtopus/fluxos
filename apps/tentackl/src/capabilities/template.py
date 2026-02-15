"""
Template Capability

Provides runtime template customization for agents, enabling
organizations to override prompts, parameters, and output transformations.
"""

from typing import Protocol, Optional, Dict, Any, List, runtime_checkable
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TemplateInfo:
    """Information about a loaded template."""
    template_id: str
    name: str
    version: str
    domain: str
    agent_type: str
    description: str = ""


# ============================================================================
# Protocol Definition
# ============================================================================

@runtime_checkable
class TemplateCapability(Protocol):
    """
    Capability for loading and applying agent templates.

    Templates allow runtime customization of:
    - Prompt templates
    - Parameter defaults and constraints
    - Output transformations
    """

    async def load_template(
        self,
        domain: str,
        agent_type: str,
        template_name: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Load a template for the given agent.

        Args:
            domain: Agent domain (e.g., "content")
            agent_type: Agent type (e.g., "youtube_script")
            template_name: Optional template name
            template_id: Optional full template ID

        Returns:
            Template data dictionary or None if not found
        """
        ...

    def get_parameters(
        self,
        template: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get effective parameters with template defaults applied.

        Args:
            template: Loaded template data
            inputs: User-provided inputs

        Returns:
            Merged parameters dictionary
        """
        ...

    def get_prompt(
        self,
        template: Dict[str, Any],
        prompt_name: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """
        Get a rendered prompt from the template.

        Args:
            template: Loaded template data
            prompt_name: Name of the prompt
            context: Context for rendering

        Returns:
            Rendered prompt string or None
        """
        ...

    def get_applicable_prompts(
        self,
        template: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        Get all applicable prompts for the given context.

        Args:
            template: Loaded template data
            context: Context for evaluating conditions

        Returns:
            Dictionary of prompt name -> rendered prompt
        """
        ...

    def transform_output(
        self,
        template: Dict[str, Any],
        output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply template's output transformations.

        Args:
            template: Loaded template data
            output: Agent output to transform
            context: Context for evaluating conditions

        Returns:
            Transformed output dictionary
        """
        ...

    def validate_parameters(
        self,
        template: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> List[str]:
        """
        Validate inputs against template parameter definitions.

        Args:
            template: Loaded template data
            inputs: User-provided inputs

        Returns:
            List of validation error messages (empty if valid)
        """
        ...


# ============================================================================
# Implementation
# ============================================================================

class TemplateCapabilityImpl:
    """
    Implementation of the TemplateCapability protocol.

    Uses AgentTemplateStore for persistence and AgentTemplate
    for template logic.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        cache_enabled: bool = True,
    ):
        """
        Initialize template capability.

        Args:
            redis_url: Redis connection URL for template storage
            cache_enabled: Whether to cache loaded templates
        """
        from src.agents.templates import AgentTemplateStore, AgentTemplate

        self._store = AgentTemplateStore(redis_url=redis_url) if redis_url else AgentTemplateStore()
        self._cache_enabled = cache_enabled
        self._cache: Dict[str, "AgentTemplate"] = {}

    async def load_template(
        self,
        domain: str,
        agent_type: str,
        template_name: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load a template for the given agent."""
        from src.agents.templates import AgentTemplate

        cache_key = template_id or f"{domain}:{agent_type}:{template_name}" if template_name else None

        # Check cache
        if self._cache_enabled and cache_key and cache_key in self._cache:
            return self._cache[cache_key].to_dict()

        try:
            template = None

            if template_id:
                template = await self._store.get_template_by_id(
                    template_id=template_id,
                    approved_only=True,
                )
            elif template_name:
                template = await self._store.get_template(
                    domain=domain,
                    agent_type=agent_type,
                    name=template_name,
                    approved_only=True,
                )

            if template and self._cache_enabled:
                self._cache[template.template_id] = template

            return template.to_dict() if template else None

        except Exception as e:
            logger.error(
                "Failed to load template",
                domain=domain,
                agent_type=agent_type,
                error=str(e),
            )
            return None

    def get_parameters(
        self,
        template: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Get effective parameters with template defaults applied."""
        from src.agents.templates import AgentTemplate

        tmpl = AgentTemplate.from_dict(template)
        return tmpl.get_effective_parameters(inputs)

    def get_prompt(
        self,
        template: Dict[str, Any],
        prompt_name: str,
        context: Dict[str, Any],
    ) -> Optional[str]:
        """Get a rendered prompt from the template."""
        from src.agents.templates import AgentTemplate

        tmpl = AgentTemplate.from_dict(template)
        return tmpl.get_prompt(prompt_name, context)

    def get_applicable_prompts(
        self,
        template: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Get all applicable prompts for the given context."""
        from src.agents.templates import AgentTemplate

        tmpl = AgentTemplate.from_dict(template)
        return tmpl.get_applicable_prompts(context)

    def transform_output(
        self,
        template: Dict[str, Any],
        output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply template's output transformations."""
        from src.agents.templates import AgentTemplate

        tmpl = AgentTemplate.from_dict(template)
        return tmpl.apply_transforms(output, context)

    def validate_parameters(
        self,
        template: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> List[str]:
        """Validate inputs against template parameter definitions."""
        from src.agents.templates import AgentTemplate

        tmpl = AgentTemplate.from_dict(template)
        return tmpl.validate_parameters(inputs)

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()
