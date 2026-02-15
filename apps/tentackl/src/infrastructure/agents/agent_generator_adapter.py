"""Infrastructure adapter for agent generation operations."""

from __future__ import annotations

from typing import List, Optional

from src.infrastructure.agents.agent_generator_service import GenerationResult, IdeationResult


def _generator_service_cls():
    from src.infrastructure.agents.agent_generator_service import AgentGeneratorService
    return AgentGeneratorService


class AgentGeneratorAdapter:
    """Adapter exposing AgentGeneratorService through a stable API."""

    @property
    def capabilities(self) -> List[str]:
        return _generator_service_cls().CAPABILITIES

    @property
    def agent_types(self) -> List[str]:
        return _generator_service_cls().AGENT_TYPES

    @property
    def categories(self) -> List[str]:
        return _generator_service_cls().CATEGORIES

    async def ideate(self, description: str, context: Optional[str] = None) -> IdeationResult:
        service = _generator_service_cls()()
        return await service.ideate(description=description, context=context)

    async def generate(
        self,
        description: str,
        agent_type: str,
        capabilities: List[str],
        name: str,
        category: str,
        keywords: List[str],
    ) -> GenerationResult:
        service = _generator_service_cls()()
        return await service.generate(
            description=description,
            agent_type=agent_type,
            capabilities=capabilities,
            name=name,
            category=category,
            keywords=keywords,
        )
