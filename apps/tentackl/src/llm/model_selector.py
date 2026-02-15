# REVIEW: Model routing is hard-coded in code, which requires deploys to update
# REVIEW: model lists or provider policies. Consider moving to config or a DB
# REVIEW: table so ops can update routing without code changes.
"""
Model Selector - Task-Based Routing using OpenRouter Native Features

Maps task types to optimal model routing configurations using OpenRouter's
native fallback and provider routing features.

See:
- https://openrouter.ai/docs/guides/routing/auto-model-selection
- https://openrouter.ai/docs/guides/routing/model-fallbacks
- https://openrouter.ai/docs/guides/routing/provider-selection
"""

from enum import Enum
from typing import Optional, Dict
from dataclasses import dataclass
import structlog

from src.llm.openrouter_client import ModelRouting, ProviderRouting

logger = structlog.get_logger(__name__)


class TaskType(Enum):
    """
    Task types that map to specific routing configurations.

    Each task type has a curated list of models optimized for that use case,
    with appropriate fallbacks and provider routing.
    """
    # Creative and writing tasks - need high quality models
    CONTENT_WRITING = "content_writing"

    # Code generation and programming tasks
    CODE_GENERATION = "code_generation"

    # Analysis and reasoning tasks
    ANALYSIS = "analysis"

    # Simple data extraction - can use faster/cheaper models
    DATA_EXTRACTION = "data_extraction"

    # Quick responses - prioritize speed
    QUICK_RESPONSE = "quick_response"

    # Simple chat - balanced cost/quality
    SIMPLE_CHAT = "simple_chat"

    # Complex reasoning requiring extended thinking
    COMPLEX_REASONING = "complex_reasoning"

    # Web research with live search - uses OpenRouter web plugin
    WEB_RESEARCH = "web_research"

    # Inbox chat agent (Flux) - conversational assistant
    INBOX_CHAT = "inbox_chat"

    # General purpose - use OpenRouter auto
    AUTO = "auto"


@dataclass
class TaskRoutingConfig:
    """Configuration for a task type's model routing."""
    models: list[str]
    provider: Optional[ProviderRouting] = None
    description: str = ""


# Task-specific routing configurations
# Note: OpenRouter limits fallback arrays to 3 models max
TASK_ROUTING_CONFIGS: Dict[TaskType, TaskRoutingConfig] = {
    TaskType.CONTENT_WRITING: TaskRoutingConfig(
        models=[
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
        ],
        provider=ProviderRouting(sort="throughput"),  # Speed matters for creative flow
        description="High-quality creative writing models with fast throughput",
    ),

    TaskType.CODE_GENERATION: TaskRoutingConfig(
        models=[
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
        ],
        provider=ProviderRouting(
            sort="throughput",
            require_parameters=True,  # Ensure code-specific params are supported
        ),
        description="Strong coding models with fallbacks",
    ),

    TaskType.ANALYSIS: TaskRoutingConfig(
        models=[
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
        ],
        provider=ProviderRouting(sort="throughput"),
        description="Models with strong reasoning capabilities",
    ),

    TaskType.DATA_EXTRACTION: TaskRoutingConfig(
        models=[
            "anthropic/claude-3.5-haiku",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
        ],
        provider=ProviderRouting(sort="price"),  # Cost-effective for extraction
        description="Fast, efficient models for structured data extraction",
    ),

    TaskType.QUICK_RESPONSE: TaskRoutingConfig(
        models=[
            "openai/gpt-oss-120b:nitro",
            "anthropic/claude-3.5-haiku:nitro",
            "openai/gpt-4o-mini:nitro",
        ],
        provider=ProviderRouting(sort="latency"),  # Fastest response time
        description="Optimized for minimal latency",
    ),

    TaskType.SIMPLE_CHAT: TaskRoutingConfig(
        models=[
            "anthropic/claude-3.5-haiku",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
        ],
        provider=ProviderRouting(sort="price"),
        description="Balanced cost and quality for simple conversations",
    ),

    TaskType.COMPLEX_REASONING: TaskRoutingConfig(
        models=[
            "anthropic/claude-sonnet-4",
            "openai/o1",
            "anthropic/claude-3.5-sonnet",
        ],
        provider=ProviderRouting(sort="throughput"),
        description="Extended thinking and complex reasoning tasks",
    ),

    TaskType.WEB_RESEARCH: TaskRoutingConfig(
        models=[
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4",
            "perplexity/sonar-pro",
        ],
        provider=ProviderRouting(sort="throughput"),
        description="Web search and research with live citations (uses OpenRouter web plugin)",
    ),

    TaskType.INBOX_CHAT: TaskRoutingConfig(
        models=[
            "x-ai/grok-4.1-fast",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
        ],
        provider=ProviderRouting(sort="throughput"),
        description="Flux - conversational assistant with tool use",
    ),

    TaskType.AUTO: TaskRoutingConfig(
        models=["openrouter/auto"],
        description="Let OpenRouter automatically select the best model",
    ),
}


