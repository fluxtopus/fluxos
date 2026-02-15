"""Integration tests for capabilities API (CAP-004, CAP-005).

Tests the /api/capabilities/agents endpoints against a real database.
"""

import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy import select

from src.database.capability_models import AgentCapability
from src.interfaces.database import Base


@pytest_asyncio.fixture
async def seed_capabilities(test_db):
    """Seed test capabilities into the database.

    Uses unique agent_type values per test run to avoid conflicts with
    existing seeded capabilities or data from previous test runs.
    """
    cap_id_1 = uuid4()
    cap_id_2 = uuid4()
    cap_id_3 = uuid4()
    org_id = uuid4()

    # Use unique suffixes to avoid conflicts with existing seeded capabilities
    unique_suffix = uuid4().hex[:8]

    async with test_db.get_session() as session:
        # System capability - summarize (with unique suffix)
        cap1 = AgentCapability(
            id=cap_id_1,
            organization_id=None,
            agent_type=f"test_summarize_{unique_suffix}",
            name="Test Summarize Agent",
            description="Summarizes content into key points",
            domain="content",
            task_type="general",
            system_prompt="You are a summarization expert.",
            inputs_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            outputs_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
            is_system=True,
            is_active=True,
            version=1,
            is_latest=True,
            tags=["content", "summarization"],
            usage_count=100,
            success_count=95,
            failure_count=5,
        )

        # System capability - web research (with unique suffix)
        cap2 = AgentCapability(
            id=cap_id_2,
            organization_id=None,
            agent_type=f"test_web_research_{unique_suffix}",
            name="Test Web Research Agent",
            description="Researches topics on the web",
            domain="research",
            task_type="reasoning",
            system_prompt="You are a research expert.",
            inputs_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            outputs_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
            is_system=True,
            is_active=True,
            version=1,
            is_latest=True,
            tags=["research", "web"],
            usage_count=50,
            success_count=48,
            failure_count=2,
        )

        # User capability (with unique suffix)
        cap3 = AgentCapability(
            id=cap_id_3,
            organization_id=org_id,
            agent_type=f"test_custom_reporter_{unique_suffix}",
            name="Custom Reporter",
            description="Generates custom reports",
            domain="analytics",
            task_type="creative",
            system_prompt="You generate detailed reports.",
            inputs_schema={"type": "object", "properties": {"data": {"type": "object"}}},
            outputs_schema={"type": "object", "properties": {"report": {"type": "string"}}},
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
            tags=["reports", "analytics"],
            usage_count=10,
            success_count=9,
            failure_count=1,
        )

        session.add(cap1)
        session.add(cap2)
        session.add(cap3)
        await session.commit()

    return {
        "cap_ids": [cap_id_1, cap_id_2, cap_id_3],
        "org_id": org_id,
        "agent_types": {
            "summarize": f"test_summarize_{unique_suffix}",
            "web_research": f"test_web_research_{unique_suffix}",
            "custom_reporter": f"test_custom_reporter_{unique_suffix}",
        },
    }


