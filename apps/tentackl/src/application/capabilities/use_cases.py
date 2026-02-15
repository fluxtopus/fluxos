"""Application use cases for capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import uuid
import yaml

from sqlalchemy import and_, or_, select, func, text

from src.database.capability_models import AgentCapability
from src.domain.capabilities.ports import CapabilityRepositoryPort
from src.llm import get_embedding_client as _get_embedding_client
from src.infrastructure.capabilities import get_validation_service, extract_keywords


try:
    from src.core.tasks import generate_capability_embedding
    _celery_available = True
except ImportError:  # pragma: no cover - depends on optional celery
    _celery_available = False
    generate_capability_embedding = None


class CapabilityNotFound(Exception):
    """Raised when a capability is not found."""


class CapabilityForbidden(Exception):
    """Raised when a user cannot access a capability."""


class CapabilityValidationError(Exception):
    """Raised when capability input is invalid."""


class CapabilityConflict(Exception):
    """Raised when a capability conflicts with an existing one."""


def _trigger_embedding_generation(capability_id: str) -> None:
    if _celery_available and generate_capability_embedding is not None:
        try:
            generate_capability_embedding.delay(capability_id)
        except Exception:
            # Fail open; embedding generation is best-effort
            pass


def _capability_to_detail(capability: AgentCapability, can_edit: bool) -> Dict[str, Any]:
    return {
        "id": capability.id,
        "agent_type": capability.agent_type,
        "name": capability.name,
        "description": capability.description,
        "domain": capability.domain,
        "task_type": capability.task_type,
        "system_prompt": capability.system_prompt,
        "inputs_schema": capability.inputs_schema or {},
        "outputs_schema": capability.outputs_schema or {},
        "examples": capability.examples or [],
        "execution_hints": capability.execution_hints or {},
        "is_system": capability.is_system,
        "is_active": capability.is_active,
        "organization_id": capability.organization_id,
        "version": capability.version,
        "is_latest": capability.is_latest,
        "created_by": capability.created_by,
        "tags": capability.tags or [],
        "spec_yaml": capability.spec_yaml,
        "usage_count": capability.usage_count,
        "success_count": capability.success_count,
        "failure_count": capability.failure_count,
        "last_used_at": capability.last_used_at,
        "created_at": capability.created_at,
        "updated_at": capability.updated_at,
        "can_edit": can_edit,
    }


def _capability_to_list_item(capability: AgentCapability, can_edit: bool) -> Dict[str, Any]:
    return {
        "id": capability.id,
        "agent_type": capability.agent_type,
        "name": capability.name,
        "description": capability.description,
        "domain": capability.domain,
        "task_type": capability.task_type,
        "is_system": capability.is_system,
        "is_active": capability.is_active,
        "organization_id": capability.organization_id,
        "version": capability.version,
        "is_latest": capability.is_latest,
        "tags": capability.tags or [],
        "usage_count": capability.usage_count,
        "success_count": capability.success_count,
        "failure_count": capability.failure_count,
        "last_used_at": capability.last_used_at,
        "created_at": capability.created_at,
        "updated_at": capability.updated_at,
        "can_edit": can_edit,
    }


def _extract_keywords(spec: Dict[str, Any]) -> List[str]:
    return extract_keywords(spec)


def validate_capability_spec(spec: Dict[str, Any]) -> List[str]:
    """Validate a capability spec and return collected error messages."""
    validation_service = get_validation_service()
    result = validation_service.validate(spec)
    return result.get_error_messages()


def get_embedding_client():
    """Resolve embedding client (kept as a function for test patching)."""
    return _get_embedding_client()


async def _generate_query_embedding(query: str) -> Optional[List[float]]:
    try:
        embedding_client = get_embedding_client()
        if not embedding_client.is_configured:
            return None

        async with embedding_client as client:
            result = await client.create_embedding(query)
            return result.embedding
    except Exception:
        return None


async def _semantic_search(
    session,
    query_embedding: List[float],
    org_id: Optional[str],
    include_system: bool,
    active_only: bool,
    domain: Optional[str],
    tags: Optional[List[str]],
    limit: int,
    min_similarity: float,
) -> List[Dict[str, Any]]:
    try:
        check_result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'capabilities_agents' "
                "AND column_name = 'description_embedding'"
            )
        )
        if not check_result.fetchone():
            return []
    except Exception:
        return []

    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    filters = ["is_latest = true", "description_embedding IS NOT NULL"]
    params: Dict[str, Any] = {
        "embedding": embedding_str,
        "limit": limit,
        "min_sim": min_similarity,
    }

    org_conditions = []
    if org_id:
        org_conditions.append("organization_id = :org_id")
        params["org_id"] = org_id
    if include_system:
        org_conditions.append("is_system = true")

    if org_conditions:
        filters.append(f"({' OR '.join(org_conditions)})")
    elif not include_system:
        return []

    if active_only:
        filters.append("is_active = true")

    if domain:
        filters.append("domain = :domain")
        params["domain"] = domain

    if tags:
        filters.append("tags && :tags")
        params["tags"] = tags

    filter_clause = " AND ".join(filters)

    result = await session.execute(
        text(
            f"""
            SELECT
                id,
                agent_type,
                name,
                description,
                domain,
                task_type,
                is_system,
                is_active,
                organization_id,
                version,
                is_latest,
                tags,
                keywords,
                usage_count,
                success_count,
                failure_count,
                last_used_at,
                1 - (description_embedding <=> CAST(:embedding AS vector)) as similarity
            FROM capabilities_agents
            WHERE {filter_clause}
                AND 1 - (description_embedding <=> CAST(:embedding AS vector)) >= :min_sim
            ORDER BY description_embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        params,
    )

    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "agent_type": row.agent_type,
            "name": row.name,
            "description": row.description,
            "domain": row.domain,
            "task_type": row.task_type,
            "is_system": row.is_system,
            "is_active": row.is_active,
            "organization_id": row.organization_id,
            "version": row.version,
            "is_latest": row.is_latest,
            "tags": row.tags or [],
            "keywords": row.keywords or [],
            "usage_count": row.usage_count,
            "success_count": row.success_count,
            "failure_count": row.failure_count,
            "last_used_at": row.last_used_at,
            "similarity": float(row.similarity),
            "match_type": "semantic",
        }
        for row in rows
    ]


