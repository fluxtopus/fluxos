"""Integration tests for UnifiedCapabilityRegistry org scoping (CAP-010).

Tests that the registry properly resolves capabilities with organization scoping:
1. User-defined agents take priority over system agents
2. Different orgs see their own custom agents
3. list_for_planner() filters by organization
"""

import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy import select

from src.capabilities.unified_registry import (
    UnifiedCapabilityRegistry,
    CapabilityType,
)
from src.database.capability_models import AgentCapability


@pytest_asyncio.fixture
async def registry_with_db(test_db):
    """Create a registry instance with the test database."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()
    yield registry
    await registry.cleanup()


@pytest_asyncio.fixture
async def org_scoped_capabilities(test_db):
    """Seed test capabilities with org scoping scenario.

    Creates:
    - System agent: summarize
    - Org A custom agent: summarize (overrides system)
    - Org A custom agent: org_a_special
    - Org B custom agent: summarize (different override)
    """
    system_cap_id = uuid4()
    org_a_cap_id = uuid4()
    org_a_special_id = uuid4()
    org_b_cap_id = uuid4()
    org_a_id = uuid4()
    org_b_id = uuid4()

    async with test_db.get_session() as session:
        # System capability - summarize
        system_summarize = AgentCapability(
            id=system_cap_id,
            organization_id=None,
            agent_type="summarize",
            name="System Summarize Agent",
            description="System-level text summarizer",
            domain="content",
            task_type="general",
            system_prompt="You are a system summarization agent.",
            inputs_schema={"text": {"type": "string", "required": True}},
            outputs_schema={"summary": {"type": "string"}},
            is_system=True,
            is_active=True,
            version=1,
            is_latest=True,
        )

        # Org A custom agent - overrides summarize
        org_a_summarize = AgentCapability(
            id=org_a_cap_id,
            organization_id=org_a_id,
            agent_type="summarize",
            name="Org A Custom Summarize",
            description="Org A custom summarizer with special formatting",
            domain="content",
            task_type="general",
            system_prompt="You are Org A's custom summarization agent.",
            inputs_schema={"text": {"type": "string", "required": True}},
            outputs_schema={"summary": {"type": "string"}},
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
        )

        # Org A unique agent
        org_a_special = AgentCapability(
            id=org_a_special_id,
            organization_id=org_a_id,
            agent_type="org_a_analyzer",
            name="Org A Special Analyzer",
            description="Special analyzer only available to Org A",
            domain="analysis",
            task_type="reasoning",
            system_prompt="You are Org A's special analyzer.",
            inputs_schema={"data": {"type": "object", "required": True}},
            outputs_schema={"analysis": {"type": "object"}},
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
        )

        # Org B custom agent - different override of summarize
        org_b_summarize = AgentCapability(
            id=org_b_cap_id,
            organization_id=org_b_id,
            agent_type="summarize",
            name="Org B Custom Summarize",
            description="Org B custom summarizer - bullet points only",
            domain="content",
            task_type="general",
            system_prompt="You are Org B's custom summarization agent.",
            inputs_schema={"text": {"type": "string", "required": True}},
            outputs_schema={"summary": {"type": "string"}},
            is_system=False,
            is_active=True,
            version=1,
            is_latest=True,
        )

        session.add(system_summarize)
        session.add(org_a_summarize)
        session.add(org_a_special)
        session.add(org_b_summarize)
        await session.commit()

    return {
        "system_cap_id": system_cap_id,
        "org_a_cap_id": org_a_cap_id,
        "org_a_special_id": org_a_special_id,
        "org_b_cap_id": org_b_cap_id,
        "org_a_id": str(org_a_id),
        "org_b_id": str(org_b_id),
    }


@pytest.mark.asyncio
async def test_resolve_prefers_org_agent_over_system(test_db, org_scoped_capabilities):
    """Org-specific agent should take priority over system agent."""
    # Create fresh registry after seeding
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]

    # Resolve with org A context
    resolved = await registry.resolve("summarize", organization_id=org_a_id)

    assert resolved is not None
    assert resolved.name == "summarize"
    assert resolved.organization_id == org_a_id
    assert resolved.config.description == "Org A custom summarizer with special formatting"

    await registry.cleanup()


@pytest.mark.asyncio
async def test_resolve_falls_back_to_system_without_org(test_db, org_scoped_capabilities):
    """Without org_id, should resolve to system agent."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    # Resolve without org context
    resolved = await registry.resolve("summarize")

    assert resolved is not None
    assert resolved.name == "summarize"
    assert resolved.organization_id is None
    assert resolved.config.is_system is True
    assert resolved.config.description == "System-level text summarizer"

    await registry.cleanup()


