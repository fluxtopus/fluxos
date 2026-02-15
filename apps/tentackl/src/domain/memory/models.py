"""
Memory Service Interface and Data Transfer Objects

This module defines the core interface for memory operations in Tentackl,
along with all DTOs, enums, and exception classes used by the memory system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class MemoryScopeEnum(str, Enum):
    """Scope levels for memory visibility and access control"""
    ORGANIZATION = "organization"
    USER = "user"
    AGENT = "agent"
    TOPIC = "topic"


@dataclass
class MemoryQuery:
    """Query parameters for memory retrieval and search"""

    organization_id: str
    text: Optional[str] = None
    key: Optional[str] = None
    keys: Optional[List[str]] = None
    scope: Optional[MemoryScopeEnum] = None
    scope_value: Optional[str] = None
    topic: Optional[str] = None
    topics: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    created_by_user_id: Optional[str] = None
    created_by_agent_id: Optional[str] = None
    status: str = "active"
    limit: int = 20
    offset: int = 0
    similarity_threshold: float = 0.7
    requesting_user_id: Optional[str] = None
    requesting_agent_id: Optional[str] = None


@dataclass
class RetrievalEvidence:
    """Evidence about how a memory was retrieved"""

    match_type: str
    relevance_score: float
    filters_applied: List[str] = field(default_factory=list)
    retrieval_time_ms: int = 0


@dataclass
class MemoryResult:
    """A single memory result returned from queries"""

    id: str
    key: str
    title: str
    body: str
    scope: str
    topic: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    version: int = 1
    extended_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence: Optional[RetrievalEvidence] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MemorySearchResponse:
    """Response from a memory search operation"""

    memories: List[MemoryResult] = field(default_factory=list)
    total_count: int = 0
    retrieval_path: List[str] = field(default_factory=list)
    query_time_ms: int = 0


@dataclass
class MemoryCreateRequest:
    """Request to create a new memory"""

    organization_id: str
    key: str
    title: str
    body: str
    scope: MemoryScopeEnum = MemoryScopeEnum.ORGANIZATION
    scope_value: Optional[str] = None
    topic: Optional[str] = None
    tags: Optional[List[str]] = None
    content_type: str = "text"
    extended_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_by_user_id: Optional[str] = None
    created_by_agent_id: Optional[str] = None


@dataclass
class MemoryUpdateRequest:
    """Request to update an existing memory"""

    body: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    topic: Optional[str] = None
    extended_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    change_summary: Optional[str] = None
    changed_by: Optional[str] = None
    changed_by_agent: bool = False


class MemoryServiceInterface(ABC):
    """
    Abstract interface for memory service operations.
    Follows SRP - defines the contract for all memory operations.
    """

    @abstractmethod
    async def store(self, request: MemoryCreateRequest) -> MemoryResult:
        """
        Store a new memory.

        Args:
            request: The memory creation request

        Returns:
            MemoryResult: The created memory
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def update(
        self, memory_id: str, organization_id: str,
        request: MemoryUpdateRequest,
        user_id: str, agent_id: Optional[str] = None,
    ) -> MemoryResult:
        """
        Update an existing memory, creating a new version.

        Args:
            memory_id: The memory identifier
            organization_id: The organization identifier
            request: The update request
            user_id: The requesting user's identifier
            agent_id: The requesting agent's identifier (if applicable)

        Returns:
            MemoryResult: The updated memory

        Raises:
            MemoryPermissionDeniedError: If the caller lacks write access
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        """
        Search memories based on query parameters.

        Args:
            query: The search query

        Returns:
            MemorySearchResponse: Search results with evidence
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def format_for_injection(self, query: MemoryQuery, max_tokens: int = 2000) -> str:
        """
        Format matching memories for injection into agent system prompts.

        Args:
            query: The query to find relevant memories
            max_tokens: Maximum token budget for the formatted output

        Returns:
            str: Formatted memory text for prompt injection
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the memory service is healthy and accessible.

        Returns:
            bool: True if healthy, False otherwise
        """
        pass


class MemoryServiceException(Exception):
    """Base exception for memory service operations"""
    pass


class MemoryNotFoundError(MemoryServiceException):
    """Raised when requested memory is not found"""
    pass


class MemoryPermissionDeniedError(MemoryServiceException):
    """Raised when memory access is denied"""
    pass


class MemoryValidationError(MemoryServiceException):
    """Raised when memory data is invalid"""
    pass


class MemoryDuplicateKeyError(MemoryServiceException):
    """Raised when a memory with the same key already exists in the organization"""
    pass


class MemoryVersionCollisionError(MemoryServiceException):
    """Raised when concurrent updates collide on version number"""
    pass
