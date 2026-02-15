"""
Integration tests for template versioning with real Redis
"""

import pytest
import asyncio
from datetime import datetime, timezone
import uuid

from src.templates.redis_template_versioning import RedisTemplateVersioning
from src.interfaces.template_versioning import ApprovalStatus, ChangeType


@pytest.fixture
async def template_versioning():
    """Create template versioning with real Redis connection"""
    versioning = RedisTemplateVersioning(
        redis_url="redis://redis:6379",
        db=14,  # Dedicated DB for template tests
        key_prefix="test:templates"
    )
    async with versioning:
        # Clean up any existing test data
        redis_client = await versioning._get_redis()
        await redis_client.flushdb()
        await redis_client.aclose()
        yield versioning


@pytest.fixture
def sample_template():
    """Sample template for testing"""
    return {
        "name": "data-processor",
        "type": "processor",
        "version": "1.0.0",
        "capabilities": [
            {"tool": "file_reader", "config": {"formats": ["json", "csv"]}},
            {"tool": "data_transformer", "config": {"mode": "aggregate"}}
        ],
        "prompt_template": "Process the data according to: {instructions}",
        "execution_strategy": "sequential",
        "state_schema": {
            "required": ["input_files", "instructions"],
            "output": ["processed_data", "summary"],
            "checkpoint": {"interval": 100}
        },
        "resources": {
            "model": "gpt-4",
            "max_tokens": 2000,
            "timeout": 600
        }
    }