@pytest.mark.asyncio
async def test_resolve_different_orgs_get_different_agents(test_db, org_scoped_capabilities):
    """Different orgs should get their own versions of same-named agent."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]
    org_b_id = org_scoped_capabilities["org_b_id"]

    # Resolve for Org A
    resolved_a = await registry.resolve("summarize", organization_id=org_a_id)
    assert resolved_a.config.description == "Org A custom summarizer with special formatting"

    # Resolve for Org B
    resolved_b = await registry.resolve("summarize", organization_id=org_b_id)
    assert resolved_b.config.description == "Org B custom summarizer - bullet points only"

    # They should be different capabilities
    assert resolved_a.config.id != resolved_b.config.id

    await registry.cleanup()


@pytest.mark.asyncio
async def test_resolve_org_unique_agent_only_visible_to_org(test_db, org_scoped_capabilities):
    """Org-specific unique agent should only be visible to that org."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]
    org_b_id = org_scoped_capabilities["org_b_id"]

    # Org A can see org_a_analyzer
    resolved_a = await registry.resolve("org_a_analyzer", organization_id=org_a_id)
    assert resolved_a is not None
    assert resolved_a.config.description == "Special analyzer only available to Org A"

    # Org B cannot see org_a_analyzer
    resolved_b = await registry.resolve("org_a_analyzer", organization_id=org_b_id)
    assert resolved_b is None

    # No org context cannot see org_a_analyzer
    resolved_none = await registry.resolve("org_a_analyzer")
    assert resolved_none is None

    await registry.cleanup()


@pytest.mark.asyncio
async def test_list_for_planner_includes_org_agents(test_db, org_scoped_capabilities):
    """list_for_planner should include org-specific agents when org_id provided."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]

    # Get planner docs for Org A
    docs = await registry.list_for_planner(organization_id=org_a_id)

    # Should include org A's unique agent
    assert "org_a_analyzer" in docs
    # Should include custom marker for org agents
    assert "[custom]" in docs
    # Should include Org A's description (overrides system)
    assert "Org A custom summarizer" in docs

    await registry.cleanup()


@pytest.mark.asyncio
async def test_list_for_planner_without_org_only_system(test_db, org_scoped_capabilities):
    """list_for_planner without org_id should only show system capabilities."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    # Get planner docs without org context
    docs = await registry.list_for_planner()

    # Should NOT include org-specific agents
    assert "org_a_analyzer" not in docs
    assert "Org A custom summarizer" not in docs
    assert "Org B custom summarizer" not in docs
    # Should include system summarize
    assert "summarize" in docs
    assert "System-level text summarizer" in docs

    await registry.cleanup()


@pytest.mark.asyncio
async def test_list_agents_with_org_includes_custom(test_db, org_scoped_capabilities):
    """list_agents with org_id should include org's custom agents."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]

    # Get agent list for Org A
    agents = registry.list_agents(organization_id=org_a_id)

    # Find agent types
    agent_types = {a["agent_type"] for a in agents}

    # Should include summarize (org A's version overrides system)
    assert "summarize" in agent_types
    # Should include org A's unique agent
    assert "org_a_analyzer" in agent_types

    # Verify the summarize is Org A's custom one
    summarize = next(a for a in agents if a["agent_type"] == "summarize")
    assert summarize["is_custom"] is True
    assert summarize["description"] == "Org A custom summarizer with special formatting"

    await registry.cleanup()


@pytest.mark.asyncio
async def test_list_agents_without_org_only_system(test_db, org_scoped_capabilities):
    """list_agents without org_id should only return system agents."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    # Get agent list without org context
    agents = registry.list_agents()

    # Find agent types
    agent_types = {a["agent_type"] for a in agents}

    # Should include system summarize
    assert "summarize" in agent_types
    # Should NOT include org-specific agents
    assert "org_a_analyzer" not in agent_types

    # Verify the summarize is the system one
    summarize = next(a for a in agents if a["agent_type"] == "summarize")
    assert summarize["is_system"] is True
    assert summarize["is_custom"] is False
    assert summarize["description"] == "System-level text summarizer"

    await registry.cleanup()


@pytest.mark.asyncio
async def test_resolve_by_type_respects_org_scoping(test_db, org_scoped_capabilities):
    """_resolve_by_type should also respect org scoping."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]

    # Resolve with explicit type and org context
    resolved = await registry._resolve_by_type(
        "summarize", "agent", organization_id=org_a_id
    )

    assert resolved is not None
    assert resolved.organization_id == org_a_id
    assert resolved.config.description == "Org A custom summarizer with special formatting"

    await registry.cleanup()


@pytest.mark.asyncio
async def test_refresh_updates_org_caches(test_db, org_scoped_capabilities):
    """Refresh should update org-scoped caches."""
    registry = UnifiedCapabilityRegistry(db=test_db)
    await registry.initialize()

    org_a_id = org_scoped_capabilities["org_a_id"]

    # Verify initial state
    resolved = await registry.resolve("summarize", organization_id=org_a_id)
    assert resolved.config.description == "Org A custom summarizer with special formatting"

    # Update the capability in database
    async with test_db.get_session() as session:
        query = select(AgentCapability).where(
            AgentCapability.id == org_scoped_capabilities["org_a_cap_id"]
        )
        result = await session.execute(query)
        cap = result.scalar_one()
        cap.description = "Updated Org A description"
        await session.commit()

    # Refresh registry
    await registry.refresh()

    # Verify updated description
    resolved_updated = await registry.resolve("summarize", organization_id=org_a_id)
    assert resolved_updated.config.description == "Updated Org A description"

    await registry.cleanup()