async def _keyword_search(
    session,
    query: str,
    org_id: Optional[str],
    include_system: bool,
    active_only: bool,
    domain: Optional[str],
    tags: Optional[List[str]],
    limit: int,
) -> List[Dict[str, Any]]:
    search_terms = [term.lower().strip() for term in query.split() if term.strip()]
    if not search_terms:
        return []

    conditions = [AgentCapability.is_latest == True]  # noqa: E712

    org_conditions = []
    if org_id:
        org_conditions.append(AgentCapability.organization_id == org_id)
    if include_system:
        org_conditions.append(AgentCapability.is_system == True)  # noqa: E712

    if org_conditions:
        conditions.append(or_(*org_conditions))
    elif not include_system:
        return []

    if active_only:
        conditions.append(AgentCapability.is_active == True)  # noqa: E712

    if domain:
        conditions.append(AgentCapability.domain == domain)

    if tags:
        conditions.append(AgentCapability.tags.overlap(tags))

    text_conditions = []
    for term in search_terms:
        pattern = f"%{term}%"
        text_conditions.append(
            or_(
                func.lower(AgentCapability.name).like(pattern),
                func.lower(AgentCapability.description).like(pattern),
                func.lower(AgentCapability.agent_type).like(pattern),
                func.array_to_string(AgentCapability.tags, ' ').ilike(pattern),
                func.array_to_string(AgentCapability.keywords, ' ').ilike(pattern),
            )
        )

    if text_conditions:
        conditions.append(or_(*text_conditions))

    query_obj = select(AgentCapability).where(and_(*conditions))
    query_obj = query_obj.order_by(
        AgentCapability.usage_count.desc(),
        AgentCapability.name.asc(),
    )
    query_obj = query_obj.limit(limit)

    result = await session.execute(query_obj)
    capabilities = result.scalars().all()

    results = []
    for cap in capabilities:
        matches = 0
        total_terms = len(search_terms)

        for term in search_terms:
            if term in (cap.name or "").lower():
                matches += 2
            elif term in (cap.description or "").lower():
                matches += 1
            elif term in (cap.agent_type or "").lower():
                matches += 1
            elif cap.tags and any(term in tag.lower() for tag in cap.tags):
                matches += 1
            elif cap.keywords and any(term in kw.lower() for kw in cap.keywords):
                matches += 1

        max_score = 2 * total_terms
        similarity = min(matches / max_score, 1.0) if max_score > 0 else 0.0

        results.append({
            "id": cap.id,
            "agent_type": cap.agent_type,
            "name": cap.name,
            "description": cap.description,
            "domain": cap.domain,
            "task_type": cap.task_type,
            "is_system": cap.is_system,
            "is_active": cap.is_active,
            "organization_id": cap.organization_id,
            "version": cap.version,
            "is_latest": cap.is_latest,
            "tags": cap.tags or [],
            "keywords": cap.keywords or [],
            "usage_count": cap.usage_count,
            "success_count": cap.success_count,
            "failure_count": cap.failure_count,
            "last_used_at": cap.last_used_at,
            "similarity": similarity,
            "match_type": "keyword",
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results


@dataclass
class CapabilityUseCases:
    """Application-layer orchestration for capability operations."""

    repository: CapabilityRepositoryPort

    async def list_capabilities(
        self,
        org_id: Optional[str],
        domain: Optional[str],
        tags: Optional[List[str]],
        include_system: bool,
        active_only: bool,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        capabilities, total = await self.repository.list_capabilities(
            org_id=org_id,
            include_system=include_system,
            active_only=active_only,
            domain=domain,
            tags=tags,
            limit=limit,
            offset=offset,
        )

        capability_items = []
        for cap in capabilities:
            can_edit = (
                not cap.is_system
                and org_id is not None
                and cap.organization_id is not None
                and str(cap.organization_id) == str(org_id)
            )
            capability_items.append(_capability_to_list_item(cap, can_edit))

        return {
            "capabilities": capability_items,
            "count": len(capability_items),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def search_capabilities(
        self,
        query: str,
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        min_similarity: float,
        prefer_semantic: bool,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        search_type = "keyword"

        if prefer_semantic:
            query_embedding = await _generate_query_embedding(query)
            if query_embedding:
                results = await self.repository.search_semantic(
                    query_embedding=query_embedding,
                    org_id=org_id,
                    include_system=include_system,
                    active_only=active_only,
                    domain=domain,
                    tags=tags,
                    limit=limit,
                    min_similarity=min_similarity,
                )
                search_type = "semantic"

        if not results:
            results = await self.repository.search_keyword(
                query=query,
                org_id=org_id,
                include_system=include_system,
                active_only=active_only,
                domain=domain,
                tags=tags,
                limit=limit,
            )
            search_type = "keyword"

        return {
            "results": results,
            "count": len(results),
            "query": query,
            "search_type": search_type,
        }

    async def create_capability(
        self,
        spec_yaml: str,
        tags: Optional[List[str]],
        org_id: Optional[str],
        user_id: str,
    ) -> Dict[str, Any]:
        try:
            spec = yaml.safe_load(spec_yaml)
        except yaml.YAMLError as exc:
            raise CapabilityValidationError(f"Invalid YAML specification: {str(exc)}") from exc

        if not isinstance(spec, dict):
            raise CapabilityValidationError("YAML specification must be an object")

        validation_errors = self._validate_capability_spec(spec)
        if validation_errors:
            raise CapabilityValidationError(
                {
                    "message": "Invalid capability specification",
                    "errors": validation_errors,
                }
            )

        if not org_id:
            raise CapabilityForbidden("User must belong to an organization to create capabilities")

        agent_type = spec.get("agent_type")

        existing_capability = await self.repository.find_conflicting_agent_type(
            org_id=org_id,
            agent_type=agent_type,
        )
        if existing_capability:
            raise CapabilityConflict(
                f"Capability with agent_type '{agent_type}' already exists in your organization"
            )

        capability = AgentCapability(
            id=uuid.uuid4(),
            organization_id=org_id,
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
            tags=tags or spec.get("tags", []),
            spec_yaml=spec_yaml,
            usage_count=0,
            success_count=0,
            failure_count=0,
            last_used_at=None,
            embedding_status="pending",
            keywords=_extract_keywords(spec),
        )

        capability = await self.repository.create_capability(capability)

        await self._refresh_registry()
        _trigger_embedding_generation(str(capability.id))

        return {
            "capability": _capability_to_detail(capability, can_edit=True),
            "message": "Capability created successfully",
        }

    async def update_capability(
        self,
        capability_id: UUID,
        spec_yaml: Optional[str],
        tags: Optional[List[str]],
        is_active: Optional[bool],
        org_id: Optional[str],
        user_id: str,
    ) -> Dict[str, Any]:
        if not org_id:
            raise CapabilityForbidden("User must belong to an organization to update capabilities")
        capability = await self.repository.get_capability(capability_id)
        if not capability:
            raise CapabilityNotFound(f"Capability with id '{capability_id}' not found")

        if capability.is_system:
            raise CapabilityForbidden("System capabilities cannot be modified")

        if str(capability.organization_id) != str(org_id):
            raise CapabilityForbidden(
                "You can only update capabilities owned by your organization"
            )

        version_created = False
        spec_changed = False
        new_spec: Optional[Dict[str, Any]] = None

        if spec_yaml is not None:
            try:
                new_spec = yaml.safe_load(spec_yaml)
            except yaml.YAMLError as exc:
                raise CapabilityValidationError(
                    f"Invalid YAML specification: {str(exc)}"
                ) from exc

            if not isinstance(new_spec, dict):
                raise CapabilityValidationError("YAML specification must be an object")

            validation_errors = self._validate_capability_spec(new_spec)
            if validation_errors:
                raise CapabilityValidationError(
                    {
                        "message": "Invalid capability specification",
                        "errors": validation_errors,
                    }
                )

            if spec_yaml.strip() != (capability.spec_yaml or "").strip():
                spec_changed = True

                new_agent_type = new_spec.get("agent_type")
                if new_agent_type != capability.agent_type:
                    conflict = await self.repository.find_conflicting_agent_type(
                        org_id=org_id,
                        agent_type=new_agent_type,
                        exclude_id=capability_id,
                    )
                    if conflict:
                        raise CapabilityConflict(
                            f"Capability with agent_type '{new_agent_type}' already exists in your organization"
                        )

        if spec_changed:
            assert new_spec is not None

            new_capability = AgentCapability(
                id=uuid.uuid4(),
                organization_id=org_id,
                agent_type=new_spec.get("agent_type", capability.agent_type),
                name=new_spec.get("name", new_spec.get("agent_type")),
                description=new_spec.get("description"),
                domain=new_spec.get("domain"),
                task_type=new_spec.get("task_type", "general"),
                system_prompt=new_spec.get("system_prompt", ""),
                inputs_schema=new_spec.get("inputs", {}),
                outputs_schema=new_spec.get("outputs", {}),
                examples=new_spec.get("examples", []),
                execution_hints=new_spec.get("execution_hints", {}),
                is_system=False,
                is_active=is_active if is_active is not None else capability.is_active,
                version=capability.version + 1,
                is_latest=True,
                created_by=user_id,
                tags=tags if tags is not None else (capability.tags or []),
                spec_yaml=spec_yaml,
                usage_count=0,
                success_count=0,
                failure_count=0,
                last_used_at=None,
                embedding_status="pending",
                keywords=_extract_keywords(new_spec),
            )

            capability = await self.repository.create_new_version(
                old_capability_id=capability_id,
                new_capability=new_capability,
            )
            version_created = True
            _trigger_embedding_generation(str(capability.id))
        else:
            if tags is not None:
                capability.tags = tags
            if is_active is not None:
                capability.is_active = is_active

            capability = await self.repository.update_capability(capability)

        await self._refresh_registry()

        return {
            "capability": _capability_to_detail(capability, can_edit=True),
            "message": "Capability updated successfully"
            if not version_created
            else f"New version {capability.version} created",
            "version_created": version_created,
        }

    async def get_capability(
        self,
        capability_id: UUID,
        org_id: Optional[str],
    ) -> Dict[str, Any]:
        capability = await self.repository.get_capability(capability_id)
        if not capability:
            raise CapabilityNotFound(f"Capability with id '{capability_id}' not found")

        if not capability.is_system:
            if capability.organization_id is None:
                raise CapabilityForbidden("Cannot access this capability")
            if org_id is None or str(capability.organization_id) != str(org_id):
                raise CapabilityForbidden(
                    "You can only view capabilities owned by your organization"
                )

        can_edit = (
            not capability.is_system
            and org_id is not None
            and capability.organization_id is not None
            and str(capability.organization_id) == str(org_id)
        )

        return {
            "capability": _capability_to_detail(capability, can_edit=can_edit)
        }

    async def delete_capability(
        self,
        capability_id: UUID,
        org_id: Optional[str],
    ) -> Dict[str, Any]:
        if not org_id:
            raise CapabilityForbidden("User must belong to an organization to delete capabilities")
        capability = await self.repository.get_capability(capability_id)
        if not capability:
            raise CapabilityNotFound(f"Capability with id '{capability_id}' not found")

        if capability.is_system:
            raise CapabilityForbidden("System capabilities cannot be deleted")

        if str(capability.organization_id) != str(org_id):
            raise CapabilityForbidden(
                "You can only delete capabilities owned by your organization"
            )

        capability.is_active = False
        capability = await self.repository.update_capability(capability)

        await self._refresh_registry()

        return {
            "id": capability.id,
            "agent_type": capability.agent_type,
            "message": "Capability deleted successfully",
        }

    def _validate_capability_spec(self, spec: Dict[str, Any]) -> List[str]:
        return validate_capability_spec(spec)

    async def _refresh_registry(self) -> None:
        try:
            from src.capabilities.unified_registry import get_registry

            registry = await get_registry()
            await registry.refresh()
        except Exception:
            # Registry refresh is best-effort; avoid failing requests
            pass
