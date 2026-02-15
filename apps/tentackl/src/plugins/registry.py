from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional
import inspect


Handler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]] | Dict[str, Any]]


@dataclass
class PluginDefinition:
    name: str
    description: str
    handler: Handler
    inputs_schema: Optional[Dict[str, Any]] = None
    outputs_schema: Optional[Dict[str, Any]] = None
    category: str = "custom"


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, PluginDefinition] = {}

    def register(self, plugin: PluginDefinition) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[PluginDefinition]:
        return self._plugins.get(name)

    async def execute(self, name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        plugin = self.get(name)
        if not plugin:
            raise ValueError(f"Plugin not found: {name}")
        fn = plugin.handler
        if inspect.iscoroutinefunction(fn):
            return await fn(inputs)
        result = fn(inputs)
        if inspect.isawaitable(result):
            return await result  # type: ignore
        return result  # type: ignore


registry = PluginRegistry()


# Built-in lightweight plugins (no external network):

def _echo(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {"echo": inputs}


def _webhook_receiver(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Webhook receiver plugin that acts as the entry point for webhook-triggered workflows.
    It simply passes through the webhook data, making it available to downstream nodes.

    In a real execution, the webhook data would be injected into the workflow's runtime
    parameters. For playground testing, the sample payload is passed via execute parameters.

    If _declared_outputs is provided, the plugin will output the data under those names
    to match what downstream nodes expect.
    """
    import structlog
    logger = structlog.get_logger("webhook_receiver_plugin")

    logger.debug("webhook_receiver_plugin_called",
                input_keys=list(inputs.keys()),
                has_declared_outputs="_declared_outputs" in inputs,
                has_webhook_event="webhook_event" in inputs)

    # Extract declared outputs (passed by workflow executor) and remove from inputs
    declared_outputs = inputs.pop("_declared_outputs", [])

    logger.debug("webhook_receiver_declared_outputs", declared_outputs=declared_outputs)

    # If webhook_event was passed in parameters (from test webhook), use that
    webhook_event = inputs.get("webhook_event", {})
    if webhook_event:
        event_data = webhook_event.get("data", {})
        base_result = {
            "event_type": webhook_event.get("event_type", "unknown"),
            "data": event_data,
            **event_data  # Also spread the data for easy access
        }
    else:
        # Otherwise, just pass through all inputs as-is (for direct execution scenarios)
        # Filter out internal keys
        clean_inputs = {k: v for k, v in inputs.items() if not k.startswith("_")}
        base_result = {
            "event_type": inputs.get("event_type", "webhook.event"),
            "data": clean_inputs,
            **clean_inputs
        }

    # Map result to declared output names if provided
    # This allows the AI to declare outputs like "order_data" and we'll provide it
    if declared_outputs:
        for output_name in declared_outputs:
            if isinstance(output_name, str) and output_name not in base_result:
                # Map the webhook data to the declared output name
                base_result[output_name] = base_result.get("data", {})
                logger.debug("webhook_receiver_added_output",
                            output_name=output_name,
                            data_value=base_result[output_name])

    logger.debug("webhook_receiver_returning",
                result_keys=list(base_result.keys()),
                order_data_keys=list(base_result.get("order_data", {}).keys()) if "order_data" in base_result else None)

    return base_result


def _sum_numbers(inputs: Dict[str, Any]) -> Dict[str, Any]:
    numbers = inputs.get("numbers", [])
    try:
        total = sum(float(x) for x in numbers)
    except Exception:
        raise ValueError("'numbers' must be an iterable of numeric values")
    return {"sum": total}


def _json_formatter(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    JSON formatter plugin that formats/structures data for output.
    Simply passes through the input data, optionally restructuring it.
    """
    import json

    # If there's a 'data' key, use it, otherwise use all inputs
    data = inputs.get("data", inputs)

    # If there's a 'template' or 'format' specified, try to apply it
    template = inputs.get("template", {})
    if template:
        # Simple template application - merge template with data
        result = {**template}
        for key, value in data.items():
            if key not in ["template", "format"]:
                result[key] = value
        return {"result": result, "formatted": json.dumps(result, indent=2)}

    # Just return the data as-is
    return {"result": data, "formatted": json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)}


registry.register(
    PluginDefinition(
        name="echo",
        description="Echo back provided inputs",
        handler=_echo,
        inputs_schema={"type": "object"},
        outputs_schema={"type": "object"},
        category="utility",
    )
)

registry.register(
    PluginDefinition(
        name="webhook",
        description="Webhook receiver plugin for webhook-triggered workflows. Receives webhook event data and passes it to downstream nodes.",
        handler=_webhook_receiver,
        inputs_schema={
            "type": "object",
            "properties": {
                "webhook_event": {
                    "type": "object",
                    "properties": {
                        "event_type": {"type": "string"},
                        "data": {"type": "object"}
                    }
                }
            }
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "data": {"type": "object"}
            }
        },
        category="integration",
    )
)

# Also register as webhook_receiver (alias) since AI might use either name
registry.register(
    PluginDefinition(
        name="webhook_receiver",
        description="Webhook receiver plugin for webhook-triggered workflows. Receives webhook event data and passes it to downstream nodes.",
        handler=_webhook_receiver,
        inputs_schema={
            "type": "object",
            "properties": {
                "webhook_event": {
                    "type": "object",
                    "properties": {
                        "event_type": {"type": "string"},
                        "data": {"type": "object"}
                    }
                }
            }
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "data": {"type": "object"}
            }
        },
        category="integration",
    )
)