class ModelSelector:
    """
    Task-based model selector using OpenRouter's native routing features.

    Instead of complex scoring algorithms, this leverages OpenRouter's:
    - Auto model selection (openrouter/auto)
    - Model fallbacks (models array)
    - Provider routing (sort by price/throughput/latency)
    - Model suffixes (:nitro for speed, :floor for cost)
    """

    @classmethod
    def get_routing(
        cls,
        task_type: Optional[TaskType] = None,
        custom_models: Optional[list[str]] = None,
        custom_provider: Optional[ProviderRouting] = None,
    ) -> ModelRouting:
        """
        Get model routing configuration for a task type.

        Args:
            task_type: Type of task to get routing for
            custom_models: Override the default models for this task type
            custom_provider: Override the provider routing config

        Returns:
            ModelRouting configuration for OpenRouterClient
        """
        if task_type is None:
            task_type = TaskType.AUTO

        config = TASK_ROUTING_CONFIGS.get(task_type, TASK_ROUTING_CONFIGS[TaskType.AUTO])

        models = custom_models or config.models
        provider = custom_provider or config.provider

        routing = ModelRouting(models=models, provider=provider)

        logger.debug(
            "Created model routing",
            task_type=task_type.value,
            models=models,
            provider_sort=provider.sort if provider else None,
        )

        return routing

    @classmethod
    def for_content_writing(cls) -> ModelRouting:
        """Get routing optimized for content writing."""
        return cls.get_routing(TaskType.CONTENT_WRITING)

    @classmethod
    def for_code_generation(cls) -> ModelRouting:
        """Get routing optimized for code generation."""
        return cls.get_routing(TaskType.CODE_GENERATION)

    @classmethod
    def for_analysis(cls) -> ModelRouting:
        """Get routing optimized for analysis tasks."""
        return cls.get_routing(TaskType.ANALYSIS)

    @classmethod
    def for_data_extraction(cls) -> ModelRouting:
        """Get routing optimized for data extraction."""
        return cls.get_routing(TaskType.DATA_EXTRACTION)

    @classmethod
    def for_quick_response(cls) -> ModelRouting:
        """Get routing optimized for quick responses."""
        return cls.get_routing(TaskType.QUICK_RESPONSE)

    @classmethod
    def for_complex_reasoning(cls) -> ModelRouting:
        """Get routing optimized for complex reasoning."""
        return cls.get_routing(TaskType.COMPLEX_REASONING)

    @classmethod
    def for_inbox_chat(cls) -> ModelRouting:
        """Get routing optimized for Flux."""
        return cls.get_routing(TaskType.INBOX_CHAT)

    @classmethod
    def for_web_research(cls) -> ModelRouting:
        """Get routing optimized for web research with live search."""
        return cls.get_routing(TaskType.WEB_RESEARCH)

    @classmethod
    def auto(cls) -> ModelRouting:
        """Let OpenRouter automatically select the best model."""
        return cls.get_routing(TaskType.AUTO)

    @classmethod
    def speed_optimized(cls, task_type: Optional[TaskType] = None) -> ModelRouting:
        """
        Get speed-optimized routing for a task type.

        Adds :nitro suffix and sorts by throughput.
        """
        if task_type is None:
            task_type = TaskType.AUTO

        config = TASK_ROUTING_CONFIGS.get(task_type, TASK_ROUTING_CONFIGS[TaskType.AUTO])

        # Add :nitro suffix to models that don't already have a suffix
        nitro_models = [
            f"{m}:nitro" if ":" not in m else m
            for m in config.models
        ]

        return ModelRouting(
            models=nitro_models,
            provider=ProviderRouting(sort="throughput")
        )

    @classmethod
    def cost_optimized(cls, task_type: Optional[TaskType] = None) -> ModelRouting:
        """
        Get cost-optimized routing for a task type.

        Adds :floor suffix and sorts by price.
        """
        if task_type is None:
            task_type = TaskType.DATA_EXTRACTION  # Default to cheap models

        config = TASK_ROUTING_CONFIGS.get(task_type, TASK_ROUTING_CONFIGS[TaskType.AUTO])

        # Add :floor suffix to models that don't already have a suffix
        floor_models = [
            f"{m}:floor" if ":" not in m else m
            for m in config.models
        ]

        return ModelRouting(
            models=floor_models,
            provider=ProviderRouting(sort="price")
        )


def get_task_routing(task_type_str: str) -> ModelRouting:
    """
    Convenience function to get routing from task type string.

    Args:
        task_type_str: Task type as string (e.g., "content_writing")

    Returns:
        ModelRouting configuration
    """
    try:
        task_type = TaskType(task_type_str)
    except ValueError:
        logger.warning(
            "Unknown task type, using auto",
            task_type=task_type_str,
        )
        task_type = TaskType.AUTO

    return ModelSelector.get_routing(task_type)
