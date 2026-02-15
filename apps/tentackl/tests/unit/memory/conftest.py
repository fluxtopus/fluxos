"""Fixtures for memory unit tests.

Provides mock session, sample data, and AuthUser fixtures.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_middleware import AuthUser
from src.database.memory_models import Memory, MemoryVersion, MemoryPermission


# ---------------------------------------------------------------------------
# Auth User Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_org_a():
    """Authenticated user in organization A."""
    return AuthUser(
        id="user-a-123",
        auth_type="bearer",
        username="user_a",
        metadata={"organization_id": "org-a"},
    )


@pytest.fixture
def user_org_b():
    """Authenticated user in organization B."""
    return AuthUser(
        id="user-b-456",
        auth_type="bearer",
        username="user_b",
        metadata={"organization_id": "org-b"},
    )


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_memory_id():
    """Sample memory UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_memory_data(sample_memory_id):
    """Sample memory creation data."""
    return {
        "organization_id": "org-a",
        "key": "brand-guidelines",
        "title": "Brand Guidelines",
        "body": "Use professional tone. Avoid jargon.",
        "scope": "organization",
        "scope_value": None,
        "topic": "content",
        "tags": ["branding", "style"],
        "content_type": "text",
        "extended_data": {},
        "metadata": {"priority": "high"},
        "created_by_user_id": "user-a-123",
        "created_by_agent_id": None,
    }


@pytest.fixture
def sample_memory(sample_memory_id, sample_memory_data):
    """Sample Memory ORM object."""
    memory = Memory(
        id=sample_memory_id,
        organization_id=sample_memory_data["organization_id"],
        key=sample_memory_data["key"],
        title=sample_memory_data["title"],
        scope=sample_memory_data["scope"],
        scope_value=sample_memory_data["scope_value"],
        topic=sample_memory_data["topic"],
        tags=sample_memory_data["tags"],
        content_type=sample_memory_data["content_type"],
        current_version=1,
        status="active",
        created_by_user_id=sample_memory_data["created_by_user_id"],
        created_by_agent_id=sample_memory_data["created_by_agent_id"],
        extra_metadata=sample_memory_data["metadata"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return memory


@pytest.fixture
def sample_version(sample_memory_id, sample_memory_data):
    """Sample MemoryVersion ORM object."""
    return MemoryVersion(
        id=uuid.uuid4(),
        memory_id=sample_memory_id,
        version=1,
        body=sample_memory_data["body"],
        extended_data=sample_memory_data["extended_data"],
        change_summary="Initial version",
        changed_by=sample_memory_data["created_by_user_id"],
        changed_by_agent=False,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Mock Database Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Mock AsyncSession for unit tests."""
    session = AsyncMock(spec=AsyncSession)

    # Mock the context manager behavior
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Mock execute to return an AsyncMock result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalar_one = MagicMock()
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    mock_result.scalar = MagicMock(return_value=0)

    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.merge = AsyncMock()

    # Mock rowcount on the execute result for update operations
    update_result = MagicMock()
    update_result.rowcount = 1

    return session


@pytest.fixture
def mock_database(mock_session):
    """Mock Database instance for unit tests."""
    database = MagicMock()

    # Make get_session return an async context manager
    async_context = AsyncMock()
    async_context.__aenter__ = AsyncMock(return_value=mock_session)
    async_context.__aexit__ = AsyncMock(return_value=None)

    database.get_session = MagicMock(return_value=async_context)

    return database
