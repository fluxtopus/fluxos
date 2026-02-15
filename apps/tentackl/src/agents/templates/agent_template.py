"""
Agent Template Model

Defines the schema for agent templates that enable runtime customization
of domain subagents. Templates can override prompts, parameters, and
define output transformations.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional, Union
import structlog
import yaml
import json

from ...core.safe_eval import safe_eval, safe_eval_condition

logger = structlog.get_logger(__name__)


class ParameterType(str, Enum):
    """Supported parameter types for template parameters."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    ENUM = "enum"


class TemplateValidationError(Exception):
    """Raised when template validation fails."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Template validation failed: {'; '.join(errors)}")


@dataclass
class TemplateParameter:
    """
    Defines a configurable parameter for an agent template.

    Parameters allow users to customize agent behavior without
    modifying the core template.
    """
    name: str
    type: ParameterType
    description: str = ""
    default: Optional[Any] = None
    required: bool = False
    allowed: Optional[List[Any]] = None  # For enum type
    min_value: Optional[Union[int, float]] = None  # For numeric types
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None  # Regex for string validation

    def validate(self, value: Any) -> List[str]:
        """Validate a value against this parameter's constraints."""
        errors = []

        if value is None:
            if self.required and self.default is None:
                errors.append(f"Parameter '{self.name}' is required")
            return errors

        # Type validation
        type_map = {
            ParameterType.STRING: str,
            ParameterType.INTEGER: int,
            ParameterType.FLOAT: (int, float),
            ParameterType.BOOLEAN: bool,
            ParameterType.LIST: list,
            ParameterType.DICT: dict,
            ParameterType.ENUM: None,  # Handled separately
        }

        expected_type = type_map.get(self.type)
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"Parameter '{self.name}' must be {self.type.value}, got {type(value).__name__}"
            )
            return errors  # Can't validate further if wrong type

        # Enum validation
        if self.type == ParameterType.ENUM and self.allowed:
            if value not in self.allowed:
                errors.append(
                    f"Parameter '{self.name}' must be one of {self.allowed}, got '{value}'"
                )

        # Numeric range validation
        if self.type in (ParameterType.INTEGER, ParameterType.FLOAT):
            if self.min_value is not None and value < self.min_value:
                errors.append(
                    f"Parameter '{self.name}' must be >= {self.min_value}"
                )
            if self.max_value is not None and value > self.max_value:
                errors.append(
                    f"Parameter '{self.name}' must be <= {self.max_value}"
                )

        # String pattern validation
        if self.type == ParameterType.STRING and self.pattern:
            if not re.match(self.pattern, value):
                errors.append(
                    f"Parameter '{self.name}' must match pattern '{self.pattern}'"
                )

        return errors

    def get_value(self, provided: Optional[Any] = None) -> Any:
        """Get the effective value (provided or default)."""
        return provided if provided is not None else self.default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "default": self.default,
            "required": self.required,
            "allowed": self.allowed,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "pattern": self.pattern,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateParameter":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            type=ParameterType(data["type"]),
            description=data.get("description", ""),
            default=data.get("default"),
            required=data.get("required", False),
            allowed=data.get("allowed"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            pattern=data.get("pattern"),
        )


@dataclass
class TemplatePrompt:
    """
    Defines a customizable prompt section for an agent template.

    Prompts use Jinja2-style templating with {{ variable }} placeholders.
    """
    name: str  # e.g., "system", "user", "shorts_system", "long_form_system"
    template: str
    description: str = ""
    extends_base: bool = True  # If True, appends to base prompt
    condition: Optional[str] = None  # Python expression for conditional inclusion

    def render(self, context: Dict[str, Any]) -> str:
        """
        Render the prompt template with the given context.

        Uses simple {{ variable }} replacement. For more complex
        templating, consider using Jinja2.
        """
        result = self.template

        # Simple variable substitution
        for key, value in context.items():
            placeholder = "{{ " + key + " }}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else "")
            # Also handle without spaces
            placeholder_no_space = "{{" + key + "}}"
            if placeholder_no_space in result:
                result = result.replace(placeholder_no_space, str(value) if value else "")

        return result.strip()

    def should_apply(self, context: Dict[str, Any]) -> bool:
        """Check if this prompt should be applied given the context."""
        if not self.condition:
            return True

        return safe_eval_condition(self.condition, context=context, default=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "template": self.template,
            "description": self.description,
            "extends_base": self.extends_base,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplatePrompt":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            template=data["template"],
            description=data.get("description", ""),
            extends_base=data.get("extends_base", True),
            condition=data.get("condition"),
        )


