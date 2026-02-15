"""
PostgreSQL-based implementation of memory storage.

Provides persistent storage for memory artifacts with CRUD operations,
versioning, org isolation, and permission checking.
"""

import inspect
import json as _json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis_async
from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.exc import IntegrityError
import structlog

from src.interfaces.database import Database
from src.database.memory_models import Memory, MemoryVersion, MemoryPermission
from src.domain.memory.models import MemoryScopeEnum

logger = structlog.get_logger()

# Cache configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MEMORY_CACHE_TTL_SECONDS = int(os.getenv("MEMORY_CACHE_TTL_SECONDS", "300"))
MEMORY_CACHE_ENABLED = os.getenv("MEMORY_CACHE_ENABLED", "true").lower() == "true"


def _cache_enabled() -> bool:
    return MEMORY_CACHE_ENABLED and bool(REDIS_URL)


async def _new_redis() -> redis_async.Redis:
    client = redis_async.from_url(REDIS_URL, decode_responses=True)
    if inspect.isawaitable(client):
        client = await client
    return client


def _cache_key(org_id: str, key: str) -> str:
    return f"tentackl:memory:key:{org_id}:{key}"


async def _cache_get(cache_key: str) -> Optional[str]:
    if not _cache_enabled():
        return None
    redis_client = await _new_redis()
    try:
        return await redis_client.get(cache_key)
    except Exception as e:
        logger.warning("memory_cache_read_failed", key=cache_key, error=str(e))
        return None
    finally:
        await redis_client.aclose()


async def _cache_set(cache_key: str, value: str, ttl_seconds: int) -> None:
    if not _cache_enabled() or ttl_seconds <= 0:
        return
    redis_client = await _new_redis()
    try:
        await redis_client.setex(cache_key, ttl_seconds, value)
    except Exception as e:
        logger.warning("memory_cache_write_failed", key=cache_key, error=str(e))
    finally:
        await redis_client.aclose()


async def _cache_delete(cache_key: str) -> None:
    if not _cache_enabled():
        return
    redis_client = await _new_redis()
    try:
        await redis_client.delete(cache_key)
    except Exception as e:
        logger.warning("memory_cache_delete_failed", key=cache_key, error=str(e))
    finally:
        await redis_client.aclose()


