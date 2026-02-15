"""
Integration tests for workspace object CRUD operations.

Tests the WorkspaceService against isolated database schema.
"""

import pytest
import uuid
from datetime import datetime

from src.infrastructure.workspace.workspace_service import WorkspaceService


@pytest.fixture
async def db(integration_db):
    """Get database instance (alias for integration_db)."""
    yield integration_db


@pytest.fixture
def org_id():
    """Generate unique org_id for test isolation."""
    return f"test-org-{uuid.uuid4()}"


class TestWorkspaceCreate:
    """Tests for creating workspace objects."""

    @pytest.mark.asyncio
    async def test_create_event(self, db, org_id):
        """Test creating a calendar event."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            result = await service.create(
                org_id=org_id,
                type="event",
                data={
                    "title": "Team Meeting",
                    "start": "2026-01-15T10:00:00Z",
                    "end": "2026-01-15T11:00:00Z",
                    "location": "Conference Room A",
                },
                tags=["meeting", "team"],
                created_by_type="user",
                created_by_id="test-user-123",
            )

            assert result["id"] is not None
            assert result["org_id"] == org_id
            assert result["type"] == "event"
            assert result["data"]["title"] == "Team Meeting"
            assert result["tags"] == ["meeting", "team"]
            assert result["created_by_type"] == "user"
            assert result["created_by_id"] == "test-user-123"

    @pytest.mark.asyncio
    async def test_create_contact(self, db, org_id):
        """Test creating a contact."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            result = await service.create(
                org_id=org_id,
                type="contact",
                data={
                    "name": "John Doe",
                    "email": "john@example.com",
                    "company": "Acme Corp",
                },
            )

            assert result["type"] == "contact"
            assert result["data"]["name"] == "John Doe"
            assert result["data"]["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_create_custom_type(self, db, org_id):
        """Test creating a custom object type."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            result = await service.create(
                org_id=org_id,
                type="project",
                data={
                    "name": "Website Redesign",
                    "status": "in_progress",
                    "priority": "high",
                    "budget": 50000,
                },
            )

            assert result["type"] == "project"
            assert result["data"]["budget"] == 50000

    @pytest.mark.asyncio
    async def test_type_normalization(self, db, org_id):
        """Test that type names are normalized."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            result = await service.create(
                org_id=org_id,
                type="  Event  ",  # Should be normalized to "event"
                data={"title": "Test"},
            )

            assert result["type"] == "event"


