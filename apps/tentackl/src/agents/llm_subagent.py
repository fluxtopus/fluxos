"""
# REVIEW:
# - LLM client lifecycle is managed per subagent; many subagents can open duplicate clients.
# - inputs_schema/outputs_schema are class-level mutables; subclasses can inadvertently share state.

LLM Subagent Base Class

Clean base class for LLM-powered subagents with:
- LLM client management
- Task-based model routing via OpenRouter
- Contract validation integration

This replaces the old BaseDomainSubagent without the domain registry baggage.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass
import time
import structlog

if TYPE_CHECKING:
    from src.domain.tasks.models import TaskStep
    from src.llm.openrouter_client import OpenRouterClient, ModelRouting
    from src.llm.model_selector import TaskType

logger = structlog.get_logger(__name__)


@dataclass
class SubagentResult:
    """Result from a subagent execution."""
    success: bool
    output: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None
    # Interactive clarification support (QA checkpoints)
    questions: Optional[list[str]] = None
    questions_context: Optional[Dict[str, Any]] = None

    def needs_clarification(self) -> bool:
        """Return True when the subagent requests user clarification."""
        return bool(self.questions)


class LLMSubagent(ABC):
    """
    Base class for LLM-powered subagents.

    Provides:
    - LLM client lifecycle management
    - Task-based model routing via OpenRouter
    - Clean interface for subagent execution

    Subclasses implement execute() and optionally override:
    - get_task_type() for custom model routing
    - get_routing() for custom routing configuration
    """

    agent_type: str = "base"  # Override in subclass
    task_type: Optional[str] = None  # Override for task-based model routing

    # Contract schemas (overridden by DatabaseConfiguredAgent from DB)
    inputs_schema: Dict[str, Dict[str, Any]] = {}
    outputs_schema: Dict[str, Dict[str, Any]] = {}

    # Routing configuration (cached after first use)
    _routing: Optional["ModelRouting"] = None

    def __init__(
        self,
        llm_client: Optional["OpenRouterClient"] = None,
        model: Optional[str] = None,
        routing: Optional["ModelRouting"] = None,
    ):
        self.llm_client = llm_client
        self._explicit_model = model
        self._custom_routing = routing
        self._own_client = False

    async def initialize(self) -> None:
        """Initialize the subagent, creating LLM client if needed."""
        if not self.llm_client:
            from src.llm.openrouter_client import OpenRouterClient
            self.llm_client = OpenRouterClient()
            self._own_client = True
            await self.llm_client.__aenter__()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._own_client and self.llm_client:
            await self.llm_client.__aexit__(None, None, None)

    def get_task_type(self) -> Optional["TaskType"]:
        """
        Get the task type for model routing.

        Override this for custom task types, or set the task_type class attribute.
        """
        if self.task_type:
            from src.llm.model_selector import TaskType
            try:
                return TaskType(self.task_type)
            except ValueError:
                logger.warning(
                    "Unknown task type",
                    task_type=self.task_type,
                    subagent=self.agent_type,
                )
        return None

    def get_routing(self) -> "ModelRouting":
        """
        Get the model routing configuration.

        Priority:
        1. Custom routing passed to constructor
        2. Explicit model (single model, no fallbacks)
        3. Routing based on task_type
        4. OpenRouter auto selection
        """
        if self._routing:
            return self._routing

        if self._custom_routing:
            self._routing = self._custom_routing
            return self._routing

        if self._explicit_model:
            from src.llm.openrouter_client import ModelRouting
            self._routing = ModelRouting.single(self._explicit_model)
            return self._routing

        from src.llm.model_selector import ModelSelector
        task_type = self.get_task_type()

        if task_type:
            self._routing = ModelSelector.get_routing(task_type)
            logger.debug(
                "Using task-based routing",
                subagent=self.agent_type,
                task_type=task_type.value,
                models=self._routing.models,
            )
        else:
            self._routing = ModelSelector.auto()
            logger.debug(
                "Using OpenRouter auto selection",
                subagent=self.agent_type,
            )

        return self._routing

    async def _llm_process(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """
        Process text through LLM with task-based model routing.

        Uses OpenRouter's native features:
        - Model fallbacks (tries next model if first fails)
        - Provider routing (sort by price/throughput/latency)

        Args:
            prompt: The user prompt (string or multimodal content list)
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            LLM response text
        """
        if not self.llm_client:
            raise ValueError(f"No LLM client available for {self.agent_type} subagent")

        routing = self.get_routing()

        from src.interfaces.llm import LLMMessage

        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))

        response = await self.llm_client.create_completion(
            messages=messages,
            routing=routing,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.debug(
            "LLM completion",
            subagent=self.agent_type,
            requested_models=routing.models,
            actual_model=response.model,
        )

        return response.content

    @abstractmethod
    async def execute(self, step: "TaskStep") -> SubagentResult:
        """
        Execute the subagent's task.

        Args:
            step: The task step containing inputs and configuration

        Returns:
            SubagentResult with output data or error
        """
        pass