registry.register(
    PluginDefinition(
        name="json_formatter",
        description="JSON formatter plugin that formats and structures data for output. Passes through data and provides formatted JSON output.",
        handler=_json_formatter,
        inputs_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "template": {"type": "object"}
            }
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {},
                "formatted": {"type": "string"}
            }
        },
        category="utility",
    )
)

registry.register(
    PluginDefinition(
        name="sum",
        description="Sum an array of numbers under 'numbers'",
        handler=_sum_numbers,
        inputs_schema={
            "type": "object",
            "properties": {"numbers": {"type": "array", "items": {"type": "number"}}},
        },
        outputs_schema={"type": "object", "properties": {"sum": {"type": "number"}}},
        category="math",
    )
)


# Register text processing plugins
from .text_processing_plugin import PLUGIN_HANDLERS

registry.register(
    PluginDefinition(
        name="clean_yaml_fences",
        description="Remove markdown code fences and clean YAML content",
        handler=PLUGIN_HANDLERS["clean_yaml_fences"],
        inputs_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "original_length": {"type": "integer"},
                "cleaned_length": {"type": "integer"}
            }
        },
        category="text",
    )
)

registry.register(
    PluginDefinition(
        name="extract_code_block",
        description="Extract content from markdown code blocks",
        handler=PLUGIN_HANDLERS["extract_code_block"],
        inputs_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "language": {"type": "string"}
            },
            "required": ["text"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "found": {"type": "boolean"}
            }
        },
        category="text",
    )
)


# Register Playwright automation plugins (optional - requires playwright)
try:
    from .playwright_plugin import PLUGIN_HANDLERS as PLAYWRIGHT_HANDLERS
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_HANDLERS = {}
    _PLAYWRIGHT_AVAILABLE = False

if _PLAYWRIGHT_AVAILABLE:
    registry.register(
        PluginDefinition(
            name="generate_tweet_image",
            description="Generate a visually appealing image for a tweet with custom styling",
            handler=PLAYWRIGHT_HANDLERS["generate_tweet_image"],
            inputs_schema={
                "type": "object",
                "properties": {
                    "tweet_text": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "background_color": {"type": "string"},
                    "text_color": {"type": "string"},
                    "font_size": {"type": "integer"},
                    "output_path": {"type": "string"}
                },
                "required": ["tweet_text"]
            },
            outputs_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "file_path": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "size_bytes": {"type": "integer"}
                }
            },
            category="automation",
        )
    )

    registry.register(
        PluginDefinition(
            name="screenshot_url",
            description="Take a screenshot of any URL using Playwright",
            handler=PLAYWRIGHT_HANDLERS["screenshot_url"],
            inputs_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "full_page": {"type": "boolean"},
                    "output_path": {"type": "string"},
                    "wait_for_selector": {"type": "string"}
                },
                "required": ["url"]
            },
            outputs_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "file_path": {"type": "string"},
                    "url": {"type": "string"},
                    "size_bytes": {"type": "integer"}
                }
            },
            category="automation",
        )
    )

    registry.register(
        PluginDefinition(
            name="html_to_pdf",
            description="Convert HTML content to PDF using Playwright",
            handler=PLAYWRIGHT_HANDLERS["html_to_pdf"],
            inputs_schema={
                "type": "object",
                "properties": {
                    "html": {"type": "string"},
                    "output_path": {"type": "string"},
                    "format": {"type": "string"}
                },
                "required": ["html", "output_path"]
            },
            outputs_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "file_path": {"type": "string"},
                    "size_bytes": {"type": "integer"}
                }
            },
            category="automation",
        )
    )


# Register file operations plugins
from .file_operations_plugin import PLUGIN_HANDLERS as FILE_HANDLERS

