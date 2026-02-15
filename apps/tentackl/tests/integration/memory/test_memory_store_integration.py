"""Integration tests for MemoryStore with real PostgreSQL.

Tests the full CRUD lifecycle, versioning, and org isolation
using the integration_db fixture from conftest.py.
"""

import pytest

from src.infrastructure.memory.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# TestMemoryLifecycle
# ---------------------------------------------------------------------------


class TestMemoryLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, integration_db):
        """Test complete memory lifecycle: create, update 2x, get versions, delete."""
        store = MemoryStore(integration_db)

        # Create
        memory = await store.create(
            organization_id="org-lifecycle",
            key="test-lifecycle",
            title="Lifecycle Test Memory",
            body="Version 1 body content",
            scope="organization",
            topic="testing",
            tags=["integration", "lifecycle"],
            created_by_user_id="user-lifecycle",
        )

        assert memory is not None
        assert memory.key == "test-lifecycle"
        assert memory.current_version == 1

        # Get by ID
        fetched = await store.get_by_id(str(memory.id), "org-lifecycle")
        assert fetched is not None
        assert fetched.key == "test-lifecycle"

        # Get by key
        fetched_by_key = await store.get_by_key("test-lifecycle", "org-lifecycle")
        assert fetched_by_key is not None
        assert str(fetched_by_key.id) == str(memory.id)

        # Get current version
        version1 = await store.get_current_version(str(memory.id))
        assert version1 is not None
        assert version1.body == "Version 1 body content"
        assert version1.version == 1

        # Update #1 - body change creates new version
        updated_version = await store.update(
            memory=fetched,
            body="Version 2 body content",
            change_summary="First update",
            changed_by="user-lifecycle",
        )
        assert updated_version.version == 2
        assert updated_version.body == "Version 2 body content"

        # Update #2 - another body change
        fetched_again = await store.get_by_id(str(memory.id), "org-lifecycle")
        updated_version2 = await store.update(
            memory=fetched_again,
            body="Version 3 body content",
            change_summary="Second update",
            changed_by="user-lifecycle",
        )
        assert updated_version2.version == 3

        # Get version history
        versions = await store.get_version_history(str(memory.id))
        assert len(versions) == 3
        # Should be in descending order
        assert versions[0].version == 3
        assert versions[1].version == 2
        assert versions[2].version == 1

        # Soft delete
        deleted = await store.soft_delete(str(memory.id), "org-lifecycle")
        assert deleted is True

        # After delete, get should return None
        after_delete = await store.get_by_id(str(memory.id), "org-lifecycle")
        assert after_delete is None


# ---------------------------------------------------------------------------
# TestMemoryOrgIsolation
# ---------------------------------------------------------------------------


class TestMemoryOrgIsolation:
    @pytest.mark.asyncio
    async def test_org_a_cannot_read_org_b(self, integration_db):
        """Test that org-A cannot read memories from org-B."""
        store = MemoryStore(integration_db)

        # Create memory in org-B
        memory_b = await store.create(
            organization_id="org-b",
            key="secret-for-org-b",
            title="Org B Secret",
            body="This is confidential to org B",
            scope="organization",
            created_by_user_id="user-b-123",
        )

        assert memory_b is not None
        assert memory_b.organization_id == "org-b"

        # Try to get from org-A context - should return None
        result_from_org_a = await store.get_by_id(str(memory_b.id), "org-a")
        assert result_from_org_a is None

        # Try to get by key from org-A - should return None
        result_by_key = await store.get_by_key("secret-for-org-b", "org-a")
        assert result_by_key is None

        # List filtered from org-A should not include org-B memory
        memories_in_org_a, count = await store.list_filtered(organization_id="org-a")
        assert count == 0
        assert len(memories_in_org_a) == 0

        # Verify org-B can still access their own memory
        result_from_org_b = await store.get_by_id(str(memory_b.id), "org-b")
        assert result_from_org_b is not None
        assert result_from_org_b.title == "Org B Secret"


# ---------------------------------------------------------------------------
# TestMemoryVersioning
# ---------------------------------------------------------------------------