@dataclass
class OutputTransform:
    """
    Defines a transformation to apply to agent output.

    Transforms can add, modify, or filter output fields.
    """
    name: str
    condition: Optional[str] = None  # Python expression
    transform_type: str = "add"  # add, modify, remove, filter
    target_field: Optional[str] = None  # Field to operate on
    value: Optional[Any] = None  # Static value or template
    expression: Optional[str] = None  # Python expression for computed value

    def should_apply(self, context: Dict[str, Any]) -> bool:
        """Check if this transform should be applied given the context."""
        if not self.condition:
            return True

        return safe_eval_condition(self.condition, context=context, default=False)

    def apply(self, output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Apply this transform to the output."""
        if not self.should_apply({**context, **output}):
            return output

        result = output.copy()

        if self.transform_type == "add" and self.target_field:
            if self.expression:
                try:
                    result[self.target_field] = safe_eval(
                        self.expression,
                        names={**context, **output},
                    )
                except Exception as e:
                    logger.error(
                        "Failed to evaluate transform expression",
                        transform=self.name,
                        expression=self.expression,
                        error=str(e),
                    )
            elif self.value is not None:
                # Template the value if it's a string
                if isinstance(self.value, str):
                    value = self.value
                    for key, val in {**context, **output}.items():
                        value = value.replace("{{ " + key + " }}", str(val) if val else "")
                        value = value.replace("{{" + key + "}}", str(val) if val else "")
                    result[self.target_field] = value
                else:
                    result[self.target_field] = self.value

        elif self.transform_type == "modify" and self.target_field:
            if self.target_field in result and self.expression:
                try:
                    result[self.target_field] = safe_eval(
                        self.expression,
                        names={**context, **output, "original": result[self.target_field]},
                    )
                except Exception as e:
                    logger.error(
                        "Failed to evaluate modify expression",
                        transform=self.name,
                        error=str(e),
                    )

        elif self.transform_type == "remove" and self.target_field:
            result.pop(self.target_field, None)

        elif self.transform_type == "filter":
            # Filter can remove fields based on condition
            if self.target_field and self.target_field in result:
                result.pop(self.target_field)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "condition": self.condition,
            "transform_type": self.transform_type,
            "target_field": self.target_field,
            "value": self.value,
            "expression": self.expression,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputTransform":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            condition=data.get("condition"),
            transform_type=data.get("transform_type", "add"),
            target_field=data.get("target_field"),
            value=data.get("value"),
            expression=data.get("expression"),
        )


@dataclass
class AgentTemplate:
    """
    Template for customizing domain subagent behavior at runtime.

    Templates allow organizations to customize agent prompts, parameters,
    and output transformations without modifying core agent code.

    Example YAML template:
    ```yaml
    name: brand-youtube-template
    version: 1.0.0
    domain: content
    agent_type: youtube_script

    parameters:
      - name: brand_voice
        type: string
        description: The brand's voice and tone
        default: professional
      - name: thumbnail_style
        type: enum
        allowed: [text_overlay, face_expression, product_focus]
        default: text_overlay

    prompts:
      - name: shorts_system
        template: |
          Brand: {{ brand_name }}
          Voice: {{ brand_voice }}

          {{ base_shorts_prompt }}
        condition: "format == 'shorts'"

    output_transforms:
      - name: add_hashtags
        condition: "format == 'shorts'"
        transform_type: add
        target_field: hashtags
        expression: "['#' + tag for tag in tags[:5]]"
    ```
    """
    name: str
    version: str
    domain: str
    agent_type: str
    description: str = ""
    parameters: List[TemplateParameter] = field(default_factory=list)
    prompts: List[TemplatePrompt] = field(default_factory=list)
    output_transforms: List[OutputTransform] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at

    @property
    def template_id(self) -> str:
        """Generate a unique template ID."""
        return f"{self.domain}:{self.agent_type}:{self.name}"

    def validate(self) -> List[str]:
        """Validate the template structure and content."""
        errors = []

        # Required fields
        if not self.name:
            errors.append("Template name is required")
        if not self.version:
            errors.append("Template version is required")
        if not self.domain:
            errors.append("Template domain is required")
        if not self.agent_type:
            errors.append("Template agent_type is required")

        # Validate version format (semver)
        version_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$"
        if self.version and not re.match(version_pattern, self.version):
            errors.append(f"Invalid version format: {self.version}. Use semver (e.g., 1.0.0)")

        # Validate parameters
        param_names = set()
        for param in self.parameters:
            if param.name in param_names:
                errors.append(f"Duplicate parameter name: {param.name}")
            param_names.add(param.name)

            if param.type == ParameterType.ENUM and not param.allowed:
                errors.append(f"Enum parameter '{param.name}' requires 'allowed' values")

        # Validate prompts
        prompt_names = set()
        for prompt in self.prompts:
            if prompt.name in prompt_names:
                errors.append(f"Duplicate prompt name: {prompt.name}")
            prompt_names.add(prompt.name)

        # Validate transforms
        transform_names = set()
        for transform in self.output_transforms:
            if transform.name in transform_names:
                errors.append(f"Duplicate transform name: {transform.name}")
            transform_names.add(transform.name)

            if transform.transform_type not in ("add", "modify", "remove", "filter"):
                errors.append(
                    f"Invalid transform type '{transform.transform_type}' for '{transform.name}'"
                )

        return errors

    def validate_parameters(self, provided: Dict[str, Any]) -> List[str]:
        """Validate provided parameter values against the template."""
        errors = []

        for param in self.parameters:
            value = provided.get(param.name)
            param_errors = param.validate(value)
            errors.extend(param_errors)

        # Check for unknown parameters
        known_params = {p.name for p in self.parameters}
        for key in provided:
            if key not in known_params:
                errors.append(f"Unknown parameter: {key}")

        return errors

    def get_effective_parameters(self, provided: Dict[str, Any]) -> Dict[str, Any]:
        """Get effective parameter values with defaults applied."""
        result = {}
        for param in self.parameters:
            result[param.name] = param.get_value(provided.get(param.name))
        return result

    def get_prompt(self, name: str, context: Dict[str, Any]) -> Optional[str]:
        """Get a rendered prompt by name."""
        for prompt in self.prompts:
            if prompt.name == name and prompt.should_apply(context):
                return prompt.render(context)
        return None

    def get_applicable_prompts(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Get all applicable prompts for the given context."""
        result = {}
        for prompt in self.prompts:
            if prompt.should_apply(context):
                result[prompt.name] = prompt.render(context)
        return result

    def apply_transforms(
        self,
        output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply all applicable output transforms."""
        result = output.copy()
        for transform in self.output_transforms:
            result = transform.apply(result, context)
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "domain": self.domain,
            "agent_type": self.agent_type,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "prompts": [p.to_dict() for p in self.prompts],
            "output_transforms": [t.to_dict() for t in self.output_transforms],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTemplate":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            version=data["version"],
            domain=data["domain"],
            agent_type=data["agent_type"],
            description=data.get("description", ""),
            parameters=[
                TemplateParameter.from_dict(p)
                for p in data.get("parameters", [])
            ],
            prompts=[
                TemplatePrompt.from_dict(p)
                for p in data.get("prompts", [])
            ],
            output_transforms=[
                OutputTransform.from_dict(t)
                for t in data.get("output_transforms", [])
            ],
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at") else None
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at") else None
            ),
        )

    def to_yaml(self) -> str:
        """Export template as YAML."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_content: str) -> "AgentTemplate":
        """Create template from YAML string."""
        data = yaml.safe_load(yaml_content)
        return cls.from_dict(data)

    def to_json(self) -> str:
        """Export template as JSON."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_json(cls, json_content: str) -> "AgentTemplate":
        """Create template from JSON string."""
        data = json.loads(json_content)
        return cls.from_dict(data)
