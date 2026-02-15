"""Infrastructure adapter for step model selection."""

from __future__ import annotations

from typing import Optional

from src.domain.tasks.ports import StepModelSelectorPort
from src.llm.model_selector import ModelSelector, TaskType


# Maps agent_type → TaskType for model selection
AGENT_TYPE_TO_TASK_TYPE = {
    "web_research": TaskType.WEB_RESEARCH,
    "summarize": TaskType.SIMPLE_CHAT,
    "compose": TaskType.CONTENT_WRITING,
    "analyze": TaskType.ANALYSIS,
    "transform": TaskType.DATA_EXTRACTION,
    "http_fetch": TaskType.AUTO,
    "notify": TaskType.AUTO,
    "file_storage": TaskType.AUTO,
    "generate_image": TaskType.AUTO,
}


class StepModelSelectorAdapter(StepModelSelectorPort):
    """Selects the LLM model for a step based on agent type.

    Pure configuration lookup — no I/O or external calls.
    """

    def select_model(self, agent_type: str, explicit_model: Optional[str] = None) -> str:
        if explicit_model:
            return explicit_model
        task_type = AGENT_TYPE_TO_TASK_TYPE.get(agent_type, TaskType.SIMPLE_CHAT)
        routing = ModelSelector.get_routing(task_type)
        return routing.models[0]
