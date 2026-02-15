"""Application use cases for agent discovery and generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
import uuid
import yaml

from src.database.capability_models import AgentCapability
from src.domain.agents import AgentConversationReaderPort
from src.domain.capabilities.ports import CapabilityRepositoryPort
from src.interfaces.database import Database
from src.infrastructure.agents import AgentGeneratorAdapter
from src.infrastructure.capabilities import extract_keywords, get_validation_service


try:
    from src.core.tasks import generate_capability_embedding
    _celery_available = True
except ImportError:  # pragma: no cover - optional celery
    _celery_available = False
    generate_capability_embedding = None


class AgentNotFound(Exception):
    """Raised when agent data is unavailable."""


class AgentValidationError(Exception):
    """Raised when agent inputs are invalid."""


class AgentGenerationError(Exception):
    """Raised when agent generation fails."""


def _trigger_embedding_generation(capability_id: str) -> None:
    if _celery_available and generate_capability_embedding is not None:
        try:
            generate_capability_embedding.delay(capability_id)
        except Exception:
            pass


@dataclass
class AgentUseCases:
    """Application-layer orchestration for agent operations."""

    database: Database
    capability_repository: CapabilityRepositoryPort
    conversation_reader: Optional[AgentConversationReaderPort] = None
    agent_generator: AgentGeneratorAdapter = field(default_factory=AgentGeneratorAdapter)

    def list_discovery_capabilities(self) -> Dict[str, Any]:
        capability_descriptions = {
            "http_fetch": "Make HTTP requests to external APIs",
            "file_storage": "Store and retrieve files in Den file storage",
            "document_db": "Store and query documents in document collections",
            "agent_storage": "Store files in agent-specific namespace",
            "notify": "Send notifications via Mimic notification service",
            "generate_image": "Generate images using AI models",
            "schedule_job": "Schedule recurring tasks and jobs",
            "html_to_pdf": "Convert HTML content to PDF documents",
        }

        capabilities = [
            {
                "name": cap,
                "description": capability_descriptions.get(cap, f"Enable {cap} capability"),
            }
            for cap in self.agent_generator.capabilities
        ]

        return {
            "capabilities": capabilities,
            "agent_types": self.agent_generator.agent_types,
            "categories": self.agent_generator.categories,
        }

    async def search_agents(
        self,
        query: str,
        limit: int,
        min_similarity: float,
        domain: Optional[str],
        tags: Optional[List[str]],
        include_system: bool,
        organization_id: Optional[str],
    ) -> Dict[str, Any]:
        from src.infrastructure.flux_runtime.capability_recommender import CapabilityRecommender

        recommender = CapabilityRecommender(self.database)

        results = await recommender.search_and_rank(
            query=query,
            domain=domain,
            tags=tags,
            organization_id=organization_id,
            include_system=include_system,
            limit=limit,
        )

        filtered_results = [r for r in results if r.similarity >= min_similarity]

        agents = [
            {
                "id": r.id,
                "name": r.name,
                "version": "1.0.0",
                "type": r.agent_type,
                "description": r.description,
                "brief": r.description[:200] if r.description else None,
                "category": r.domain,
                "tags": r.tags,
                "capabilities": [],
                "similarity": r.similarity,
            }
            for r in filtered_results
        ]

        return {
            "agents": agents,
            "query": query,
            "total": len(filtered_results),
        }

    async def get_agent_conversations(
        self,
        agent_id: str,
        workflow_id: Optional[str],
    ) -> Dict[str, Any]:
        if not self.conversation_reader:
            raise AgentNotFound("Conversation store not available")

        conversations = await self.conversation_reader.list_agent_conversations(
            agent_id=agent_id,
            workflow_id=workflow_id,
        )
        return {"conversations": conversations}

    async def generate_agent_events(
        self,
        description: str,
        context: Optional[str],
        user_id: str,
        organization_id: Optional[str],
    ) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        yield "progress", {"phase": "ideating", "message": "Understanding your request..."}
        ideation = await self.agent_generator.ideate(description, context)
        yield "progress", {
            "phase": "ideated",
            "message": f"Designing a {ideation.suggested_type} agent: {ideation.suggested_name}",
        }

        yield "progress", {"phase": "generating", "message": "Generating agent specification..."}
        result = await self.agent_generator.generate(
            description=description,
            agent_type=ideation.suggested_type,
            capabilities=ideation.suggested_capabilities,
            name=ideation.suggested_name,
            category=ideation.suggested_category,
            keywords=ideation.suggested_keywords,
        )
        yield "progress", {
            "phase": "generated",
            "message": f"Agent '{result.name}' specification ready",
        }

        yield "progress", {"phase": "validating", "message": "Validating specification..."}
        raw_spec = yaml.safe_load(result.yaml_spec)
        if not isinstance(raw_spec, dict):
            yield "error", {"message": "Generated specification is not a valid object"}
            return

        agent_type_name = raw_spec.get("name", result.name)

        raw_inputs = raw_spec.get("inputs")
        if isinstance(raw_inputs, dict):
            inputs = raw_inputs
        elif isinstance(raw_inputs, list):
            inputs = {field: {"type": "string", "description": field} for field in raw_inputs}
        else:
            state_required = raw_spec.get("state_schema", {}).get("required", [])
            if isinstance(state_required, list):
                inputs = {field: {"type": "string", "description": field} for field in state_required}
            elif isinstance(state_required, dict):
                inputs = state_required
            else:
                inputs = {"input": {"type": "string", "description": "Primary input"}}

        raw_outputs = raw_spec.get("outputs")
        if isinstance(raw_outputs, dict):
            outputs = raw_outputs
        elif isinstance(raw_outputs, list):
            outputs = {field: {"type": "string", "description": field} for field in raw_outputs}
        else:
            state_output = raw_spec.get("state_schema", {}).get("output", [])
            if isinstance(state_output, list):
                outputs = {field: {"type": "string", "description": field} for field in state_output}
            elif isinstance(state_output, dict):
                outputs = state_output
            else:
                outputs = {}

        spec = {
            "agent_type": agent_type_name,
            "name": raw_spec.get("name", result.name),
            "description": raw_spec.get("description", ideation.brief),
            "domain": raw_spec.get("domain", ideation.suggested_category),
            "task_type": raw_spec.get("task_type", "general"),
            "system_prompt": raw_spec.get("prompt_template") or raw_spec.get("system_prompt", ""),
            "inputs": inputs,
            "outputs": outputs,
            "examples": raw_spec.get("examples", []),
            "execution_hints": raw_spec.get("execution_hints") or raw_spec.get("resources", {}),
        }

        validation_service = get_validation_service()
        validation_result = validation_service.validate(spec)
        errors = validation_result.get_error_messages()
        if errors:
            yield "error", {
                "message": f"Validation failed: {'; '.join(errors)}",
                "errors": errors,
            }
            return

        yield "progress", {"phase": "registering", "message": "Saving agent..."}

        if not organization_id:
            yield "error", {"message": "User must belong to an organization to create agents"}
            return

        agent_type = spec["agent_type"]

        existing = await self.capability_repository.find_conflicting_agent_type(
            org_id=organization_id,
            agent_type=agent_type,
        )
        if existing:
            yield "error", {
                "message": f"An agent with type '{agent_type}' already exists in your organization",
            }
            return

        capability = AgentCapability(
            id=uuid.uuid4(),
            organization_id=organization_id,
            agent_type=agent_type,
            name=spec.get("name", agent_type),
            description=spec.get("description"),
            domain=spec.get("domain"),
            task_type=spec.get("task_type", "general"),
            system_prompt=spec.get("system_prompt", ""),
            inputs_schema=spec.get("inputs", {}),
            outputs_schema=spec.get("outputs", {}),
            examples=spec.get("examples", []),
            execution_hints=spec.get("execution_hints", {}),
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
            created_by=user_id,
            tags=ideation.suggested_keywords[:10],
            spec_yaml=result.yaml_spec,
            usage_count=0,
            success_count=0,
            failure_count=0,
            last_used_at=None,
            embedding_status="pending",
            keywords=extract_keywords(spec),
        )

        capability = await self.capability_repository.create_capability(capability)

        _trigger_embedding_generation(str(capability.id))
        await self._refresh_registry()

        yield "complete", {
            "capability": {
                "id": str(capability.id),
                "agent_type": capability.agent_type,
                "name": capability.name,
                "description": capability.description,
                "domain": capability.domain,
                "tags": capability.tags or [],
            },
            "yaml_spec": result.yaml_spec,
        }

    async def _refresh_registry(self) -> None:
        try:
            from src.capabilities.unified_registry import get_registry

            registry = await get_registry()
            await registry.refresh()
        except Exception:
            pass
