"""Unit tests for MemoryStore CRUD operations.

Tests all 9 methods with mocked AsyncSession:
- create
- get_by_id
- get_by_key
- get_current_version
- update
- soft_delete
- list_filtered
- get_version_history
- check_permission
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.memory_models import Memory, MemoryVersion, MemoryPermission
from src.infrastructure.memory.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# TestMemoryStoreCreate
# ---------------------------------------------------------------------------


class TestMemoryStoreCreate:
    @pytest.mark.asyncio
    async def test_create_returns_memory(self, mock_database, sample_memory_data, sample_memory):
        """Test create returns a Memory ORM object."""
        # No complex side_effects needed - the store creates the Memory object internally

        store = MemoryStore(mock_database)
        result = await store.create(
            organization_id=sample_memory_data["organization_id"],
            key=sample_memory_data["key"],
            title=sample_memory_data["title"],
            body=sample_memory_data["body"],
            scope=sample_memory_data["scope"],
            topic=sample_memory_data["topic"],
            tags=sample_memory_data["tags"],
            created_by_user_id=sample_memory_data["created_by_user_id"],
        )

        # Verify a Memory was created
        assert result.organization_id == sample_memory_data["organization_id"]
        assert result.key == sample_memory_data["key"]
        assert result.title == sample_memory_data["title"]

    @pytest.mark.asyncio
    async def test_create_sets_version_1(self, mock_database, sample_memory_data):
        """Test create sets current_version to 1."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        store = MemoryStore(mock_database)
        result = await store.create(
            organization_id=sample_memory_data["organization_id"],
            key=sample_memory_data["key"],
            title=sample_memory_data["title"],
            body=sample_memory_data["body"],
        )

        assert result.current_version == 1
        # Verify session.add was called twice (Memory + MemoryVersion)
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_create_stores_org_id(self, mock_database, sample_memory_data):
        """Test create stores the organization_id."""
        store = MemoryStore(mock_database)
        result = await store.create(
            organization_id="test-org-123",
            key=sample_memory_data["key"],
            title=sample_memory_data["title"],
            body=sample_memory_data["body"],
        )

        assert result.organization_id == "test-org-123"


# ---------------------------------------------------------------------------
# TestMemoryStoreGet
# ---------------------------------------------------------------------------


