"""
Agent Templates Module

Provides runtime customization of domain subagents through YAML/JSON templates.
Templates can override prompts, parameters, and output transformations.

Example template (YAML):
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

Usage via capabilities:
```python
from src.capabilities import AgentCapabilities, TemplateCapabilityImpl

# Create runtime with template capability
capabilities = AgentCapabilities(
    templates=TemplateCapabilityImpl()
)

# In subagent execute:
async def execute(self, step: TaskStep) -> SubagentResult:
    if self.runtime.capabilities.has_templates():
        templates = self.runtime.capabilities.templates

        tmpl = await templates.load_template(
            domain=self.domain,
            agent_type=self.agent_type,
            template_name=step.inputs.get("template_name"),
        )

        if tmpl:
            params = templates.get_parameters(tmpl, step.inputs)
            prompts = templates.get_applicable_prompts(tmpl, step.inputs)
            # Execute with customizations...

            output = templates.transform_output(tmpl, output, step.inputs)
```
"""

from src.agents.templates.agent_template import (
    AgentTemplate,
    TemplateParameter,
    TemplatePrompt,
    OutputTransform,
    ParameterType,
    TemplateValidationError,
)
from src.agents.templates.template_store import AgentTemplateStore

__all__ = [
    # Core template classes
    "AgentTemplate",
    "TemplateParameter",
    "TemplatePrompt",
    "OutputTransform",
    "ParameterType",
    "TemplateValidationError",
    # Store
    "AgentTemplateStore",
]