class TestMemoryVersioning:
    @pytest.mark.asyncio
    async def test_version_increments(self, integration_db):
        """Test that version increments with each body update."""
        store = MemoryStore(integration_db)

        # Create initial memory
        memory = await store.create(
            organization_id="org-versioning",
            key="versioning-test",
            title="Versioning Test",
            body="Initial body",
            created_by_user_id="user-v",
        )

        assert memory.current_version == 1

        # First update
        fetched = await store.get_by_id(str(memory.id), "org-versioning")
        v2 = await store.update(
            memory=fetched,
            body="Second body",
            change_summary="Update 1",
        )
        assert v2.version == 2

        # Second update
        fetched2 = await store.get_by_id(str(memory.id), "org-versioning")
        v3 = await store.update(
            memory=fetched2,
            body="Third body",
            change_summary="Update 2",
        )
        assert v3.version == 3

        # Verify memory.current_version reflects latest
        final = await store.get_by_id(str(memory.id), "org-versioning")
        assert final.current_version == 3

    @pytest.mark.asyncio
    async def test_previous_versions_accessible(self, integration_db):
        """Test that previous versions remain accessible after updates."""
        store = MemoryStore(integration_db)

        # Create and update twice
        memory = await store.create(
            organization_id="org-versions",
            key="versions-history",
            title="Versions History Test",
            body="Body version 1",
            created_by_user_id="user-versions",
        )

        fetched = await store.get_by_id(str(memory.id), "org-versions")
        await store.update(
            memory=fetched,
            body="Body version 2",
        )

        fetched2 = await store.get_by_id(str(memory.id), "org-versions")
        await store.update(
            memory=fetched2,
            body="Body version 3",
        )

        # Get version history
        versions = await store.get_version_history(str(memory.id))

        assert len(versions) == 3

        # Check all version bodies are preserved
        version_bodies = {v.version: v.body for v in versions}
        assert version_bodies[1] == "Body version 1"
        assert version_bodies[2] == "Body version 2"
        assert version_bodies[3] == "Body version 3"

    @pytest.mark.asyncio
    async def test_metadata_update_without_version(self, integration_db):
        """Test that metadata updates don't create new version."""
        store = MemoryStore(integration_db)

        memory = await store.create(
            organization_id="org-meta",
            key="metadata-only",
            title="Original Title",
            body="Body stays the same",
            tags=["original"],
            created_by_user_id="user-meta",
        )

        assert memory.current_version == 1

        # Update only title and tags (no body)
        fetched = await store.get_by_id(str(memory.id), "org-meta")
        await store.update(
            memory=fetched,
            title="Updated Title",
            tags=["updated", "tags"],
        )

        # Version should still be 1
        updated = await store.get_by_id(str(memory.id), "org-meta")
        assert updated.current_version == 1
        assert updated.title == "Updated Title"
        assert "updated" in updated.tags


# ---------------------------------------------------------------------------
# TestMemoryListFiltered
# ---------------------------------------------------------------------------


class TestMemoryListFiltered:
    @pytest.mark.asyncio
    async def test_list_by_topic(self, integration_db):
        """Test filtering by topic."""
        store = MemoryStore(integration_db)

        # Create memories with different topics
        await store.create(
            organization_id="org-list",
            key="content-1",
            title="Content Memory 1",
            body="Content body 1",
            topic="content",
            created_by_user_id="user-list",
        )

        await store.create(
            organization_id="org-list",
            key="ops-1",
            title="Ops Memory 1",
            body="Ops body 1",
            topic="operations",
            created_by_user_id="user-list",
        )

        # Filter by topic
        content_memories, content_count = await store.list_filtered(
            organization_id="org-list",
            topic="content",
        )

        assert content_count == 1
        assert len(content_memories) == 1
        assert content_memories[0].topic == "content"

    @pytest.mark.asyncio
    async def test_list_by_tags(self, integration_db):
        """Test filtering by tags."""
        store = MemoryStore(integration_db)

        await store.create(
            organization_id="org-tags",
            key="tagged-1",
            title="Tagged Memory 1",
            body="Body with tags",
            tags=["api", "learned"],
            created_by_user_id="user-tags",
        )

        await store.create(
            organization_id="org-tags",
            key="tagged-2",
            title="Tagged Memory 2",
            body="Different tags",
            tags=["manual", "reference"],
            created_by_user_id="user-tags",
        )

        # Filter by tags - should find overlap
        api_memories, api_count = await store.list_filtered(
            organization_id="org-tags",
            tags=["api"],
        )

        assert api_count == 1
        assert len(api_memories) == 1
        assert "api" in api_memories[0].tags

    @pytest.mark.asyncio
    async def test_list_pagination(self, integration_db):
        """Test pagination with limit and offset."""
        store = MemoryStore(integration_db)

        # Create 5 memories
        for i in range(5):
            await store.create(
                organization_id="org-page",
                key=f"page-{i}",
                title=f"Page Memory {i}",
                body=f"Body {i}",
                created_by_user_id="user-page",
            )

        # Get first page (limit 2)
        page1, total = await store.list_filtered(
            organization_id="org-page",
            limit=2,
            offset=0,
        )
        assert total == 5
        assert len(page1) == 2

        # Get second page
        page2, _ = await store.list_filtered(
            organization_id="org-page",
            limit=2,
            offset=2,
        )
        assert len(page2) == 2

        # Get third page (partial)
        page3, _ = await store.list_filtered(
            organization_id="org-page",
            limit=2,
            offset=4,
        )
        assert len(page3) == 1