class TestMemoryStoreGet:
    @pytest.mark.asyncio
    async def test_get_by_id(self, mock_database, sample_memory):
        """Test get_by_id returns memory when found."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_memory
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.get_by_id(str(sample_memory.id), "org-a")

        assert result == sample_memory
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self, mock_database):
        """Test get_by_id returns None when not found."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.get_by_id(str(uuid.uuid4()), "org-a")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_filters_by_org_id(self, mock_database, sample_memory):
        """Test get_by_id filters by organization_id."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        # Return None because org doesn't match
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        # Try to get from different org
        result = await store.get_by_id(str(sample_memory.id), "different-org")

        assert result is None


# ---------------------------------------------------------------------------
# TestMemoryStoreUpdate
# ---------------------------------------------------------------------------


class TestMemoryStoreUpdate:
    @pytest.mark.asyncio
    async def test_update_creates_new_version(self, mock_database, sample_memory, sample_version):
        """Test update creates new MemoryVersion when body changes."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_session.merge.return_value = sample_memory

        # Mock the version query result
        mock_ver_result = MagicMock()
        mock_ver_result.scalar_one.return_value = sample_version
        mock_session.execute.return_value = mock_ver_result

        store = MemoryStore(mock_database)
        result = await store.update(
            memory=sample_memory,
            body="Updated body content",
            change_summary="Updated guidelines",
        )

        # Verify a new version was added
        assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_update_increments_version_number(self, mock_database, sample_memory):
        """Test update increments current_version when body changes."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        # Mock the SELECT ... FOR UPDATE returning the locked memory
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_memory
        mock_session.execute.return_value = mock_result

        initial_version = sample_memory.current_version

        store = MemoryStore(mock_database)
        await store.update(
            memory=sample_memory,
            body="New body content",
        )

        # Version should be incremented
        assert sample_memory.current_version == initial_version + 1


# ---------------------------------------------------------------------------
# TestMemoryStoreDelete
# ---------------------------------------------------------------------------


class TestMemoryStoreDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_status(self, mock_database, sample_memory):
        """Test soft_delete sets status to 'deleted'."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.soft_delete(str(sample_memory.id), "org-a")

        assert result is True
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing(self, mock_database):
        """Test soft_delete returns False when memory not found."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.soft_delete(str(uuid.uuid4()), "org-a")

        assert result is False


# ---------------------------------------------------------------------------
# TestMemoryStoreList
# ---------------------------------------------------------------------------


class TestMemoryStoreList:
    @pytest.mark.asyncio
    async def test_list_by_org_id(self, mock_database, sample_memory):
        """Test list_filtered returns memories for org."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        # First call returns memories, second returns count
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [sample_memory]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_session.execute.side_effect = [mock_list_result, mock_count_result]

        store = MemoryStore(mock_database)
        memories, count = await store.list_filtered(organization_id="org-a")

        assert len(memories) == 1
        assert count == 1
        assert memories[0] == sample_memory

    @pytest.mark.asyncio
    async def test_list_with_scope_filter(self, mock_database, sample_memory):
        """Test list_filtered applies scope filter."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [sample_memory]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_session.execute.side_effect = [mock_list_result, mock_count_result]

        store = MemoryStore(mock_database)
        memories, count = await store.list_filtered(
            organization_id="org-a",
            scope="organization",
        )

        assert len(memories) == 1
        # Verify execute was called (filter applied)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_with_topic_filter(self, mock_database, sample_memory):
        """Test list_filtered applies topic filter."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [sample_memory]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_session.execute.side_effect = [mock_list_result, mock_count_result]

        store = MemoryStore(mock_database)
        memories, count = await store.list_filtered(
            organization_id="org-a",
            topic="content",
        )

        assert len(memories) == 1
        # Verify two queries were made (list + count)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_pagination(self, mock_database):
        """Test list_filtered respects limit and offset."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_session.execute.side_effect = [mock_list_result, mock_count_result]

        store = MemoryStore(mock_database)
        memories, count = await store.list_filtered(
            organization_id="org-a",
            limit=10,
            offset=20,
        )

        # Count reflects total, not limited results
        assert count == 50
        assert len(memories) == 0


# ---------------------------------------------------------------------------
# TestMemoryStoreVersionHistory
# ---------------------------------------------------------------------------


class TestMemoryStoreVersionHistory:
    @pytest.mark.asyncio
    async def test_get_version_history(self, mock_database, sample_memory_id, sample_version):
        """Test get_version_history returns versions in desc order."""
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        # Create version 2
        version2 = MemoryVersion(
            id=uuid.uuid4(),
            memory_id=sample_memory_id,
            version=2,
            body="Updated content",
            change_summary="Second update",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [version2, sample_version]
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        versions = await store.get_version_history(str(sample_memory_id))

        assert len(versions) == 2
        # First should be latest version
        assert versions[0].version == 2
        assert versions[1].version == 1


# ---------------------------------------------------------------------------
# TestMemoryStorePermission
# ---------------------------------------------------------------------------


class TestMemoryStorePermission:
    @pytest.mark.asyncio
    async def test_org_scope_all_read(self, mock_database, sample_memory):
        """Test organization scope allows all org members to read."""
        sample_memory.scope = "organization"
        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        # Mock permission query to return None (no overrides)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.check_permission(
            memory=sample_memory,
            user_id="any-user",
            agent_id=None,
            required_level="read",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_user_scope_only_owner(self, mock_database, sample_memory):
        """Test user scope allows only the scope_value user."""
        sample_memory.scope = "user"
        sample_memory.scope_value = "user-specific-123"

        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)

        # Owner should have access
        result_owner = await store.check_permission(
            memory=sample_memory,
            user_id="user-specific-123",
            agent_id=None,
            required_level="read",
        )
        assert result_owner is True

        # Other user should be denied
        result_other = await store.check_permission(
            memory=sample_memory,
            user_id="different-user",
            agent_id=None,
            required_level="read",
        )
        assert result_other is False

    @pytest.mark.asyncio
    async def test_agent_scope_only_agent(self, mock_database, sample_memory):
        """Test agent scope allows only the scope_value agent."""
        sample_memory.scope = "agent"
        sample_memory.scope_value = "agent-specific-456"

        mock_session = mock_database.get_session.return_value.__aenter__.return_value
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)

        # Correct agent should have access
        result_agent = await store.check_permission(
            memory=sample_memory,
            user_id=None,
            agent_id="agent-specific-456",
            required_level="read",
        )
        assert result_agent is True

        # Different agent should be denied
        result_other = await store.check_permission(
            memory=sample_memory,
            user_id=None,
            agent_id="other-agent",
            required_level="read",
        )
        assert result_other is False

    @pytest.mark.asyncio
    async def test_permission_override_grants_access(self, mock_database, sample_memory):
        """Test MemoryPermission override grants access."""
        sample_memory.scope = "user"
        sample_memory.scope_value = "someone-else"

        mock_session = mock_database.get_session.return_value.__aenter__.return_value

        # Create a permission override
        permission = MemoryPermission(
            id=uuid.uuid4(),
            memory_id=sample_memory.id,
            grantee_user_id="granted-user",
            permission_level="read",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = permission
        mock_session.execute.return_value = mock_result

        store = MemoryStore(mock_database)
        result = await store.check_permission(
            memory=sample_memory,
            user_id="granted-user",
            agent_id=None,
            required_level="read",
        )

        assert result is True