class TestTemplateVersioningIntegration:
    """Integration tests for template versioning"""
    
    @pytest.mark.asyncio
    async def test_complete_template_lifecycle(self, template_versioning, sample_template):
        """Test complete template lifecycle: create, version, approve, rollback"""
        template_id = f"test-template-{uuid.uuid4().hex[:8]}"
        
        # 1. Create initial template
        v1 = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123",
            rationale="Initial template for data processing"
        )
        
        assert v1.version == "1.0.0"
        assert not v1.is_approved
        assert len(v1.changes) == 1
        assert v1.changes[0].change_type == ChangeType.CREATED
        
        # 2. Approve initial version
        v1_approved = await template_versioning.approve_version(
            version_id=v1.id,
            approver_id="admin-456",
            comments="Approved for production use"
        )
        
        assert v1_approved.is_approved
        assert v1_approved.approval.status == ApprovalStatus.APPROVED
        assert len(v1_approved.changes) == 2  # Create + Approve
        
        # 3. Create new version with modifications
        import copy
        modified_template = copy.deepcopy(sample_template)
        modified_template["capabilities"].append({
            "tool": "error_handler",
            "config": {"retry_count": 3}
        })
        modified_template["resources"]["max_tokens"] = 3000
        
        v2 = await template_versioning.create_version(
            template_id=template_id,
            content=modified_template,
            author_id="user-789",
            rationale="Added error handling capability"
        )
        
        assert v2.version == "1.0.1"
        assert v2.parent_version_id == v1.id
        assert not v2.is_approved
        
        # 4. Verify version history
        history = await template_versioning.get_version_history(template_id)
        assert len(history) == 2
        assert history[0].id == v2.id  # Most recent first
        assert history[1].id == v1.id
        
        # 5. Reject v2
        v2_rejected = await template_versioning.reject_version(
            version_id=v2.id,
            approver_id="admin-456",
            comments="Error handler config needs review"
        )
        
        assert v2_rejected.approval.status == ApprovalStatus.REJECTED
        
        # 6. Create v3 with fixes
        fixed_template = copy.deepcopy(modified_template)
        fixed_template["capabilities"][-1]["config"]["retry_count"] = 5
        fixed_template["capabilities"][-1]["config"]["backoff"] = "exponential"
        
        v3 = await template_versioning.create_version(
            template_id=template_id,
            content=fixed_template,
            author_id="user-789",
            rationale="Fixed error handler configuration"
        )
        
        assert v3.version == "1.0.2"
        
        # 7. Approve v3
        v3_approved = await template_versioning.approve_version(
            version_id=v3.id,
            approver_id="admin-456",
            comments="Error handling looks good now"
        )
        
        assert v3_approved.is_approved
        
        # 8. Get latest approved version
        latest = await template_versioning.get_latest_version(template_id, approved_only=True)
        assert latest.id == v3.id
        
        # 9. Simulate issue and rollback to v1
        rollback = await template_versioning.rollback_to_version(
            template_id=template_id,
            target_version_id=v1.id,
            author_id="admin-456",
            rationale="Error handler causing issues in production"
        )
        
        assert rollback.version == "1.0.3"
        # Rollback should have the original v1 content (without error handler)
        assert rollback.content == sample_template  # Original content
        assert rollback.metadata["rollback_from"] == v1.id
        
        # 10. Verify complete history
        final_history = await template_versioning.get_version_history(template_id)
        assert len(final_history) == 4
    
    @pytest.mark.asyncio
    async def test_approval_workflow(self, template_versioning, sample_template):
        """Test approval workflow with multiple templates"""
        # Create multiple templates needing approval
        template_ids = []
        version_ids = []
        
        for i in range(3):
            template_id = f"approval-test-{i}"
            template_ids.append(template_id)
            
            version = await template_versioning.create_template(
                template_id=template_id,
                content=sample_template,
                author_id=f"user-{i}",
                rationale=f"Template {i} for testing"
            )
            version_ids.append(version.id)
        
        # Get pending approvals
        pending = await template_versioning.get_pending_approvals()
        assert len(pending) >= 3
        
        # Approve first template
        await template_versioning.approve_version(
            version_id=version_ids[0],
            approver_id="admin-1",
            comments="Approved"
        )
        
        # Reject second template
        await template_versioning.reject_version(
            version_id=version_ids[1],
            approver_id="admin-1",
            comments="Needs improvements"
        )
        
        # Check pending approvals again
        pending_after = await template_versioning.get_pending_approvals()
        assert len(pending_after) == len(pending) - 2
    
    @pytest.mark.asyncio
    async def test_capability_indexing(self, template_versioning, sample_template):
        """Test capability-based template indexing"""
        # Create templates with different capabilities
        templates = [
            {
                **sample_template,
                "name": "file-processor",
                "capabilities": [
                    {"tool": "file_reader", "config": {}},
                    {"tool": "file_writer", "config": {}}
                ]
            },
            {
                **sample_template,
                "name": "api-caller",
                "capabilities": [
                    {"tool": "http_client", "config": {}},
                    {"tool": "json_parser", "config": {}}
                ]
            },
            {
                **sample_template,
                "name": "data-analyzer",
                "capabilities": [
                    {"tool": "file_reader", "config": {}},
                    {"tool": "data_analyzer", "config": {}}
                ]
            }
        ]
        
        created_versions = []
        for i, template in enumerate(templates):
            version = await template_versioning.create_template(
                template_id=f"cap-test-{i}",
                content=template,
                author_id="user-123"
            )
            
            # Approve it
            approved = await template_versioning.approve_version(
                version_id=version.id,
                approver_id="admin-123"
            )
            created_versions.append(approved)
        
        # Search by capability
        file_reader_templates = await template_versioning.get_templates_by_capability(
            "file_reader",
            approved_only=True
        )
        
        assert len(file_reader_templates) == 2
        template_names = [v.content["name"] for v in file_reader_templates]
        assert "file-processor" in template_names
        assert "data-analyzer" in template_names
    
    @pytest.mark.asyncio
    async def test_version_diffing(self, template_versioning, sample_template):
        """Test version difference tracking"""
        template_id = "diff-test"
        
        # Create initial version
        v1 = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123"
        )
        
        # Make multiple changes
        changes = [
            {
                "description": "Add new capability",
                "modify": lambda t: t["capabilities"].append({"tool": "logger", "config": {"level": "info"}})
            },
            {
                "description": "Update model",
                "modify": lambda t: t.update({"resources": {**t["resources"], "model": "gpt-4-turbo"}})
            },
            {
                "description": "Change execution strategy",
                "modify": lambda t: t.update({"execution_strategy": "parallel"})
            }
        ]
        
        current_template = sample_template.copy()
        
        for change in changes:
            # Apply change
            change["modify"](current_template)
            
            # Create new version
            version = await template_versioning.create_version(
                template_id=template_id,
                content=current_template.copy(),
                author_id="user-123",
                rationale=change["description"]
            )
            
            # Verify diff was captured
            assert len(version.changes) > 0
            latest_change = version.changes[-1]
            assert latest_change.change_type == ChangeType.MODIFIED
            assert len(latest_change.diff) > 0
    
    @pytest.mark.asyncio
    async def test_export_import_workflow(self, template_versioning, sample_template):
        """Test exporting and importing templates"""
        # Create and approve a template
        template_id = "export-test"
        version = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123"
        )
        
        approved = await template_versioning.approve_version(
            version_id=version.id,
            approver_id="admin-123"
        )
        
        # Export as YAML
        yaml_export = await template_versioning.export_template(
            version_id=approved.id,
            format="yaml"
        )
        
        assert "data-processor" in yaml_export
        assert "file_reader" in yaml_export
        
        # Export as JSON
        json_export = await template_versioning.export_template(
            version_id=approved.id,
            format="json"
        )
        
        assert "data-processor" in json_export
        
        # Import into new template
        imported = await template_versioning.import_template(
            content=yaml_export,
            format="yaml",
            author_id="user-456",
            validate=True
        )
        
        # Verify imported content matches
        assert imported.content["name"] == sample_template["name"]
        assert len(imported.content["capabilities"]) == len(sample_template["capabilities"])
        assert imported.metadata["imported"] is True
    
    @pytest.mark.asyncio
    async def test_concurrent_version_creation(self, template_versioning, sample_template):
        """Test concurrent version creation handling"""
        template_id = "concurrent-test"
        
        # Create initial template
        v1 = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123"
        )
        
        # Try to create multiple versions concurrently
        async def create_version(suffix):
            modified = sample_template.copy()
            modified["name"] = f"processor-{suffix}"
            
            return await template_versioning.create_version(
                template_id=template_id,
                content=modified,
                author_id=f"user-{suffix}",
                rationale=f"Concurrent change {suffix}"
            )
        
        # Create versions concurrently
        versions = await asyncio.gather(
            create_version("a"),
            create_version("b"),
            create_version("c"),
            return_exceptions=True
        )
        
        # All should succeed without errors
        successful_versions = [v for v in versions if not isinstance(v, Exception)]
        assert len(successful_versions) == 3
        
        # Verify version numbers are sequential
        version_numbers = [v.version for v in successful_versions]
        assert "1.0.1" in version_numbers
        assert "1.0.2" in version_numbers
        assert "1.0.3" in version_numbers
    
    @pytest.mark.asyncio
    async def test_usage_tracking(self, template_versioning, sample_template):
        """Test usage statistics tracking"""
        template_id = "usage-test"
        
        # Create template
        version = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123"
        )
        
        # Simulate usage (in real system, this would be done by execution engine)
        redis_client = await template_versioning._get_redis()
        stats_key = template_versioning._get_usage_stats_key(template_id, version.id)
        
        # Update stats
        await redis_client.hincrby(stats_key, "execution_count", 10)
        await redis_client.hincrby(stats_key, "success_count", 8)
        await redis_client.hincrby(stats_key, "failure_count", 2)
        await redis_client.hset(stats_key, "average_duration", "3.5")
        await redis_client.hset(stats_key, "last_used", datetime.now(timezone.utc).isoformat())
        await redis_client.aclose()
        
        # Get usage stats
        stats = await template_versioning.get_usage_stats(template_id, version.id)
        
        assert stats["execution_count"] == 10
        assert stats["success_count"] == 8
        assert stats["failure_count"] == 2
        assert stats["success_rate"] == 0.8
        assert stats["average_duration"] == 3.5
    
    @pytest.mark.asyncio
    async def test_template_deprecation(self, template_versioning, sample_template):
        """Test template deprecation workflow"""
        template_id = "deprecation-test"
        
        # Create and approve template
        v1 = await template_versioning.create_template(
            template_id=template_id,
            content=sample_template,
            author_id="user-123"
        )
        
        v1_approved = await template_versioning.approve_version(
            version_id=v1.id,
            approver_id="admin-123"
        )
        
        # Use it for a while...
        
        # Deprecate it
        deprecated = await template_versioning.deprecate_version(
            version_id=v1.id,
            deprecator_id="admin-456",
            reason="Replaced by new architecture"
        )
        
        assert deprecated.approval.status == ApprovalStatus.DEPRECATED
        assert len(deprecated.changes) == 3  # Create + Approve + Deprecate
        
        # Should not be returned as latest approved
        latest = await template_versioning.get_latest_version(
            template_id,
            approved_only=True
        )
        assert latest is None  # No approved versions left
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self, template_versioning):
        """Test health check with real Redis"""
        # Create some test data
        for i in range(3):
            await template_versioning.create_template(
                template_id=f"health-test-{i}",
                content={"name": f"test-{i}", "type": "test", "capabilities": [], "prompt_template": "test"},
                author_id="user-123"
            )
        
        # Check health
        health = await template_versioning.health_check()
        
        assert health["status"] == "healthy"
        assert health["redis"] == "connected"
        assert health["templates"] >= 3
        assert health["pending_approvals"] >= 3