"""Infrastructure adapter for planning intent extraction."""

from __future__ import annotations

from typing import Optional

import structlog

from src.domain.tasks.ports import PlanningIntentPort
from src.domain.tasks.planning_models import PlanningIntent


logger = structlog.get_logger(__name__)


class PlanningIntentAdapter(PlanningIntentPort):
    """Adapter wrapping IntentExtractorAgent for planning intent."""

    async def extract_intent(self, goal: str) -> Optional[PlanningIntent]:
        try:
            from src.agents.intent_extractor_agent import IntentExtractorAgent

            extractor = IntentExtractorAgent()
            await extractor.initialize()

            try:
                intent = await extractor.extract_intent(goal)
                return PlanningIntent.from_intent_dict(intent)
            finally:
                await extractor.cleanup()

        except Exception as exc:
            logger.warning(
                "Failed to extract planning intent",
                error=str(exc),
            )
            return None