registry.register(
    PluginDefinition(
        name="write_csv",
        description="Write data to a CSV file from list of dicts or list of lists",
        handler=FILE_HANDLERS["write_csv"],
        inputs_schema={
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "file_path": {"type": "string"},
                "headers": {"type": "array", "items": {"type": "string"}},
                "delimiter": {"type": "string"},
                "append": {"type": "boolean"}
            },
            "required": ["data", "file_path"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "rows_written": {"type": "integer"},
                "size_bytes": {"type": "integer"}
            }
        },
        category="file_io",
    )
)

registry.register(
    PluginDefinition(
        name="csv_from_text",
        description="Save CSV text content (e.g., from LLM output) to a file",
        handler=FILE_HANDLERS["csv_from_text"],
        inputs_schema={
            "type": "object",
            "properties": {
                "csv_text": {"type": "string"},
                "file_path": {"type": "string"},
                "skip_validation": {"type": "boolean"}
            },
            "required": ["csv_text", "file_path"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "rows_written": {"type": "integer"},
                "size_bytes": {"type": "integer"}
            }
        },
        category="file_io",
    )
)

registry.register(
    PluginDefinition(
        name="write_json",
        description="Write data to a JSON file with optional formatting",
        handler=FILE_HANDLERS["write_json"],
        inputs_schema={
            "type": "object",
            "properties": {
                "data": {},  # Can be any JSON-serializable data
                "file_path": {"type": "string"},
                "indent": {"type": "integer"},
                "append_to_array": {"type": "boolean"}
            },
            "required": ["data", "file_path"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "size_bytes": {"type": "integer"}
            }
        },
        category="file_io",
    )
)

registry.register(
    PluginDefinition(
        name="write_text",
        description="Write text content to a file",
        handler=FILE_HANDLERS["write_text"],
        inputs_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "file_path": {"type": "string"},
                "append": {"type": "boolean"},
                "encoding": {"type": "string"}
            },
            "required": ["content", "file_path"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "size_bytes": {"type": "integer"},
                "lines_written": {"type": "integer"}
            }
        },
        category="file_io",
    )
)

registry.register(
    PluginDefinition(
        name="read_file",
        description="Read content from a text file",
        handler=FILE_HANDLERS["read_file"],
        inputs_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "encoding": {"type": "string"},
                "max_bytes": {"type": "integer"}
            },
            "required": ["file_path"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "size_bytes": {"type": "integer"},
                "lines": {"type": "integer"},
                "truncated": {"type": "boolean"}
            }
        },
        category="file_io",
    )
)

registry.register(
    PluginDefinition(
        name="list_files",
        description="List files in a directory with optional glob pattern matching",
        handler=FILE_HANDLERS["list_files"],
        inputs_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "pattern": {"type": "string"},
                "recursive": {"type": "boolean"}
            },
            "required": ["directory"]
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "result": {"type": "array", "items": {"type": "string"}},
                "count": {"type": "integer"}
            }
        },
        category="file_io",
    )
)


# Register HTTP plugin
from .http_plugin import HTTP_PLUGIN_DEFINITION

registry.register(
    PluginDefinition(**HTTP_PLUGIN_DEFINITION)
)


# Register Google plugins
from .google import GOOGLE_PLUGIN_DEFINITIONS

for plugin_def in GOOGLE_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register Den file plugins
from .den_file_plugin import DEN_PLUGIN_DEFINITIONS

for plugin_def in DEN_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register image generation plugins
from .image_generation_plugin import IMAGE_PLUGIN_DEFINITIONS

for plugin_def in IMAGE_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register agent storage plugins
from .agent_storage_plugin import AGENT_STORAGE_PLUGIN_DEFINITIONS

for plugin_def in AGENT_STORAGE_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register document DB plugins
from .document_db_plugin import DOCUMENT_DB_PLUGIN_DEFINITIONS

for plugin_def in DOCUMENT_DB_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register markdown composer plugin
from .markdown_composer_plugin import PLUGIN_DEFINITION as MARKDOWN_COMPOSER_DEFINITION

registry.register(
    PluginDefinition(**MARKDOWN_COMPOSER_DEFINITION)
)


# Register Discord followup plugins (for responding to slash commands)
from .discord_followup_plugin import DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS

for plugin_def in DISCORD_FOLLOWUP_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )


# Register CSV composer plugin
from .csv_composer_plugin import PLUGIN_DEFINITION as CSV_COMPOSER_DEFINITION

registry.register(
    PluginDefinition(**CSV_COMPOSER_DEFINITION)
)


# Register workspace CSV plugins
from .workspace_csv_plugin import WORKSPACE_CSV_PLUGIN_DEFINITIONS

for plugin_def in WORKSPACE_CSV_PLUGIN_DEFINITIONS:
    registry.register(
        PluginDefinition(**plugin_def)
    )