class MemoryStore:
    """
    PostgreSQL-based store for memory artifacts.

    Provides:
    - CRUD operations with org isolation
    - Automatic versioning on body updates
    - Permission checking based on scope
    - Filtering and pagination
    """

    def __init__(self, database: Database):
        """
        Initialize the memory store.

        Args:
            database: Database instance for session management
        """
        self.db = database

    @staticmethod
    def _parse_uuid(value: str, field_name: str = "memory_id") -> uuid.UUID:
        """
        Parse a string as UUID, raising MemoryValidationError on invalid input.

        Args:
            value: The string to parse as UUID
            field_name: Name of the field for error messages

        Returns:
            uuid.UUID: The parsed UUID

        Raises:
            MemoryValidationError: If value is not a valid UUID
        """
        try:
            return uuid.UUID(value)
        except (ValueError, AttributeError) as e:
            from src.domain.memory.models import MemoryValidationError
            raise MemoryValidationError(
                f"Invalid {field_name}: '{value}' is not a valid UUID"
            ) from e

    async def create(
        self,
        organization_id: str,
        key: str,
        title: str,
        body: str,
        scope: str = "organization",
        scope_value: Optional[str] = None,
        topic: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_type: str = "text",
        extended_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_by_user_id: Optional[str] = None,
        created_by_agent_id: Optional[str] = None,
    ) -> Memory:
        """
        Create a new memory with initial version.

        Creates both the Memory row and MemoryVersion(version=1) in a single
        transaction.

        Args:
            organization_id: Organization identifier
            key: Unique key within the organization
            title: Memory title
            body: Memory body content
            scope: Visibility scope (organization, user, agent, topic)
            scope_value: Value for scope (e.g., user_id for user scope)
            topic: Optional topic categorization
            tags: Optional list of tags
            content_type: Content type (default: text)
            extended_data: Additional structured data
            metadata: Additional metadata
            created_by_user_id: User who created the memory
            created_by_agent_id: Agent who created the memory

        Returns:
            Memory: The created Memory ORM object
        """
        async with self.db.get_session() as session:
            # Create the memory
            memory = Memory(
                organization_id=organization_id,
                key=key,
                title=title,
                scope=scope,
                scope_value=scope_value,
                topic=topic,
                tags=tags or [],
                content_type=content_type,
                current_version=1,
                status="active",
                created_by_user_id=created_by_user_id,
                created_by_agent_id=created_by_agent_id,
                extra_metadata=metadata or {},
            )

            session.add(memory)
            await session.flush()  # Get the ID assigned

            # Create the initial version
            version = MemoryVersion(
                memory_id=memory.id,
                version=1,
                body=body,
                extended_data=extended_data or {},
                change_summary="Initial version",
                changed_by=created_by_user_id,
                changed_by_agent=created_by_agent_id is not None,
            )

            session.add(version)

            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                error_str = str(e.orig) if e.orig else str(e)
                if "idx_memory_org_key" in error_str:
                    from src.domain.memory.models import MemoryDuplicateKeyError
                    raise MemoryDuplicateKeyError(
                        f"Memory with key '{key}' already exists in organization '{organization_id}'"
                    ) from e
                raise

            await session.refresh(memory)

            logger.info(
                "Created memory",
                memory_id=str(memory.id),
                organization_id=organization_id,
                key=key,
                scope=scope,
            )

            return memory

    async def get_by_id(
        self, memory_id: str, organization_id: str
    ) -> Optional[Memory]:
        """
        Get a memory by ID, filtered by organization.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier

        Returns:
            Optional[Memory]: The memory if found and active, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(
                    and_(
                        Memory.id == self._parse_uuid(memory_id),
                        Memory.organization_id == organization_id,
                        Memory.status != "deleted",
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_by_key(
        self, key: str, organization_id: str
    ) -> Optional[Memory]:
        """
        Get a memory by unique key within an organization.

        Uses Redis cache for fast lookups; falls back to PostgreSQL on miss.

        Args:
            key: The memory key
            organization_id: The organization identifier

        Returns:
            Optional[Memory]: The memory if found and active, None otherwise
        """
        # Check cache first
        ck = _cache_key(organization_id, key)
        cached = await _cache_get(ck)
        if cached is not None:
            try:
                data = _json.loads(cached)
                memory = Memory(**data)
                return memory
            except Exception:
                pass  # Cache corrupted, fall through to DB

        async with self.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(
                    and_(
                        Memory.key == key,
                        Memory.organization_id == organization_id,
                        Memory.status != "deleted",
                    )
                )
            )
            memory = result.scalar_one_or_none()

        # Cache the result
        if memory is not None:
            try:
                cache_data = {
                    "id": str(memory.id),
                    "organization_id": memory.organization_id,
                    "key": memory.key,
                    "title": memory.title,
                    "scope": memory.scope,
                    "scope_value": memory.scope_value,
                    "topic": memory.topic,
                    "tags": memory.tags or [],
                    "content_type": memory.content_type,
                    "current_version": memory.current_version,
                    "status": memory.status,
                    "created_by_user_id": memory.created_by_user_id,
                    "created_by_agent_id": memory.created_by_agent_id,
                    "extra_metadata": memory.extra_metadata or {},
                    "created_at": memory.created_at.isoformat() if memory.created_at else None,
                    "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
                }
                await _cache_set(ck, _json.dumps(cache_data), MEMORY_CACHE_TTL_SECONDS)
            except Exception:
                pass  # Best effort cache write

        return memory

    async def get_current_version(
        self, memory_id: str
    ) -> Optional[MemoryVersion]:
        """
        Get the current version of a memory.

        Args:
            memory_id: The memory identifier

        Returns:
            Optional[MemoryVersion]: The current version or None
        """
        async with self.db.get_session() as session:
            # First get the memory to know the current version number
            mem_result = await session.execute(
                select(Memory).where(Memory.id == self._parse_uuid(memory_id))
            )
            memory = mem_result.scalar_one_or_none()

            if not memory:
                return None

            # Get the current version
            ver_result = await session.execute(
                select(MemoryVersion).where(
                    and_(
                        MemoryVersion.memory_id == self._parse_uuid(memory_id),
                        MemoryVersion.version == memory.current_version,
                    )
                )
            )
            return ver_result.scalar_one_or_none()

    async def update(
        self,
        memory: Memory,
        body: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        topic: Optional[str] = None,
        extended_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        change_summary: Optional[str] = None,
        changed_by: Optional[str] = None,
        changed_by_agent: bool = False,
    ) -> MemoryVersion:
        """
        Update a memory, creating a new version if body changes.

        If body is provided, increments current_version and creates a new
        MemoryVersion row. Other fields are updated directly on the Memory.

        Args:
            memory: The Memory ORM object to update
            body: New body content (triggers version increment)
            title: New title
            tags: New tags
            topic: New topic
            extended_data: New extended data for the version
            metadata: New metadata for the memory
            change_summary: Description of the change
            changed_by: User who made the change
            changed_by_agent: Whether change was made by an agent

        Returns:
            MemoryVersion: The new (or current) version
        """
        async with self.db.get_session() as session:
            # Lock the row with FOR UPDATE to prevent concurrent version collisions
            result = await session.execute(
                select(Memory)
                .where(Memory.id == memory.id)
                .with_for_update()
            )
            locked_memory = result.scalar_one_or_none()

            if locked_memory is None:
                from src.domain.memory.models import MemoryNotFoundError
                raise MemoryNotFoundError(f"Memory {memory.id} not found")

            # Update metadata fields if provided
            if title is not None:
                locked_memory.title = title
            if tags is not None:
                locked_memory.tags = tags
            if topic is not None:
                locked_memory.topic = topic
            if metadata is not None:
                locked_memory.extra_metadata = metadata

            locked_memory.updated_at = datetime.utcnow()

            new_version = None

            # If body is provided, create a new version
            if body is not None:
                locked_memory.current_version += 1

                new_version = MemoryVersion(
                    memory_id=locked_memory.id,
                    version=locked_memory.current_version,
                    body=body,
                    extended_data=extended_data or {},
                    change_summary=change_summary,
                    changed_by=changed_by,
                    changed_by_agent=changed_by_agent,
                )

                session.add(new_version)

            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                error_str = str(e.orig) if e.orig else str(e)
                if "uq_memory_version" in error_str:
                    from src.domain.memory.models import MemoryVersionCollisionError
                    raise MemoryVersionCollisionError(
                        f"Version collision on memory {memory.id}. "
                        "Another update was committed concurrently."
                    ) from e
                raise

            # Invalidate cache for this key
            if memory.key and memory.organization_id:
                await _cache_delete(_cache_key(memory.organization_id, memory.key))

            # Get the current version to return
            if new_version:
                await session.refresh(new_version)
                return new_version
            else:
                # Return the existing current version
                ver_result = await session.execute(
                    select(MemoryVersion).where(
                        and_(
                            MemoryVersion.memory_id == locked_memory.id,
                            MemoryVersion.version == locked_memory.current_version,
                        )
                    )
                )
                return ver_result.scalar_one()

    async def soft_delete(
        self, memory_id: str, organization_id: str
    ) -> bool:
        """
        Soft-delete a memory by setting status to 'deleted'.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier

        Returns:
            bool: True if deleted, False if not found
        """
        memory_key: Optional[str] = None

        async with self.db.get_session() as session:
            # Fetch the key for cache invalidation
            key_result = await session.execute(
                select(Memory.key).where(
                    and_(
                        Memory.id == self._parse_uuid(memory_id),
                        Memory.organization_id == organization_id,
                    )
                )
            )
            key_row = key_result.scalar_one_or_none()
            if key_row:
                memory_key = key_row

            result = await session.execute(
                update(Memory)
                .where(
                    and_(
                        Memory.id == self._parse_uuid(memory_id),
                        Memory.organization_id == organization_id,
                    )
                )
                .values(status="deleted", updated_at=datetime.utcnow())
            )

            await session.commit()

            if result.rowcount > 0:
                # Invalidate cache
                if memory_key:
                    await _cache_delete(_cache_key(organization_id, memory_key))

                logger.info(
                    "Soft-deleted memory",
                    memory_id=memory_id,
                    organization_id=organization_id,
                )
                return True

            return False

    async def list_filtered(
        self,
        organization_id: str,
        scope: Optional[str] = None,
        scope_value: Optional[str] = None,
        topic: Optional[str] = None,
        topics: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        key: Optional[str] = None,
        keys: Optional[List[str]] = None,
        created_by_user_id: Optional[str] = None,
        created_by_agent_id: Optional[str] = None,
        status: str = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Memory], int]:
        """
        List memories with filters.

        All queries include organization_id filtering for isolation.

        Args:
            organization_id: Organization identifier (required)
            scope: Filter by scope
            scope_value: Filter by scope value
            topic: Filter by single topic
            topics: Filter by list of topics
            tags: Filter by tags (intersection)
            key: Filter by single key
            keys: Filter by list of keys
            created_by_user_id: Filter by creator user
            created_by_agent_id: Filter by creator agent
            status: Filter by status (default: active)
            limit: Maximum results to return
            offset: Results offset for pagination

        Returns:
            Tuple[List[Memory], int]: (memories, total_count)
        """
        async with self.db.get_session() as session:
            # Base conditions - org isolation is always enforced
            conditions = [
                Memory.organization_id == organization_id,
                Memory.status == status,
            ]

            if scope is not None:
                conditions.append(Memory.scope == scope)
            if scope_value is not None:
                conditions.append(Memory.scope_value == scope_value)
            if topic is not None:
                conditions.append(Memory.topic == topic)
            if topics is not None and len(topics) > 0:
                conditions.append(Memory.topic.in_(topics))
            if tags is not None and len(tags) > 0:
                # Match any of the provided tags using overlap
                conditions.append(Memory.tags.overlap(tags))
            if key is not None:
                conditions.append(Memory.key == key)
            if keys is not None and len(keys) > 0:
                conditions.append(Memory.key.in_(keys))
            if created_by_user_id is not None:
                conditions.append(Memory.created_by_user_id == created_by_user_id)
            if created_by_agent_id is not None:
                conditions.append(Memory.created_by_agent_id == created_by_agent_id)

            # Build query
            query = (
                select(Memory)
                .where(and_(*conditions))
                .order_by(Memory.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )

            # Get results
            result = await session.execute(query)
            memories = list(result.scalars().all())

            # Get total count
            count_query = select(func.count(Memory.id)).where(and_(*conditions))
            count_result = await session.execute(count_query)
            total_count = count_result.scalar() or 0

            return memories, total_count

    async def get_version_history(
        self, memory_id: str, limit: int = 20
    ) -> List[MemoryVersion]:
        """
        Get version history for a memory.

        Args:
            memory_id: The memory identifier
            limit: Maximum versions to return

        Returns:
            List[MemoryVersion]: Versions ordered by version DESC
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(MemoryVersion)
                .where(MemoryVersion.memory_id == self._parse_uuid(memory_id))
                .order_by(MemoryVersion.version.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def check_permission(
        self,
        memory: Memory,
        user_id: Optional[str],
        agent_id: Optional[str],
        required_level: str = "read",
    ) -> bool:
        """
        Check if user/agent has permission to access a memory.

        Permission logic:
        - scope=organization: all org members have read, creator has write
        - scope=user: only the scope_value user has access
        - scope=agent: only the scope_value agent has access
        - scope=topic: all org members have read, creator has write
        - MemoryPermission overrides can grant additional access

        Args:
            memory: The Memory ORM object
            user_id: User requesting access
            agent_id: Agent requesting access
            required_level: Required permission level (read/write)

        Returns:
            bool: True if access is allowed
        """
        # Check scope-based access first
        scope = memory.scope

        if scope == MemoryScopeEnum.ORGANIZATION.value or scope == "organization":
            # All org members have read access
            if required_level == "read":
                return True
            # Only creator has write access
            if memory.created_by_user_id == user_id:
                return True
            if memory.created_by_agent_id == agent_id:
                return True

        elif scope == MemoryScopeEnum.USER.value or scope == "user":
            # Only the specific user has access
            if memory.scope_value == user_id:
                return True

        elif scope == MemoryScopeEnum.AGENT.value or scope == "agent":
            # Only the specific agent has access
            if memory.scope_value == agent_id:
                return True

        elif scope == MemoryScopeEnum.TOPIC.value or scope == "topic":
            # All org members have read access
            if required_level == "read":
                return True
            # Only creator has write access
            if memory.created_by_user_id == user_id:
                return True
            if memory.created_by_agent_id == agent_id:
                return True

        # Check for explicit permission overrides
        async with self.db.get_session() as session:
            grantee_conditions = []
            if user_id:
                grantee_conditions.append(MemoryPermission.grantee_user_id == user_id)
            if agent_id:
                grantee_conditions.append(MemoryPermission.grantee_agent_id == agent_id)

            if not grantee_conditions:
                return False

            result = await session.execute(
                select(MemoryPermission).where(
                    and_(
                        MemoryPermission.memory_id == memory.id,
                        or_(*grantee_conditions),
                    )
                )
            )
            permission = result.scalar_one_or_none()

            if permission:
                # Check if the granted level is sufficient
                if required_level == "read":
                    return permission.permission_level in ["read", "write"]
                if required_level == "write":
                    return permission.permission_level == "write"

        return False

    async def get_by_ids(
        self, memory_ids: List[str], organization_id: str
    ) -> Dict[str, "Memory"]:
        """
        Get multiple memories by IDs in a single query.

        Args:
            memory_ids: List of memory identifiers
            organization_id: The organization identifier

        Returns:
            Dict[str, Memory]: Memories keyed by str(memory.id)
        """
        if not memory_ids:
            return {}

        parsed_ids = [self._parse_uuid(mid) for mid in memory_ids]

        async with self.db.get_session() as session:
            result = await session.execute(
                select(Memory).where(
                    and_(
                        Memory.id.in_(parsed_ids),
                        Memory.organization_id == organization_id,
                        Memory.status != "deleted",
                    )
                )
            )
            memories = list(result.scalars().all())
            return {str(m.id): m for m in memories}

    async def batch_get_current_versions(
        self, memory_ids: List[str]
    ) -> Dict[str, "MemoryVersion"]:
        """
        Get current versions for multiple memories in a single query.

        Joins memory_versions with memories to get the current version
        for each memory in one round-trip.

        Args:
            memory_ids: List of memory identifiers

        Returns:
            Dict[str, MemoryVersion]: Versions keyed by str(memory_id)
        """
        if not memory_ids:
            return {}

        parsed_ids = [self._parse_uuid(mid) for mid in memory_ids]

        async with self.db.get_session() as session:
            result = await session.execute(
                select(MemoryVersion)
                .join(
                    Memory,
                    and_(
                        MemoryVersion.memory_id == Memory.id,
                        MemoryVersion.version == Memory.current_version,
                    ),
                )
                .where(Memory.id.in_(parsed_ids))
            )
            versions = list(result.scalars().all())
            return {str(v.memory_id): v for v in versions}

    async def batch_check_permissions(
        self,
        memories: List["Memory"],
        user_id: Optional[str],
        agent_id: Optional[str],
        required_level: str = "read",
    ) -> set:
        """
        Check permissions for multiple memories in bulk.

        First pass: scope-based checks in Python (no DB call).
        Second pass: for memories that fail scope check, single query
        for MemoryPermission overrides.

        Args:
            memories: List of Memory ORM objects
            user_id: User requesting access
            agent_id: Agent requesting access
            required_level: Required permission level (read/write)

        Returns:
            Set[str]: Set of permitted memory IDs (as strings)
        """
        if not memories:
            return set()

        permitted = set()
        needs_db_check = []

        # First pass: scope-based checks in Python
        for memory in memories:
            scope = memory.scope

            if scope in (MemoryScopeEnum.ORGANIZATION.value, "organization"):
                if required_level == "read":
                    permitted.add(str(memory.id))
                    continue
                if memory.created_by_user_id == user_id:
                    permitted.add(str(memory.id))
                    continue
                if memory.created_by_agent_id == agent_id:
                    permitted.add(str(memory.id))
                    continue

            elif scope in (MemoryScopeEnum.USER.value, "user"):
                if memory.scope_value == user_id:
                    permitted.add(str(memory.id))
                    continue

            elif scope in (MemoryScopeEnum.AGENT.value, "agent"):
                if memory.scope_value == agent_id:
                    permitted.add(str(memory.id))
                    continue

            elif scope in (MemoryScopeEnum.TOPIC.value, "topic"):
                if required_level == "read":
                    permitted.add(str(memory.id))
                    continue
                if memory.created_by_user_id == user_id:
                    permitted.add(str(memory.id))
                    continue
                if memory.created_by_agent_id == agent_id:
                    permitted.add(str(memory.id))
                    continue

            # Scope check failed — need DB lookup for overrides
            needs_db_check.append(memory)

        # Second pass: batch DB check for permission overrides
        if needs_db_check and (user_id or agent_id):
            remaining_ids = [m.id for m in needs_db_check]

            grantee_conditions = []
            if user_id:
                grantee_conditions.append(MemoryPermission.grantee_user_id == user_id)
            if agent_id:
                grantee_conditions.append(MemoryPermission.grantee_agent_id == agent_id)

            async with self.db.get_session() as session:
                result = await session.execute(
                    select(MemoryPermission).where(
                        and_(
                            MemoryPermission.memory_id.in_(remaining_ids),
                            or_(*grantee_conditions),
                        )
                    )
                )
                permissions = list(result.scalars().all())

                for perm in permissions:
                    if required_level == "read" and perm.permission_level in ("read", "write"):
                        permitted.add(str(perm.memory_id))
                    elif required_level == "write" and perm.permission_level == "write":
                        permitted.add(str(perm.memory_id))

        return permitted

    async def list_failed_embeddings(
        self, batch_size: int = 50
    ) -> List[Tuple[str, str]]:
        """
        List memories with failed embeddings for retry.

        Args:
            batch_size: Maximum number of results

        Returns:
            List of (memory_id, key) tuples
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Memory.id, Memory.key)
                .where(
                    and_(
                        Memory.embedding_status == "failed",
                        Memory.status == "active",
                    )
                )
                .limit(batch_size)
            )
            rows = result.all()
            return [(str(row[0]), row[1]) for row in rows]

    async def update_embedding(
        self,
        memory_id: str,
        embedding: List[float],
        status: str = "completed",
    ) -> bool:
        """
        Update the embedding for a memory.

        This method is called after async embedding generation.

        Args:
            memory_id: The memory identifier
            embedding: The embedding vector (1536 floats)
            status: Embedding status (completed, failed)

        Returns:
            bool: True if updated successfully
        """
        async with self.db.get_session() as session:
            from sqlalchemy import text

            # For failed status with empty embedding, just update the status
            if status == "failed" or not embedding:
                result = await session.execute(
                    text("""
                        UPDATE memories
                        SET embedding_status = :status,
                            updated_at = :updated_at
                        WHERE id = :memory_id
                    """),
                    {
                        "status": status,
                        "updated_at": datetime.utcnow(),
                        "memory_id": memory_id,
                    },
                )
                await session.commit()
                return result.rowcount > 0

            # Convert embedding list to pgvector string format
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

            result = await session.execute(
                text("""
                    UPDATE memories
                    SET content_embedding = CAST(:embedding AS vector),
                        embedding_status = :status,
                        updated_at = :updated_at
                    WHERE id = :memory_id
                """),
                {
                    "embedding": embedding_str,
                    "status": status,
                    "updated_at": datetime.utcnow(),
                    "memory_id": memory_id,
                },
            )

            await session.commit()
            return result.rowcount > 0