class TestWorkspaceGet:
    """Tests for retrieving workspace objects."""

    @pytest.mark.asyncio
    async def test_get_existing_object(self, db, org_id):
        """Test retrieving an existing object."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            created = await service.create(
                org_id=org_id,
                type="event",
                data={"title": "Test Event"},
            )

            result = await service.get(org_id, created["id"])

            assert result is not None
            assert result["id"] == created["id"]
            assert result["data"]["title"] == "Test Event"

    @pytest.mark.asyncio
    async def test_get_nonexistent_object(self, db, org_id):
        """Test retrieving a non-existent object."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            result = await service.get(org_id, str(uuid.uuid4()))

            assert result is None

    @pytest.mark.asyncio
    async def test_get_wrong_org(self, db, org_id):
        """Test that objects are isolated by org_id."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            created = await service.create(
                org_id=org_id,
                type="event",
                data={"title": "Test Event"},
            )

            # Try to get with different org_id
            result = await service.get("different-org", created["id"])

            assert result is None


class TestWorkspaceUpdate:
    """Tests for updating workspace objects."""

    @pytest.mark.asyncio
    async def test_update_merge(self, db, org_id):
        """Test updating with merge mode (default)."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            created = await service.create(
                org_id=org_id,
                type="event",
                data={"title": "Original", "location": "Room A"},
            )

            result = await service.update(
                org_id=org_id,
                id=created["id"],
                data={"title": "Updated", "notes": "New field"},
                merge=True,
            )

            assert result["data"]["title"] == "Updated"
            assert result["data"]["location"] == "Room A"  # Preserved
            assert result["data"]["notes"] == "New field"  # Added

    @pytest.mark.asyncio
    async def test_update_replace(self, db, org_id):
        """Test updating with replace mode."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            created = await service.create(
                org_id=org_id,
                type="event",
                data={"title": "Original", "location": "Room A"},
            )

            result = await service.update(
                org_id=org_id,
                id=created["id"],
                data={"title": "Replaced"},
                merge=False,
            )

            assert result["data"]["title"] == "Replaced"
            assert "location" not in result["data"]  # Removed


class TestWorkspaceDelete:
    """Tests for deleting workspace objects."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, db, org_id):
        """Test deleting an existing object."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            created = await service.create(
                org_id=org_id,
                type="event",
                data={"title": "To Delete"},
            )

            deleted = await service.delete(org_id, created["id"])
            assert deleted is True

            # Verify it's gone
            result = await service.get(org_id, created["id"])
            assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db, org_id):
        """Test deleting a non-existent object."""
        async with db.get_session() as session:
            service = WorkspaceService(session)
            deleted = await service.delete(org_id, str(uuid.uuid4()))
            assert deleted is False


class TestWorkspaceQuery:
    """Tests for querying workspace objects."""

    @pytest.mark.asyncio
    async def test_query_by_type(self, db, org_id):
        """Test querying by object type."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            # Create mixed types
            await service.create(org_id=org_id, type="event", data={"title": "Event 1"})
            await service.create(org_id=org_id, type="event", data={"title": "Event 2"})
            await service.create(org_id=org_id, type="contact", data={"name": "John"})

            results = await service.query(org_id=org_id, type="event")

            assert len(results) == 2
            assert all(r["type"] == "event" for r in results)

    @pytest.mark.asyncio
    async def test_query_by_tags(self, db, org_id):
        """Test querying by tags."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            await service.create(org_id=org_id, type="event", data={"title": "A"}, tags=["urgent", "team"])
            await service.create(org_id=org_id, type="event", data={"title": "B"}, tags=["urgent"])
            await service.create(org_id=org_id, type="event", data={"title": "C"}, tags=["team"])

            results = await service.query(org_id=org_id, tags=["urgent", "team"])

            assert len(results) == 1
            assert results[0]["data"]["title"] == "A"

    @pytest.mark.asyncio
    async def test_query_with_where_eq(self, db, org_id):
        """Test querying with $eq operator."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            await service.create(org_id=org_id, type="event", data={"status": "confirmed"})
            await service.create(org_id=org_id, type="event", data={"status": "pending"})

            results = await service.query(
                org_id=org_id,
                type="event",
                where={"status": {"$eq": "confirmed"}},
            )

            assert len(results) == 1
            assert results[0]["data"]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_query_pagination(self, db, org_id):
        """Test query pagination."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            for i in range(5):
                await service.create(org_id=org_id, type="event", data={"index": i})

            page1 = await service.query(org_id=org_id, type="event", limit=2, offset=0)
            page2 = await service.query(org_id=org_id, type="event", limit=2, offset=2)

            assert len(page1) == 2
            assert len(page2) == 2


class TestWorkspaceSearch:
    """Tests for full-text search.

    NOTE: These tests require the workspace_objects_search_trigger PostgreSQL
    trigger function, which is created by Alembic migrations but not by
    SQLAlchemy create_all(). The integration test schema doesn't include
    triggers, so search_vector is never populated.
    """

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="search_vector trigger not replicated in test schema")
    async def test_search_by_title(self, db, org_id):
        """Test searching by title."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            await service.create(org_id=org_id, type="event", data={"title": "Marketing Strategy Meeting"})
            await service.create(org_id=org_id, type="event", data={"title": "Engineering Standup"})
            await service.create(org_id=org_id, type="contact", data={"name": "Marketing Lead"})

            results = await service.search(org_id=org_id, query="Marketing")

            assert len(results) == 2

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="search_vector trigger not replicated in test schema")
    async def test_search_by_description(self, db, org_id):
        """Test searching by description."""
        async with db.get_session() as session:
            service = WorkspaceService(session)

            await service.create(
                org_id=org_id,
                type="event",
                data={"title": "Meeting", "description": "Discuss quarterly budget allocation"},
            )

            results = await service.search(org_id=org_id, query="budget allocation")

            assert len(results) == 1


class TestWorkspaceIsolation:
    """Tests for multi-tenant isolation."""

    @pytest.mark.asyncio
    async def test_org_isolation(self, db):
        """Test that objects are isolated between organizations."""
        org1 = f"org-{uuid.uuid4()}"
        org2 = f"org-{uuid.uuid4()}"

        async with db.get_session() as session:
            service = WorkspaceService(session)

            await service.create(org_id=org1, type="event", data={"title": "Org1 Event"})
            await service.create(org_id=org2, type="event", data={"title": "Org2 Event"})

            org1_results = await service.query(org_id=org1)
            org2_results = await service.query(org_id=org2)

            assert len(org1_results) == 1
            assert org1_results[0]["data"]["title"] == "Org1 Event"
            assert len(org2_results) == 1
            assert org2_results[0]["data"]["title"] == "Org2 Event"
