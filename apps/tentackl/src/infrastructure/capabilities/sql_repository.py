"""SQLAlchemy repository for capabilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, select, func, text

from src.database.capability_models import AgentCapability
from src.domain.capabilities.ports import CapabilityRepositoryPort
from src.interfaces.database import Database


class SqlCapabilityRepository(CapabilityRepositoryPort):
    """SQLAlchemy-backed capability repository."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_capabilities(
        self,
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        offset: int,
    ) -> Tuple[List[AgentCapability], int]:
        async with self._database.get_session() as session:
            conditions = []

            org_conditions = []
            if org_id:
                org_conditions.append(AgentCapability.organization_id == org_id)
            if include_system:
                org_conditions.append(AgentCapability.is_system == True)  # noqa: E712

            if org_conditions:
                conditions.append(or_(*org_conditions))
            elif not include_system:
                return [], 0

            if active_only:
                conditions.append(AgentCapability.is_active == True)  # noqa: E712

            conditions.append(AgentCapability.is_latest == True)  # noqa: E712

            if domain:
                conditions.append(AgentCapability.domain == domain)

            if tags:
                conditions.append(AgentCapability.tags.overlap(tags))

            count_query = select(func.count()).select_from(AgentCapability)
            if conditions:
                count_query = count_query.where(and_(*conditions))

            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            query = select(AgentCapability)
            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(
                AgentCapability.is_system.desc(),
                AgentCapability.name.asc(),
            )
            query = query.offset(offset).limit(limit)

            result = await session.execute(query)
            capabilities = result.scalars().all()

            return capabilities, total

    async def get_capability(self, capability_id: UUID) -> Optional[AgentCapability]:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == capability_id)
            )
            return result.scalar_one_or_none()

    async def find_conflicting_agent_type(
        self,
        org_id: str,
        agent_type: str,
        exclude_id: Optional[UUID] = None,
    ) -> Optional[AgentCapability]:
        async with self._database.get_session() as session:
            conditions = [
                AgentCapability.organization_id == org_id,
                AgentCapability.agent_type == agent_type,
                AgentCapability.is_latest == True,  # noqa: E712
            ]
            if exclude_id is not None:
                conditions.append(AgentCapability.id != exclude_id)

            result = await session.execute(select(AgentCapability).where(and_(*conditions)))
            return result.scalar_one_or_none()

    async def create_capability(self, capability: AgentCapability) -> AgentCapability:
        async with self._database.get_session() as session:
            session.add(capability)
            await session.commit()
            await session.refresh(capability)
            return capability

    async def update_capability(self, capability: AgentCapability) -> AgentCapability:
        async with self._database.get_session() as session:
            session.add(capability)
            await session.commit()
            await session.refresh(capability)
            return capability

    async def create_new_version(
        self,
        old_capability_id: UUID,
        new_capability: AgentCapability,
    ) -> AgentCapability:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == old_capability_id)
            )
            old_capability = result.scalar_one_or_none()
            if old_capability is None:
                raise ValueError("Existing capability not found for versioning")

            old_capability.is_latest = False
            session.add(old_capability)

            session.add(new_capability)
            await session.commit()
            await session.refresh(new_capability)
            return new_capability

    async def search_semantic(
        self,
        query_embedding: List[float],
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        min_similarity: float,
    ) -> List[Dict[str, Any]]:
        async with self._database.get_session() as session:
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

    async def search_keyword(
        self,
        query: str,
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        async with self._database.get_session() as session:
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