@pytest.mark.asyncio
async def test_list_capabilities_returns_system_caps(test_db, seed_capabilities):
    """Should return system capabilities when include_system=True."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    # Inject test database
    cap_module.database = test_db

    # Mock user (no org - only sees system caps)
    mock_user = MagicMock()
    mock_user.metadata = {}

    result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=True,
        active_only=True,
        limit=500,  # Increased to accommodate all seeded caps
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should return at least the system capabilities (seeded by fixture)
    assert result.count >= 2
    assert result.total >= 2

    # Verify the seeded test capabilities are in results
    agent_types = [c.agent_type for c in result.capabilities]
    # Check for the unique test capabilities seeded by the fixture
    assert seed_capabilities["agent_types"]["summarize"] in agent_types
    assert seed_capabilities["agent_types"]["web_research"] in agent_types

    # User without org can't edit any capability
    for cap in result.capabilities:
        assert cap.can_edit is False


@pytest.mark.asyncio
async def test_list_capabilities_filter_by_domain(test_db, seed_capabilities):
    """Should filter capabilities by domain."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.metadata = {}

    result = await list_capabilities(
        domain="content",  # Filter to only content domain
        tags=None,
        include_system=True,
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should return only content domain capabilities
    assert result.count >= 1
    # All returned capabilities should have content domain
    for cap in result.capabilities:
        assert cap.domain == "content"
    # Our seeded summarize capability should be in results
    summarize_agent_type = seed_capabilities["agent_types"]["summarize"]
    assert any(
        c.agent_type in {"summarize", summarize_agent_type}
        for c in result.capabilities
    )


@pytest.mark.asyncio
async def test_list_capabilities_filter_by_tags(test_db, seed_capabilities):
    """Should filter capabilities by tags."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.metadata = {}

    result = await list_capabilities(
        domain=None,
        tags=["research"],  # Filter by research tag
        include_system=True,
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should return capabilities with research tag
    assert result.count >= 1
    web_research_agent_type = seed_capabilities["agent_types"]["web_research"]
    assert any(
        c.agent_type in {"web_research", web_research_agent_type}
        for c in result.capabilities
    )


@pytest.mark.asyncio
async def test_list_capabilities_org_scoping(test_db, seed_capabilities):
    """Should return org capabilities plus system capabilities."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    # User from the same org as the custom capability
    mock_user = MagicMock()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=True,
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should return system caps + org caps
    assert result.count >= 3

    # Find the custom capability (using dynamic agent_type from fixture)
    custom_agent_type = seed_capabilities["agent_types"]["custom_reporter"]
    custom_cap = next((c for c in result.capabilities if c.agent_type == custom_agent_type), None)
    assert custom_cap is not None
    # User can edit their org's non-system capability
    assert custom_cap.can_edit is True


@pytest.mark.asyncio
async def test_list_capabilities_exclude_system(test_db, seed_capabilities):
    """Should exclude system capabilities when include_system=False."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    # User from org with custom capability
    mock_user = MagicMock()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=False,  # Exclude system caps
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should only return user org capabilities, not system ones
    assert result.count >= 1
    # All returned capabilities should be non-system
    for cap in result.capabilities:
        assert cap.is_system is False
    # Our custom capability should be in results (using dynamic agent_type)
    custom_agent_type = seed_capabilities["agent_types"]["custom_reporter"]
    assert any(c.agent_type == custom_agent_type for c in result.capabilities)


@pytest.mark.asyncio
async def test_list_capabilities_pagination(test_db, seed_capabilities):
    """Should support pagination."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    # Get first page
    result1 = await list_capabilities(
        domain=None,
        tags=None,
        include_system=True,
        active_only=True,
        limit=2,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Get second page
    result2 = await list_capabilities(
        domain=None,
        tags=None,
        include_system=True,
        active_only=True,
        limit=2,
        offset=2,
        db=test_db,
        current_user=mock_user,
    )

    # First page should have 2 results
    assert result1.count == 2
    # Total should be >= 3
    assert result1.total >= 3

    # Second page should have at least 1 result
    assert result2.count >= 1

    # Results should be different
    page1_types = {c.agent_type for c in result1.capabilities}
    page2_types = {c.agent_type for c in result2.capabilities}
    assert page1_types != page2_types


@pytest.mark.asyncio
async def test_list_capabilities_empty_when_no_system_no_org(test_db, seed_capabilities):
    """Should return empty when no system caps and no org_id."""
    from src.api.routers.capabilities import list_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    # User without org
    mock_user = MagicMock()
    mock_user.metadata = {}

    result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=False,  # No system caps
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should return empty - no org caps and no system caps
    assert result.count == 0
    assert result.total == 0


# CAP-005: Create Capability Integration Tests

@pytest.mark.asyncio
async def test_create_capability_success(test_db):
    """Should create capability and persist to database."""
    from src.api.routers.capabilities import create_capability, CreateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"test_int_agent_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Test Integration Agent
description: An agent created in integration tests
domain: testing
task_type: general
system_prompt: You are a test agent for integration testing.
inputs:
  test_input:
    type: string
    required: true
    description: Test input field
outputs:
  test_output:
    type: string
    description: Test output field
execution_hints:
  speed: fast
  cost: low
"""
    request = CreateCapabilityRequest(
        spec_yaml=yaml_spec,
        tags=["integration", "test"]
    )

    result = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user,
    )

    # Verify response
    assert result.message == "Capability created successfully"
    assert result.capability.agent_type == unique_agent_type
    assert result.capability.name == "Test Integration Agent"
    assert result.capability.domain == "testing"
    assert result.capability.is_system is False
    assert result.capability.is_active is True
    assert result.capability.version == 1
    assert result.capability.is_latest is True
    assert result.capability.can_edit is True
    assert result.capability.organization_id == org_id
    assert result.capability.created_by == user_id
    assert result.capability.tags == ["integration", "test"]

    # Verify it was persisted to database
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(
            AgentCapability.id == result.capability.id
        )
        db_result = await session.execute(query)
        saved_cap = db_result.scalar_one_or_none()

        assert saved_cap is not None
        assert saved_cap.agent_type == unique_agent_type
        assert saved_cap.name == "Test Integration Agent"
        assert saved_cap.is_system is False
        assert saved_cap.organization_id == org_id
        assert saved_cap.created_by == user_id
        assert saved_cap.embedding_status == "pending"


@pytest.mark.asyncio
async def test_create_capability_duplicate_agent_type(test_db):
    """Should reject duplicate agent_type within organization."""
    from src.api.routers.capabilities import create_capability, CreateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"dup_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Duplicate Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    request = CreateCapabilityRequest(spec_yaml=yaml_spec)

    # Create first capability
    result1 = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user,
    )
    assert result1.capability.agent_type == unique_agent_type

    # Try to create duplicate
    with pytest.raises(HTTPException) as exc_info:
        await create_capability(
            request=request,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_capability_different_orgs_same_agent_type(test_db):
    """Should allow same agent_type in different organizations."""
    from src.api.routers.capabilities import create_capability, CreateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id_1 = uuid4()
    org_id_2 = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"shared_agent_{uuid4().hex[:8]}"

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Shared Name Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    request = CreateCapabilityRequest(spec_yaml=yaml_spec)

    # Create in org 1
    mock_user_1 = MagicMock()
    mock_user_1.id = user_id_1
    mock_user_1.metadata = {"organization_id": str(org_id_1)}

    result1 = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user_1,
    )
    assert result1.capability.organization_id == org_id_1

    # Create same agent_type in org 2 - should succeed
    mock_user_2 = MagicMock()
    mock_user_2.id = user_id_2
    mock_user_2.metadata = {"organization_id": str(org_id_2)}

    result2 = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user_2,
    )
    assert result2.capability.organization_id == org_id_2

    # Verify both were created by fetching their specific IDs
    async with test_db.get_session() as session:
        # Query for the two specific capabilities we created
        from sqlalchemy import or_
        query = select(AgentCapability).where(
            or_(
                AgentCapability.id == result1.capability.id,
                AgentCapability.id == result2.capability.id
            )
        )
        db_result = await session.execute(query)
        saved_caps = db_result.scalars().all()

        assert len(saved_caps) == 2
        orgs = {c.organization_id for c in saved_caps}
        assert org_id_1 in orgs
        assert org_id_2 in orgs


@pytest.mark.asyncio
async def test_create_capability_validates_yaml_spec(test_db):
    """Should validate capability spec and reject invalid specs."""
    from src.api.routers.capabilities import create_capability, CreateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"incomplete_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    # Missing required fields (system_prompt and inputs)
    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Incomplete Agent
"""
    request = CreateCapabilityRequest(spec_yaml=yaml_spec)

    with pytest.raises(HTTPException) as exc_info:
        await create_capability(
            request=request,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 400
    assert "Invalid capability specification" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_capability_keywords_extracted(test_db):
    """Should extract keywords from spec for search."""
    from src.api.routers.capabilities import create_capability, CreateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"content_analysis_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Content Analysis Agent
domain: analytics
system_prompt: You analyze content.
inputs:
  raw_content:
    type: string
  analysis_type:
    type: string
outputs:
  analysis_result:
    type: object
"""
    request = CreateCapabilityRequest(spec_yaml=yaml_spec)

    result = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user,
    )

    # Verify keywords were extracted and stored
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(
            AgentCapability.id == result.capability.id
        )
        db_result = await session.execute(query)
        saved_cap = db_result.scalar_one()

        # Should have keywords extracted
        assert saved_cap.keywords is not None
        assert len(saved_cap.keywords) > 0
        # Should include words from agent_type, domain, input/output names
        keywords_lower = [k.lower() for k in saved_cap.keywords]
        assert "content" in keywords_lower
        assert "analysis" in keywords_lower
        assert "analytics" in keywords_lower


@pytest.mark.asyncio
async def test_created_capability_appears_in_list(test_db):
    """Should show created capability in list endpoint."""
    from src.api.routers.capabilities import (
        create_capability,
        list_capabilities,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    # Use unique agent_type to avoid conflicts with other test runs
    unique_agent_type = f"list_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: List Test Agent
domain: testing
system_prompt: Test agent.
inputs:
  data:
    type: string
"""
    request = CreateCapabilityRequest(
        spec_yaml=yaml_spec,
        tags=["list-test"]
    )

    # Create the capability
    create_result = await create_capability(
        request=request,
        db=test_db,
        current_user=mock_user,
    )

    # Now list capabilities and verify it appears
    list_result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=False,  # Only custom caps
        active_only=True,
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Find our created capability by ID (more reliable than agent_type)
    created_cap = next(
        (c for c in list_result.capabilities if c.id == create_result.capability.id),
        None
    )

    assert created_cap is not None
    assert created_cap.agent_type == unique_agent_type
    assert created_cap.name == "List Test Agent"
    assert created_cap.is_system is False
    assert created_cap.can_edit is True


# CAP-006: Update Capability Integration Tests

@pytest.mark.asyncio
async def test_update_capability_metadata_only(test_db):
    """Should update metadata without creating new version."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"update_meta_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    # Create the capability first
    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Original Name
system_prompt: Original prompt.
inputs:
  data:
    type: string
"""
    create_request = CreateCapabilityRequest(
        spec_yaml=yaml_spec,
        tags=["original"]
    )

    create_result = await create_capability(
        request=create_request,
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id
    original_version = create_result.capability.version

    # Update only metadata (tags)
    update_request = UpdateCapabilityRequest(
        tags=["updated", "new-tag"]
    )

    update_result = await update_capability(
        capability_id=cap_id,
        request=update_request,
        db=test_db,
        current_user=mock_user,
    )

    # Verify no new version created
    assert update_result.version_created is False
    assert update_result.capability.version == original_version
    assert update_result.capability.tags == ["updated", "new-tag"]
    # ID should be the same
    assert update_result.capability.id == cap_id


@pytest.mark.asyncio
async def test_update_capability_spec_creates_version(test_db):
    """Should create new version when spec_yaml changes."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"update_spec_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    # Create the capability
    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Original Name
system_prompt: Original prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    original_cap_id = create_result.capability.id
    assert create_result.capability.version == 1

    # Update spec_yaml (adds new input field)
    new_yaml = f"""
agent_type: {unique_agent_type}
name: Updated Name
system_prompt: Updated prompt with more detail.
inputs:
  data:
    type: string
  extra_field:
    type: integer
    description: A new field
outputs:
  result:
    type: string
"""
    update_result = await update_capability(
        capability_id=original_cap_id,
        request=UpdateCapabilityRequest(spec_yaml=new_yaml),
        db=test_db,
        current_user=mock_user,
    )

    # Verify new version created
    assert update_result.version_created is True
    assert update_result.capability.version == 2
    assert update_result.capability.is_latest is True
    # New capability should have different ID
    assert update_result.capability.id != original_cap_id
    # Name should be updated
    assert update_result.capability.name == "Updated Name"
    # Analytics should be reset
    assert update_result.capability.usage_count == 0

    # Verify old version is marked as not latest in database
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(
            AgentCapability.id == original_cap_id
        )
        db_result = await session.execute(query)
        old_cap = db_result.scalar_one()

        assert old_cap.is_latest is False
        assert old_cap.version == 1


@pytest.mark.asyncio
async def test_update_capability_system_rejected(test_db, seed_capabilities):
    """Should reject updates to system capabilities."""
    from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    user_id = uuid4()

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(uuid4())}

    # Try to update the seeded system capability
    system_cap_id = seed_capabilities["cap_ids"][0]

    with pytest.raises(HTTPException) as exc_info:
        await update_capability(
            capability_id=system_cap_id,
            request=UpdateCapabilityRequest(tags=["hacked"]),
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 403
    assert "system capabilities" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_update_capability_wrong_org_rejected(test_db):
    """Should reject updates from different organization."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id_1 = uuid4()
    org_id_2 = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    unique_agent_type = f"org_test_{uuid4().hex[:8]}"

    # Create capability as org 1
    mock_user_1 = MagicMock()
    mock_user_1.id = user_id_1
    mock_user_1.metadata = {"organization_id": str(org_id_1)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Org Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user_1,
    )

    cap_id = create_result.capability.id

    # Try to update as org 2
    mock_user_2 = MagicMock()
    mock_user_2.id = user_id_2
    mock_user_2.metadata = {"organization_id": str(org_id_2)}

    with pytest.raises(HTTPException) as exc_info:
        await update_capability(
            capability_id=cap_id,
            request=UpdateCapabilityRequest(tags=["stolen"]),
            db=test_db,
            current_user=mock_user_2,
        )

    assert exc_info.value.status_code == 403
    assert "your organization" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_update_capability_not_found(test_db):
    """Should return 404 for non-existent capability."""
    from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(uuid4())}

    non_existent_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await update_capability(
            capability_id=non_existent_id,
            request=UpdateCapabilityRequest(tags=["test"]),
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_update_capability_is_active(test_db):
    """Should update is_active flag in place."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"active_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Active Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id
    assert create_result.capability.is_active is True

    # Deactivate the capability
    update_result = await update_capability(
        capability_id=cap_id,
        request=UpdateCapabilityRequest(is_active=False),
        db=test_db,
        current_user=mock_user,
    )

    assert update_result.version_created is False
    assert update_result.capability.is_active is False
    assert update_result.capability.id == cap_id  # Same ID

    # Verify persisted
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(AgentCapability.id == cap_id)
        db_result = await session.execute(query)
        saved_cap = db_result.scalar_one()
        assert saved_cap.is_active is False


@pytest.mark.asyncio
async def test_update_capability_agent_type_change_conflict(test_db):
    """Should reject agent_type change that conflicts with existing capability."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    agent_type_1 = f"agent_a_{uuid4().hex[:8]}"
    agent_type_2 = f"agent_b_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    # Create first capability
    yaml_spec_1 = f"""
agent_type: {agent_type_1}
name: Agent A
system_prompt: First agent.
inputs:
  data:
    type: string
"""
    create_result_1 = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec_1),
        db=test_db,
        current_user=mock_user,
    )

    # Create second capability
    yaml_spec_2 = f"""
agent_type: {agent_type_2}
name: Agent B
system_prompt: Second agent.
inputs:
  data:
    type: string
"""
    await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec_2),
        db=test_db,
        current_user=mock_user,
    )

    # Try to update first capability's agent_type to match second
    conflicting_yaml = f"""
agent_type: {agent_type_2}
name: Agent A Renamed
system_prompt: Updated prompt.
inputs:
  data:
    type: string
"""
    with pytest.raises(HTTPException) as exc_info:
        await update_capability(
            capability_id=create_result_1.capability.id,
            request=UpdateCapabilityRequest(spec_yaml=conflicting_yaml),
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_update_capability_invalid_spec_rejected(test_db):
    """Should reject invalid spec_yaml."""
    from src.api.routers.capabilities import (
        create_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"invalid_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Valid Agent
system_prompt: Valid prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # Try to update with invalid spec (missing required fields)
    invalid_yaml = f"""
agent_type: {unique_agent_type}
name: Now Invalid
"""
    with pytest.raises(HTTPException) as exc_info:
        await update_capability(
            capability_id=cap_id,
            request=UpdateCapabilityRequest(spec_yaml=invalid_yaml),
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 400
    assert "Invalid capability specification" in str(exc_info.value.detail)


# CAP-007: Delete Capability Integration Tests

@pytest.mark.asyncio
async def test_delete_capability_success(test_db):
    """Should soft-delete capability by setting is_active=false."""
    from src.api.routers.capabilities import (
        create_capability,
        delete_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"delete_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Delete Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    # Create the capability
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id
    assert create_result.capability.is_active is True

    # Delete the capability
    delete_result = await delete_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )

    assert delete_result.id == cap_id
    assert delete_result.agent_type == unique_agent_type
    assert delete_result.message == "Capability deleted successfully"

    # Verify it was soft-deleted (is_active=false) in database
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(AgentCapability.id == cap_id)
        db_result = await session.execute(query)
        saved_cap = db_result.scalar_one()

        assert saved_cap.is_active is False
        # Record should still exist
        assert saved_cap.id == cap_id
        assert saved_cap.agent_type == unique_agent_type


@pytest.mark.asyncio
async def test_delete_capability_not_found(test_db):
    """Should return 404 for non-existent capability."""
    from src.api.routers.capabilities import delete_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(uuid4())}

    non_existent_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await delete_capability(
            capability_id=non_existent_id,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_capability_system_rejected(test_db, seed_capabilities):
    """Should reject deletion of system capabilities."""
    from src.api.routers.capabilities import delete_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(uuid4())}

    # Try to delete the seeded system capability
    system_cap_id = seed_capabilities["cap_ids"][0]

    with pytest.raises(HTTPException) as exc_info:
        await delete_capability(
            capability_id=system_cap_id,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 403
    assert "system capabilities" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_capability_wrong_org_rejected(test_db):
    """Should reject deletion from different organization."""
    from src.api.routers.capabilities import (
        create_capability,
        delete_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id_1 = uuid4()
    org_id_2 = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    unique_agent_type = f"delete_org_test_{uuid4().hex[:8]}"

    # Create capability as org 1
    mock_user_1 = MagicMock()
    mock_user_1.id = user_id_1
    mock_user_1.metadata = {"organization_id": str(org_id_1)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Delete Org Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user_1,
    )

    cap_id = create_result.capability.id

    # Try to delete as org 2
    mock_user_2 = MagicMock()
    mock_user_2.id = user_id_2
    mock_user_2.metadata = {"organization_id": str(org_id_2)}

    with pytest.raises(HTTPException) as exc_info:
        await delete_capability(
            capability_id=cap_id,
            db=test_db,
            current_user=mock_user_2,
        )

    assert exc_info.value.status_code == 403
    assert "your organization" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_capability_no_org_rejected(test_db):
    """Should reject if user has no organization."""
    from src.api.routers.capabilities import delete_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}  # No organization_id

    with pytest.raises(HTTPException) as exc_info:
        await delete_capability(
            capability_id=uuid4(),
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 403
    assert "organization" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_capability_already_inactive(test_db):
    """Should succeed even if capability is already inactive (idempotent)."""
    from src.api.routers.capabilities import (
        create_capability,
        delete_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"delete_idem_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Delete Idempotent Test
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    # Create the capability
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # First delete
    delete_result_1 = await delete_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )
    assert delete_result_1.message == "Capability deleted successfully"

    # Second delete should also succeed (idempotent)
    delete_result_2 = await delete_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )
    assert delete_result_2.message == "Capability deleted successfully"


@pytest.mark.asyncio
async def test_deleted_capability_excluded_from_active_only_list(test_db):
    """Should not show deleted capability in list when active_only=True."""
    from src.api.routers.capabilities import (
        create_capability,
        delete_capability,
        list_capabilities,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"delete_list_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Delete List Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    # Create the capability
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # Delete the capability
    await delete_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )

    # List with active_only=True should not include the deleted capability
    list_result = await list_capabilities(
        domain=None,
        tags=None,
        include_system=False,
        active_only=True,  # Only active
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should not find our deleted capability
    deleted_cap = next(
        (c for c in list_result.capabilities if c.id == cap_id),
        None
    )
    assert deleted_cap is None

    # List with active_only=False should include it
    list_result_all = await list_capabilities(
        domain=None,
        tags=None,
        include_system=False,
        active_only=False,  # Include inactive
        limit=100,
        offset=0,
        db=test_db,
        current_user=mock_user,
    )

    # Should find our deleted capability with is_active=False
    found_cap = next(
        (c for c in list_result_all.capabilities if c.id == cap_id),
        None
    )
    assert found_cap is not None
    assert found_cap.is_active is False


@pytest.mark.asyncio
async def test_deleted_capability_can_be_reactivated(test_db):
    """Should be able to reactivate a deleted capability via update endpoint."""
    from src.api.routers.capabilities import (
        create_capability,
        delete_capability,
        update_capability,
        CreateCapabilityRequest,
        UpdateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"reactivate_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Reactivate Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    # Create the capability
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # Delete (deactivate) the capability
    await delete_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )

    # Reactivate via update
    update_result = await update_capability(
        capability_id=cap_id,
        request=UpdateCapabilityRequest(is_active=True),
        db=test_db,
        current_user=mock_user,
    )

    assert update_result.capability.is_active is True
    assert update_result.capability.id == cap_id

    # Verify persisted
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(AgentCapability.id == cap_id)
        db_result = await session.execute(query)
        saved_cap = db_result.scalar_one()

        assert saved_cap.is_active is True


# CAP-008: Get Single Capability Integration Tests

@pytest.mark.asyncio
async def test_get_capability_system_success(test_db, seed_capabilities):
    """Should return system capability with full details."""
    from src.api.routers.capabilities import get_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    # User without org can still view system capabilities
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}

    # Get the seeded system capability
    system_cap_id = seed_capabilities["cap_ids"][0]

    result = await get_capability(
        capability_id=system_cap_id,
        db=test_db,
        current_user=mock_user,
    )

    assert result.capability.id == system_cap_id
    # Use the unique agent_type from fixture
    assert result.capability.agent_type == seed_capabilities["agent_types"]["summarize"]
    assert result.capability.is_system is True
    assert result.capability.system_prompt == "You are a summarization expert."
    assert result.capability.can_edit is False
    # Verify usage stats are included
    assert result.capability.usage_count == 100
    assert result.capability.success_count == 95


@pytest.mark.asyncio
async def test_get_capability_user_owned_success(test_db):
    """Should return user-owned capability with can_edit=True."""
    from src.api.routers.capabilities import (
        create_capability,
        get_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"get_user_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Get User Test Agent
description: An agent for testing get endpoint
domain: testing
task_type: reasoning
system_prompt: You are a test agent.
inputs:
  query:
    type: string
    required: true
outputs:
  result:
    type: string
execution_hints:
  speed: fast
  cost: low
"""
    # Create the capability
    create_result = await create_capability(
        request=CreateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["get-test", "user-owned"]
        ),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # Get the capability
    result = await get_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )

    # Verify full details are returned
    assert result.capability.id == cap_id
    assert result.capability.agent_type == unique_agent_type
    assert result.capability.name == "Get User Test Agent"
    assert result.capability.description == "An agent for testing get endpoint"
    assert result.capability.domain == "testing"
    assert result.capability.task_type == "reasoning"
    assert result.capability.system_prompt == "You are a test agent."
    assert "query" in result.capability.inputs_schema
    assert "result" in result.capability.outputs_schema
    assert result.capability.execution_hints["speed"] == "fast"
    assert result.capability.is_system is False
    assert result.capability.is_active is True
    assert result.capability.version == 1
    assert result.capability.can_edit is True
    assert result.capability.organization_id == org_id
    assert result.capability.created_by == user_id
    assert result.capability.tags == ["get-test", "user-owned"]
    assert result.capability.spec_yaml is not None
    assert unique_agent_type in result.capability.spec_yaml


@pytest.mark.asyncio
async def test_get_capability_not_found(test_db):
    """Should return 404 for non-existent capability."""
    from src.api.routers.capabilities import get_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(uuid4())}

    non_existent_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await get_capability(
            capability_id=non_existent_id,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_capability_wrong_org_rejected(test_db):
    """Should reject access to capability from different organization."""
    from src.api.routers.capabilities import (
        create_capability,
        get_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    org_id_1 = uuid4()
    org_id_2 = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    unique_agent_type = f"get_wrong_org_{uuid4().hex[:8]}"

    # Create capability as org 1
    mock_user_1 = MagicMock()
    mock_user_1.id = user_id_1
    mock_user_1.metadata = {"organization_id": str(org_id_1)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Wrong Org Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user_1,
    )

    cap_id = create_result.capability.id

    # Try to get as org 2
    mock_user_2 = MagicMock()
    mock_user_2.id = user_id_2
    mock_user_2.metadata = {"organization_id": str(org_id_2)}

    with pytest.raises(HTTPException) as exc_info:
        await get_capability(
            capability_id=cap_id,
            db=test_db,
            current_user=mock_user_2,
        )

    assert exc_info.value.status_code == 403
    assert "your organization" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_capability_no_org_user_can_see_system(test_db, seed_capabilities):
    """User without org can see system capabilities."""
    from src.api.routers.capabilities import get_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    # User without organization
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}  # No org

    system_cap_id = seed_capabilities["cap_ids"][0]

    result = await get_capability(
        capability_id=system_cap_id,
        db=test_db,
        current_user=mock_user,
    )

    assert result.capability.id == system_cap_id
    assert result.capability.is_system is True
    assert result.capability.can_edit is False


@pytest.mark.asyncio
async def test_get_capability_no_org_user_cannot_see_user_caps(test_db, seed_capabilities):
    """User without org cannot see user-defined capabilities."""
    from src.api.routers.capabilities import get_capability
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock
    from fastapi import HTTPException

    cap_module.database = test_db

    # User without organization
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}  # No org

    # Try to access the seeded user capability (cap_ids[2] is custom_reporter)
    user_cap_id = seed_capabilities["cap_ids"][2]

    with pytest.raises(HTTPException) as exc_info:
        await get_capability(
            capability_id=user_cap_id,
            db=test_db,
            current_user=mock_user,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_capability_same_org_can_see_other_users_caps(test_db):
    """Users in same org can see capabilities created by other users in org."""
    from src.api.routers.capabilities import (
        create_capability,
        get_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()
    unique_agent_type = f"same_org_test_{uuid4().hex[:8]}"

    # Create capability as user 1
    mock_user_1 = MagicMock()
    mock_user_1.id = user_id_1
    mock_user_1.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Same Org Test Agent
system_prompt: Test prompt.
inputs:
  data:
    type: string
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user_1,
    )

    cap_id = create_result.capability.id

    # Get as user 2 from same org
    mock_user_2 = MagicMock()
    mock_user_2.id = user_id_2
    mock_user_2.metadata = {"organization_id": str(org_id)}

    result = await get_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user_2,
    )

    # Should succeed - same org
    assert result.capability.id == cap_id
    assert result.capability.agent_type == unique_agent_type
    assert result.capability.can_edit is True  # Same org can edit


@pytest.mark.asyncio
async def test_get_capability_returns_spec_yaml(test_db):
    """Should return the original spec_yaml used to create the capability."""
    from src.api.routers.capabilities import (
        create_capability,
        get_capability,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"spec_yaml_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""agent_type: {unique_agent_type}
name: Spec YAML Test Agent
description: Testing that spec_yaml is preserved
domain: testing
task_type: creative
system_prompt: |
  You are a creative agent.
  Be creative and helpful.
inputs:
  prompt:
    type: string
    required: true
    description: The creative prompt
outputs:
  creation:
    type: string
    description: The creative output
execution_hints:
  deterministic: false
  speed: slow
  cost: high
"""
    create_result = await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    cap_id = create_result.capability.id

    # Get the capability and verify spec_yaml is preserved
    result = await get_capability(
        capability_id=cap_id,
        db=test_db,
        current_user=mock_user,
    )

    assert result.capability.spec_yaml is not None
    assert unique_agent_type in result.capability.spec_yaml
    assert "creative agent" in result.capability.spec_yaml.lower()
    assert "execution_hints" in result.capability.spec_yaml


# CAP-013: Search Capability Integration Tests

@pytest.mark.asyncio
async def test_search_capabilities_keyword_basic(test_db, seed_capabilities):
    """Should find capabilities matching keyword search terms."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    # Patch embedding generation to return None (force keyword search)
    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="summarize content",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # Should return results using keyword search
    assert result.search_type == "keyword"
    # Should find capabilities matching "summarize" or "content"
    assert result.count >= 1
    # Verify the response structure
    assert result.query == "summarize content"


@pytest.mark.asyncio
async def test_search_capabilities_filters_by_domain(test_db, seed_capabilities):
    """Should filter search results by domain."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="test",
            domain="content",  # Filter to content domain
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # All results should be in content domain
    for cap in result.results:
        assert cap.domain == "content"


@pytest.mark.asyncio
async def test_search_capabilities_filters_by_tags(test_db, seed_capabilities):
    """Should filter search results by tags."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="agent",
            domain=None,
            tags=["research"],  # Filter by research tag
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # All results should have research tag
    for cap in result.results:
        assert "research" in cap.tags or any("research" in t.lower() for t in cap.tags)


@pytest.mark.asyncio
async def test_search_capabilities_org_scoping(test_db, seed_capabilities):
    """Should respect organization scoping in search."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    # User from the org that owns custom_reporter
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="reporter custom",
            domain=None,
            tags=None,
            include_system=False,  # Only custom caps
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # Should find the custom_reporter capability
    assert result.count >= 1
    # Verify can_edit flag is set correctly
    for cap in result.results:
        if not cap.is_system and str(cap.organization_id) == str(seed_capabilities["org_id"]):
            assert cap.can_edit is True


@pytest.mark.asyncio
async def test_search_capabilities_exclude_system(test_db, seed_capabilities):
    """Should exclude system capabilities when include_system=False."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {"organization_id": str(seed_capabilities["org_id"])}

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="agent",
            domain=None,
            tags=None,
            include_system=False,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # All results should be non-system
    for cap in result.results:
        assert cap.is_system is False


@pytest.mark.asyncio
async def test_search_capabilities_empty_no_system_no_org(test_db):
    """Should return empty when no system caps and no org_id."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    # User without organization
    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}  # No org

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="test agent",
            domain=None,
            tags=None,
            include_system=False,  # No system caps
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # Should return empty
    assert result.count == 0
    assert result.results == []


@pytest.mark.asyncio
async def test_search_capabilities_returns_match_type(test_db, seed_capabilities):
    """Should return match_type in search results."""
    from src.api.routers.capabilities import search_capabilities
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    mock_user = MagicMock()
    mock_user.id = uuid4()
    mock_user.metadata = {}

    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query="summarize",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # Results should indicate keyword match type
    assert result.search_type == "keyword"
    for cap in result.results:
        assert cap.match_type == "keyword"
        assert isinstance(cap.similarity, float)
        assert 0.0 <= cap.similarity <= 1.0


@pytest.mark.asyncio
async def test_search_capabilities_returns_keywords(test_db):
    """Should return keywords in search results."""
    from src.api.routers.capabilities import (
        create_capability,
        search_capabilities,
        CreateCapabilityRequest
    )
    from src.api.routers import capabilities as cap_module
    from unittest.mock import MagicMock, patch

    cap_module.database = test_db

    org_id = uuid4()
    user_id = uuid4()
    unique_agent_type = f"search_kw_test_{uuid4().hex[:8]}"

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.metadata = {"organization_id": str(org_id)}

    yaml_spec = f"""
agent_type: {unique_agent_type}
name: Search Keywords Test Agent
description: An agent for testing keyword extraction
domain: testing
system_prompt: You are a test agent.
inputs:
  user_query:
    type: string
  analysis_depth:
    type: integer
outputs:
  analysis_result:
    type: object
"""
    # Create the capability
    await create_capability(
        request=CreateCapabilityRequest(spec_yaml=yaml_spec),
        db=test_db,
        current_user=mock_user,
    )

    # Search for it
    with patch("src.api.routers.capabilities._generate_query_embedding", return_value=None):
        result = await search_capabilities(
            query=unique_agent_type,
            domain=None,
            tags=None,
            include_system=False,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=test_db,
            current_user=mock_user,
        )

    # Should find our capability with keywords
    assert result.count >= 1
    found_cap = next(
        (c for c in result.results if c.agent_type == unique_agent_type),
        None
    )
    assert found_cap is not None
    # Keywords should be populated from extraction during create
    assert isinstance(found_cap.keywords, list)
