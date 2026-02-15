"""
MemoryService Facade - Composing all memory internals.

This is the main entry point for memory operations in Tentackl.
Implements MemoryServiceInterface by delegating to:
- MemoryStore for PostgreSQL persistence
- MemoryRetriever for query routing and scoring
- MemoryInjector for prompt formatting
- MemoryLogger for structured logging
"""

import asyncio
from typing import Any, Dict, List, Optional

import structlog

from src.interfaces.database import Database
from src.domain.memory.models import (
    MemoryServiceInterface,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
    RetrievalEvidence,
    MemoryNotFoundError,
    MemoryPermissionDeniedError,
    MemoryDuplicateKeyError,
)
from src.infrastructure.memory.memory_store import MemoryStore
from src.infrastructure.memory.memory_retriever import MemoryRetriever
from src.infrastructure.memory.memory_injector import MemoryInjector
from src.infrastructure.memory.memory_logger import MemoryLogger
from src.database.memory_models import Memory


logger = structlog.get_logger()


class MemoryService(MemoryServiceInterface):
    """
    Main facade for memory service operations.

    Composes MemoryStore, MemoryRetriever, MemoryInjector, and MemoryLogger
    to provide a unified interface for all memory operations.
    """

    def __init__(self, database: Database):
        """
        Initialize the memory service.

        Args:
            database: Database instance for session management
        """
        self._database = database
        self._logger = MemoryLogger()
        self._injector = MemoryInjector()

    async def store(self, request: MemoryCreateRequest) -> MemoryResult:
        """
        Store a new memory.

        Delegates to MemoryStore.create() and converts ORM to MemoryResult.

        Args:
            request: The memory creation request

        Returns:
            MemoryResult: The created memory
        """
        store = MemoryStore(self._database)

        # Convert scope enum to string if needed
        scope_value = request.scope.value if hasattr(request.scope, 'value') else str(request.scope)

        try:
            memory = await store.create(
                organization_id=request.organization_id,
                key=request.key,
                title=request.title,
                body=request.body,
                scope=scope_value,
                scope_value=request.scope_value,
                topic=request.topic,
                tags=request.tags,
                content_type=request.content_type,
                extended_data=request.extended_data,
                metadata=request.metadata,
                created_by_user_id=request.created_by_user_id,
                created_by_agent_id=request.created_by_agent_id,
            )
        except MemoryDuplicateKeyError:
            # Key already exists — upsert by updating the existing memory
            return await self._upsert_existing(store, request, scope_value)

        # Get the initial version body
        version = await store.get_current_version(str(memory.id))
        body = version.body if version else request.body
        extended_data = version.extended_data if version else {}

        # Log the store operation
        self._logger.log_store(
            organization_id=request.organization_id,
            key=request.key,
            scope=scope_value,
            created_by_agent=request.created_by_agent_id is not None,
        )

        # Fire-and-forget: generate embedding asynchronously
        # This doesn't block the API response
        asyncio.create_task(self._generate_embedding(str(memory.id), request.body))

        return self._to_result(memory, body, extended_data=extended_data)

    async def retrieve(
        self, memory_id: str, organization_id: str,
        user_id: str, agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        """
        Retrieve a memory by ID.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)

        Returns:
            Optional[MemoryResult]: The memory or None if not found

        Raises:
            MemoryPermissionDeniedError: If the caller lacks read access
        """
        store = MemoryStore(self._database)

        memory = await store.get_by_id(memory_id, organization_id)
        if not memory:
            return None

        has_permission = await store.check_permission(
            memory=memory, user_id=user_id, agent_id=agent_id,
            required_level="read",
        )
        if not has_permission:
            raise MemoryPermissionDeniedError(
                f"User {user_id} lacks read access to memory {memory_id}"
            )

        version = await store.get_current_version(memory_id)
        body = version.body if version else ""
        extended_data = version.extended_data if version else {}

        return self._to_result(memory, body, extended_data=extended_data)

    async def retrieve_by_key(
        self, key: str, organization_id: str,
        user_id: str, agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        """
        Retrieve a memory by its unique key within an organization.

        Args:
            key: The memory key
            organization_id: The organization identifier
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)

        Returns:
            Optional[MemoryResult]: The memory or None if not found

        Raises:
            MemoryPermissionDeniedError: If the caller lacks read access
        """
        store = MemoryStore(self._database)

        memory = await store.get_by_key(key, organization_id)
        if not memory:
            return None

        has_permission = await store.check_permission(
            memory=memory, user_id=user_id, agent_id=agent_id,
            required_level="read",
        )
        if not has_permission:
            raise MemoryPermissionDeniedError(
                f"User {user_id} lacks read access to memory with key '{key}'"
            )

        version = await store.get_current_version(str(memory.id))
        body = version.body if version else ""
        extended_data = version.extended_data if version else {}

        return self._to_result(memory, body, extended_data=extended_data)

    async def update(
        self, memory_id: str, organization_id: str,
        request: MemoryUpdateRequest,
        user_id: str, agent_id: Optional[str] = None,
    ) -> MemoryResult:
        """
        Update an existing memory, creating a new version if body changes.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier
            request: The update request
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)

        Returns:
            MemoryResult: The updated memory

        Raises:
            MemoryNotFoundError: If memory not found
            MemoryPermissionDeniedError: If the caller lacks write access
        """
        store = MemoryStore(self._database)

        memory = await store.get_by_id(memory_id, organization_id)
        if not memory:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")

        has_permission = await store.check_permission(
            memory=memory, user_id=user_id, agent_id=agent_id,
            required_level="write",
        )
        if not has_permission:
            raise MemoryPermissionDeniedError(
                f"User {user_id} lacks write access to memory {memory_id}"
            )

        version = await store.update(
            memory=memory,
            body=request.body,
            title=request.title,
            tags=request.tags,
            topic=request.topic,
            extended_data=request.extended_data,
            metadata=request.metadata,
            change_summary=request.change_summary,
            changed_by=request.changed_by,
            changed_by_agent=request.changed_by_agent,
        )

        # Re-fetch memory to get updated fields
        updated_memory = await store.get_by_id(memory_id, organization_id)
        if not updated_memory:
            raise MemoryNotFoundError(f"Memory {memory_id} not found after update")

        # Fire-and-forget: generate new embedding if body changed
        # This doesn't block the API response
        if request.body is not None:
            asyncio.create_task(self._generate_embedding(memory_id, request.body))

        return self._to_result(
            updated_memory,
            version.body,
            extended_data=version.extended_data or {},
        )

    async def delete(
        self, memory_id: str, organization_id: str,
        user_id: str, agent_id: Optional[str] = None,
    ) -> bool:
        """
        Soft-delete a memory.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)

        Returns:
            bool: True if deleted, False if not found

        Raises:
            MemoryPermissionDeniedError: If the caller lacks write access
        """
        store = MemoryStore(self._database)

        memory = await store.get_by_id(memory_id, organization_id)
        if not memory:
            return False

        has_permission = await store.check_permission(
            memory=memory, user_id=user_id, agent_id=agent_id,
            required_level="write",
        )
        if not has_permission:
            raise MemoryPermissionDeniedError(
                f"User {user_id} lacks write access to memory {memory_id}"
            )

        return await store.soft_delete(memory_id, organization_id)

    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        """
        Search memories based on query parameters.

        Delegates to MemoryRetriever.search() which handles routing,
        scoring, and permission filtering.

        Args:
            query: The search query

        Returns:
            MemorySearchResponse: Search results with evidence
        """
        store = MemoryStore(self._database)
        retriever = MemoryRetriever(store, self._logger)

        return await retriever.search(query)

    async def get_version_history(
        self, memory_id: str, organization_id: str,
        user_id: str, agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Get version history for a memory.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)
            limit: Maximum number of versions to return

        Returns:
            List[Dict]: Version history entries

        Raises:
            MemoryPermissionDeniedError: If the caller lacks read access
        """
        store = MemoryStore(self._database)

        # First verify the memory exists and belongs to the org
        memory = await store.get_by_id(memory_id, organization_id)
        if not memory:
            return []

        has_permission = await store.check_permission(
            memory=memory, user_id=user_id, agent_id=agent_id,
            required_level="read",
        )
        if not has_permission:
            raise MemoryPermissionDeniedError(
                f"User {user_id} lacks read access to memory {memory_id}"
            )

        versions = await store.get_version_history(memory_id, limit)

        return [
            {
                "version": v.version,
                "body": v.body,
                "extended_data": v.extended_data or {},
                "change_summary": v.change_summary,
                "changed_by": v.changed_by,
                "changed_by_agent": v.changed_by_agent,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    async def format_for_injection(
        self, query: MemoryQuery, max_tokens: int = 2000
    ) -> str:
        """
        Format matching memories for injection into agent system prompts.

        Calls search() to get relevant memories, then uses MemoryInjector
        to format them as XML within the token budget.

        Args:
            query: The query to find relevant memories
            max_tokens: Maximum token budget for the formatted output

        Returns:
            str: Formatted memory text for prompt injection
        """
        # Search for relevant memories
        response = await self.search(query)

        if not response.memories:
            return ""

        # Format using injector
        formatted = self._injector.format_for_prompt(response.memories, max_tokens)

        # Log the injection
        injected_tokens = self._injector.estimate_tokens(formatted)

        # Count how many memories actually made it into the formatted output
        # by checking if we had to truncate
        truncated = injected_tokens < self._injector.estimate_tokens(
            self._injector.format_for_prompt(response.memories, max_tokens=100000)
        )

        self._logger.log_injection(
            memory_count=len(response.memories),
            injected_tokens=injected_tokens,
            max_tokens=max_tokens,
            truncated=truncated,
        )

        return formatted

    async def health_check(self) -> bool:
        """
        Check if the memory service is healthy and accessible.

        Attempts a simple database query to verify connectivity.

        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            async with self._database.get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            self._logger.log_error(
                operation="health_check",
                error=str(e),
                org_id=None,
            )
            return False

    async def _upsert_existing(
        self, store: MemoryStore, request: MemoryCreateRequest, scope_value: str,
    ) -> MemoryResult:
        """
        Update an existing memory when a store request hits a duplicate key.

        Looks up the memory by key, then updates its body, title, tags, and topic
        to match the incoming request, creating a new version.
        """
        memory = await store.get_by_key(request.key, request.organization_id)
        if not memory:
            raise MemoryNotFoundError(
                f"Memory with key '{request.key}' reported as duplicate but not found"
            )

        update_request = MemoryUpdateRequest(
            body=request.body,
            title=request.title,
            tags=request.tags,
            topic=request.topic,
            extended_data=request.extended_data,
            metadata=request.metadata,
            change_summary="Updated via store (upsert)",
            changed_by=request.created_by_user_id,
            changed_by_agent=request.created_by_agent_id is not None,
        )

        result = await self.update(
            memory_id=str(memory.id),
            organization_id=request.organization_id,
            request=update_request,
            user_id=request.created_by_user_id or "",
            agent_id=request.created_by_agent_id,
        )

        logger.info(
            "memory_upserted",
            key=request.key,
            memory_id=result.id,
            version=result.version,
            organization_id=request.organization_id,
        )

        return result

    async def _generate_embedding(self, memory_id: str, text: str) -> None:
        """
        Generate embedding for a memory's content asynchronously.

        This method is called fire-and-forget after memory creation or update.
        It generates an embedding vector using OpenAI's text-embedding-3-small
        model and stores it in the database.

        Args:
            memory_id: The memory identifier
            text: The text content to generate embedding for
        """
        from src.llm import OpenAIEmbeddingClient

        store = MemoryStore(self._database)

        try:
            # Create a new client instance for this embedding request
            # (HTTPClient requires async context manager pattern)
            embedding_client = OpenAIEmbeddingClient()

            if not embedding_client.is_configured:
                logger.warning(
                    "embedding_generation_skipped",
                    reason="OpenAI API key not configured",
                    memory_id=memory_id,
                )
                await store.update_embedding(memory_id, [], status="failed")
                return

            # Use async context manager for HTTP client
            async with embedding_client:
                # Generate embedding using OpenAI
                result = await embedding_client.create_embedding(text)

            # Store the embedding
            success = await store.update_embedding(
                memory_id=memory_id,
                embedding=result.embedding,
                status="completed",
            )

            if success:
                logger.info(
                    "embedding_generated",
                    memory_id=memory_id,
                    model=result.model,
                    dimensions=len(result.embedding),
                    tokens=result.usage.get("total_tokens"),
                )
            else:
                logger.error(
                    "embedding_store_failed",
                    memory_id=memory_id,
                    reason="update_embedding returned False",
                )

        except Exception as e:
            logger.error(
                "embedding_generation_failed",
                memory_id=memory_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Mark as failed so we know it needs retry
            try:
                await store.update_embedding(memory_id, [], status="failed")
            except Exception:
                pass  # Best effort to mark as failed

    def _to_result(
        self,
        memory: Memory,
        body: str,
        evidence: Optional[RetrievalEvidence] = None,
        extended_data: Optional[Dict[str, Any]] = None,
    ) -> MemoryResult:
        """
        Convert ORM Memory object to MemoryResult dataclass.

        Args:
            memory: The Memory ORM object
            body: The current body content from MemoryVersion
            evidence: Optional retrieval evidence
            extended_data: Optional extended data from version

        Returns:
            MemoryResult dataclass
        """
        return MemoryResult(
            id=str(memory.id),
            key=memory.key,
            title=memory.title,
            body=body,
            scope=memory.scope,
            topic=memory.topic,
            tags=memory.tags or [],
            version=memory.current_version,
            extended_data=extended_data or {},
            metadata=memory.extra_metadata or {},
            evidence=evidence,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
