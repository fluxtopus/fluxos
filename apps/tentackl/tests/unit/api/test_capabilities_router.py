"""Unit tests for the capabilities router (CAP-004, CAP-005).

Tests the /api/capabilities/agents endpoints for the unified capabilities system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime, timezone

from src.api.routers.capabilities import (
    CapabilityListItem,
    CapabilitiesListResponse,
    CapabilityDetail,
    CreateCapabilityRequest,
    CreateCapabilityResponse,
    GetCapabilityResponse,
    list_capabilities,
    create_capability,
    get_capability,
    validate_capability_spec,
    _extract_keywords,
)


class TestCapabilityModels:
    """Tests for Pydantic request/response models."""

    def test_capability_list_item_defaults(self):
        """Should have proper defaults."""
        item = CapabilityListItem(
            id=uuid4(),
            agent_type="summarize",
            name="Summarize Agent",
            task_type="general",
            is_system=True,
            is_active=True,
            version=1,
            is_latest=True,
            usage_count=0,
            success_count=0,
            failure_count=0,
        )

        assert item.agent_type == "summarize"
        assert item.tags == []
        assert item.can_edit is False
        assert item.description is None
        assert item.domain is None

    def test_capability_list_item_with_all_fields(self):
        """Should handle all fields correctly."""
        cap_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        item = CapabilityListItem(
            id=cap_id,
            agent_type="web_research",
            name="Web Research Agent",
            description="Searches the web for information",
            domain="research",
            task_type="reasoning",
            is_system=False,
            is_active=True,
            organization_id=org_id,
            version=2,
            is_latest=True,
            tags=["web", "research", "search"],
            usage_count=100,
            success_count=95,
            failure_count=5,
            last_used_at=now,
            created_at=now,
            updated_at=now,
            can_edit=True,
        )

        assert item.id == cap_id
        assert item.organization_id == org_id
        assert item.tags == ["web", "research", "search"]
        assert item.usage_count == 100
        assert item.success_count == 95
        assert item.can_edit is True

    def test_capabilities_list_response(self):
        """Should serialize list response correctly."""
        cap_id = uuid4()
        response = CapabilitiesListResponse(
            capabilities=[
                CapabilityListItem(
                    id=cap_id,
                    agent_type="test",
                    name="Test Agent",
                    task_type="general",
                    is_system=True,
                    is_active=True,
                    version=1,
                    is_latest=True,
                    usage_count=0,
                    success_count=0,
                    failure_count=0,
                )
            ],
            count=1,
            total=10,
            limit=100,
            offset=0,
        )

        assert response.count == 1
        assert response.total == 10
        assert len(response.capabilities) == 1


@pytest.mark.asyncio
class TestListCapabilities:
    """Tests for list_capabilities endpoint."""

    @patch("src.api.routers.capabilities.database")
    async def test_list_capabilities_empty(self, mock_db):
        """Should return empty list when no capabilities exist."""
        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # Mock main query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_main_result = MagicMock()
        mock_main_result.scalars.return_value = mock_scalars

        # Setup execute to return different results based on call order
        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_main_result])

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.metadata = {"organization_id": str(uuid4())}

        # Import and patch the module-level database
        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await list_capabilities(
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=100,
            offset=0,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.count == 0
        assert result.total == 0
        assert result.capabilities == []

    @patch("src.api.routers.capabilities.database")
    async def test_list_capabilities_with_results(self, mock_db):
        """Should return capabilities list."""
        cap_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "summarize"
        mock_cap.name = "Summarize Agent"
        mock_cap.description = "Summarizes content"
        mock_cap.domain = "content"
        mock_cap.task_type = "general"
        mock_cap.is_system = True
        mock_cap.is_active = True
        mock_cap.organization_id = None
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.tags = ["content", "summary"]
        mock_cap.usage_count = 50
        mock_cap.success_count = 48
        mock_cap.failure_count = 2
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock main query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_cap]
        mock_main_result = MagicMock()
        mock_main_result.scalars.return_value = mock_scalars

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_main_result])
        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.metadata = {"organization_id": str(org_id)}

        # Import and patch the module-level database
        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await list_capabilities(
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=100,
            offset=0,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.count == 1
        assert result.total == 1
        assert len(result.capabilities) == 1
        assert result.capabilities[0].agent_type == "summarize"
        assert result.capabilities[0].is_system is True
        # System capabilities cannot be edited by users
        assert result.capabilities[0].can_edit is False

    @patch("src.api.routers.capabilities.database")
    async def test_list_capabilities_user_can_edit_own(self, mock_db):
        """Should set can_edit=True for user's own capabilities."""
        cap_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock user-owned capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "custom_agent"
        mock_cap.name = "Custom Agent"
        mock_cap.description = "My custom agent"
        mock_cap.domain = "custom"
        mock_cap.task_type = "general"
        mock_cap.is_system = False  # User-created
        mock_cap.is_active = True
        mock_cap.organization_id = org_id  # Owned by user's org
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.tags = []
        mock_cap.usage_count = 10
        mock_cap.success_count = 9
        mock_cap.failure_count = 1
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_cap]
        mock_main_result = MagicMock()
        mock_main_result.scalars.return_value = mock_scalars

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_main_result])
        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user from same org
        mock_user = MagicMock()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await list_capabilities(
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=100,
            offset=0,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.count == 1
        # User can edit their own org's non-system capabilities
        assert result.capabilities[0].can_edit is True

    async def test_list_capabilities_no_system_no_org(self):
        """Should return empty when include_system=False and no org_id."""
        # Mock user without organization
        mock_user = MagicMock()
        mock_user.metadata = {}  # No org_id

        mock_db = MagicMock()

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await list_capabilities(
            domain=None,
            tags=None,
            include_system=False,  # No system caps
            active_only=True,
            limit=100,
            offset=0,
            db=mock_db,
            current_user=mock_user,
        )

        # Should return empty - no org caps (no org_id) and no system caps requested
        assert result.count == 0
        assert result.total == 0


class TestCapabilityFilters:
    """Tests for capability filtering logic."""

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.database")
    async def test_filter_by_domain(self, mock_db):
        """Should filter capabilities by domain."""
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "web_search"
        mock_cap.name = "Web Search"
        mock_cap.description = "Searches the web"
        mock_cap.domain = "research"
        mock_cap.task_type = "general"
        mock_cap.is_system = True
        mock_cap.is_active = True
        mock_cap.organization_id = None
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.tags = []
        mock_cap.usage_count = 0
        mock_cap.success_count = 0
        mock_cap.failure_count = 0
        mock_cap.last_used_at = None
        mock_cap.created_at = now
        mock_cap.updated_at = now

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_cap]
        mock_main_result = MagicMock()
        mock_main_result.scalars.return_value = mock_scalars

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_main_result])
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.metadata = {"organization_id": str(uuid4())}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await list_capabilities(
            domain="research",  # Filter by domain
            tags=None,
            include_system=True,
            active_only=True,
            limit=100,
            offset=0,
            db=mock_db,
            current_user=mock_user,
        )

        # The mock returns results regardless of filters - we're testing the endpoint works
        # Real filtering is tested in integration tests
        assert result.count == 1
        assert result.capabilities[0].domain == "research"


# Tests for CAP-005: Create Capability Endpoint

class TestCreateCapabilityModels:
    """Tests for create capability request/response models."""

    def test_create_capability_request_valid_yaml(self):
        """Should accept valid YAML."""
        yaml_spec = """
agent_type: my_summarizer
name: My Custom Summarizer
system_prompt: You are a helpful summarizer.
inputs:
  content:
    type: string
    required: true
"""
        request = CreateCapabilityRequest(spec_yaml=yaml_spec)
        assert "my_summarizer" in request.spec_yaml

    def test_create_capability_request_invalid_yaml(self):
        """Should reject invalid YAML."""
        invalid_yaml = """
agent_type: test
  bad_indent: true
name: broken
"""
        with pytest.raises(ValueError, match="Invalid YAML"):
            CreateCapabilityRequest(spec_yaml=invalid_yaml)

    def test_create_capability_request_with_tags(self):
        """Should accept optional tags."""
        yaml_spec = """
agent_type: test_agent
system_prompt: Test prompt
inputs:
  data:
    type: string
    required: true
"""
        request = CreateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["custom", "test"]
        )
        assert request.tags == ["custom", "test"]

    def test_capability_detail_model(self):
        """Should create CapabilityDetail with all fields."""
        cap_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        detail = CapabilityDetail(
            id=cap_id,
            agent_type="custom_agent",
            name="Custom Agent",
            description="A custom agent",
            domain="custom",
            task_type="general",
            system_prompt="You are a helpful agent.",
            inputs_schema={"content": {"type": "string"}},
            outputs_schema={"result": {"type": "string"}},
            examples=[{"input": "test"}],
            execution_hints={"speed": "fast"},
            is_system=False,
            is_active=True,
            organization_id=org_id,
            version=1,
            is_latest=True,
            created_by=user_id,
            tags=["custom"],
            spec_yaml="agent_type: custom_agent",
            usage_count=0,
            success_count=0,
            failure_count=0,
            last_used_at=None,
            created_at=now,
            updated_at=now,
            can_edit=True,
        )

        assert detail.id == cap_id
        assert detail.agent_type == "custom_agent"
        assert detail.is_system is False
        assert detail.can_edit is True


class TestValidateCapabilitySpec:
    """Tests for validate_capability_spec function."""

    def test_valid_spec(self):
        """Should return no errors for valid spec."""
        spec = {
            "agent_type": "my_agent",
            "system_prompt": "You are a helpful agent.",
            "inputs": {
                "content": {"type": "string", "required": True}
            }
        }
        errors = validate_capability_spec(spec)
        assert errors == []

    def test_missing_agent_type(self):
        """Should report missing agent_type."""
        spec = {
            "system_prompt": "Test",
            "inputs": {"data": {"type": "string"}}
        }
        errors = validate_capability_spec(spec)
        assert "Missing required field: agent_type" in errors

    def test_missing_system_prompt(self):
        """Should report missing system_prompt."""
        spec = {
            "agent_type": "test",
            "inputs": {"data": {"type": "string"}}
        }
        errors = validate_capability_spec(spec)
        assert "Missing required field: system_prompt" in errors

    def test_missing_inputs(self):
        """Should report missing inputs."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test prompt"
        }
        errors = validate_capability_spec(spec)
        assert "Missing required field: inputs" in errors

    def test_invalid_agent_type_format(self):
        """Should report invalid agent_type format."""
        spec = {
            "agent_type": "my agent!",  # Invalid characters
            "system_prompt": "Test",
            "inputs": {"data": {"type": "string"}}
        }
        errors = validate_capability_spec(spec)
        assert any("alphanumeric" in e for e in errors)

    def test_inputs_must_be_dict(self):
        """Should report when inputs is not a dict."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test",
            "inputs": "not a dict"
        }
        errors = validate_capability_spec(spec)
        assert any("inputs must be an object" in e for e in errors)

    def test_input_missing_type(self):
        """Should report when input field lacks type."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test",
            "inputs": {
                "data": {"required": True}  # Missing type
            }
        }
        errors = validate_capability_spec(spec)
        assert "Input 'data' missing required 'type' field" in errors

    def test_outputs_validation(self):
        """Should validate outputs structure if present."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test",
            "inputs": {"data": {"type": "string"}},
            "outputs": {
                "result": {"description": "No type field"}  # Missing type
            }
        }
        errors = validate_capability_spec(spec)
        assert "Output 'result' missing required 'type' field" in errors

    def test_invalid_task_type(self):
        """Should report invalid task_type."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test",
            "inputs": {"data": {"type": "string"}},
            "task_type": "invalid_type"
        }
        errors = validate_capability_spec(spec)
        # Validation service returns "Invalid task_type 'X'. Valid values: ..."
        assert any("Invalid task_type" in e or "task_type" in e for e in errors)

    def test_valid_task_types(self):
        """Should accept valid task types."""
        for task_type in ["general", "reasoning", "creative", "web_research", "analysis"]:
            spec = {
                "agent_type": "test",
                "system_prompt": "Test",
                "inputs": {"data": {"type": "string"}},
                "task_type": task_type
            }
            errors = validate_capability_spec(spec)
            assert not any("task_type" in e for e in errors)


class TestExtractKeywords:
    """Tests for _extract_keywords helper function."""

    def test_extracts_from_agent_type(self):
        """Should extract words from agent_type."""
        spec = {
            "agent_type": "web_content_analyzer",
            "name": "Test",
        }
        keywords = _extract_keywords(spec)
        assert "web" in keywords
        assert "content" in keywords
        assert "analyzer" in keywords

    def test_extracts_from_name(self):
        """Should extract words from name."""
        spec = {
            "agent_type": "test",
            "name": "Advanced Data Processor",
        }
        keywords = _extract_keywords(spec)
        assert "advanced" in keywords
        assert "data" in keywords
        assert "processor" in keywords

    def test_extracts_from_domain(self):
        """Should extract domain."""
        spec = {
            "agent_type": "test",
            "domain": "analytics",
        }
        keywords = _extract_keywords(spec)
        assert "analytics" in keywords

    def test_extracts_from_input_names(self):
        """Should extract input field names."""
        spec = {
            "agent_type": "test",
            "inputs": {
                "user_query": {"type": "string"},
                "max_results": {"type": "integer"},
            }
        }
        keywords = _extract_keywords(spec)
        assert "user" in keywords
        assert "query" in keywords
        assert "max" in keywords
        assert "results" in keywords

    def test_extracts_from_output_names(self):
        """Should extract output field names."""
        spec = {
            "agent_type": "test",
            "outputs": {
                "search_results": {"type": "array"},
            }
        }
        keywords = _extract_keywords(spec)
        assert "search" in keywords
        assert "results" in keywords

    def test_removes_stop_words(self):
        """Should remove common stop words."""
        spec = {
            "agent_type": "test",
            "name": "The Best Agent for Analysis",
        }
        keywords = _extract_keywords(spec)
        assert "the" not in keywords
        assert "for" not in keywords

    def test_removes_short_words(self):
        """Should remove very short words."""
        spec = {
            "agent_type": "an",
            "name": "A B C Test",
        }
        keywords = _extract_keywords(spec)
        assert "an" not in keywords
        # "A", "B", "C" would be lowercase and too short

    def test_limits_keywords(self):
        """Should limit to 20 keywords."""
        spec = {
            "agent_type": "one_two_three_four_five_six_seven_eight_nine_ten",
            "name": "Word1 Word2 Word3 Word4 Word5 Word6 Word7 Word8 Word9 Word10",
            "inputs": {
                "field1": {}, "field2": {}, "field3": {}, "field4": {}, "field5": {},
            },
            "outputs": {
                "out1": {}, "out2": {}, "out3": {}, "out4": {}, "out5": {},
            }
        }
        keywords = _extract_keywords(spec)
        assert len(keywords) <= 20


@pytest.mark.asyncio
class TestCreateCapability:
    """Tests for create_capability endpoint."""

    @patch("src.api.routers.capabilities.database")
    async def test_create_capability_success(self, mock_db):
        """Should create capability successfully."""
        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        yaml_spec = """
agent_type: my_custom_agent
name: My Custom Agent
description: A custom summarization agent
domain: content
task_type: reasoning
system_prompt: You are a helpful summarization agent.
inputs:
  content:
    type: string
    required: true
    description: Content to summarize
outputs:
  summary:
    type: string
    description: The summarized content
execution_hints:
  speed: fast
  cost: low
"""
        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock check for existing capability
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None  # No existing

        mock_session.execute = AsyncMock(return_value=mock_existing_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Mock refresh to set the capability properties
        async def mock_refresh(cap):
            cap.id = cap_id
            cap.created_at = now
            cap.updated_at = now
        mock_session.refresh = mock_refresh

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user with organization
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = CreateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["custom", "summarizer"]
        )

        result = await create_capability(
            request=request,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.message == "Capability created successfully"
        assert result.capability.agent_type == "my_custom_agent"
        assert result.capability.name == "My Custom Agent"
        assert result.capability.is_system is False
        assert result.capability.can_edit is True
        assert result.capability.version == 1
        assert result.capability.is_latest is True

        # Verify session.add was called
        mock_session.add.assert_called_once()

    @patch("src.api.routers.capabilities.database")
    async def test_create_capability_missing_required_fields(self, mock_db):
        """Should reject spec missing required fields."""
        org_id = uuid4()
        user_id = uuid4()

        # Missing system_prompt and inputs
        yaml_spec = """
agent_type: incomplete_agent
name: Incomplete Agent
"""
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = CreateCapabilityRequest(spec_yaml=yaml_spec)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_capability(
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid capability specification" in str(exc_info.value.detail)

    @patch("src.api.routers.capabilities.database")
    async def test_create_capability_no_organization(self, mock_db):
        """Should reject if user has no organization."""
        user_id = uuid4()

        yaml_spec = """
agent_type: test_agent
system_prompt: Test
inputs:
  data:
    type: string
"""
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {}  # No organization_id

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = CreateCapabilityRequest(spec_yaml=yaml_spec)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_capability(
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_create_capability_duplicate_agent_type(self, mock_db):
        """Should reject duplicate agent_type within organization."""
        org_id = uuid4()
        user_id = uuid4()

        yaml_spec = """
agent_type: existing_agent
system_prompt: Test
inputs:
  data:
    type: string
"""
        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock existing capability found
        mock_existing = MagicMock()
        mock_existing.id = uuid4()
        mock_existing.agent_type = "existing_agent"

        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = mock_existing

        mock_session.execute = AsyncMock(return_value=mock_existing_result)
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = CreateCapabilityRequest(spec_yaml=yaml_spec)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_capability(
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    @patch("src.api.routers.capabilities.database")
    async def test_create_capability_sets_embedding_status_pending(self, mock_db):
        """Should set embedding_status to pending for later background processing."""
        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        yaml_spec = """
agent_type: test_agent
system_prompt: Test prompt
inputs:
  data:
    type: string
"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_existing_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Capture the added capability
        added_capability = None
        def capture_add(cap):
            nonlocal added_capability
            added_capability = cap
        mock_session.add = capture_add

        async def mock_refresh(cap):
            cap.id = cap_id
            cap.created_at = now
            cap.updated_at = now
        mock_session.refresh = mock_refresh

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = CreateCapabilityRequest(spec_yaml=yaml_spec)

        result = await create_capability(
            request=request,
            db=mock_db,
            current_user=mock_user,
        )

        # Verify embedding_status was set to pending
        assert added_capability is not None
        assert added_capability.embedding_status == "pending"


# Tests for CAP-006: Update Capability Endpoint

class TestUpdateCapabilityModels:
    """Tests for update capability request/response models."""

    def test_update_capability_request_empty(self):
        """Should allow empty update request (no changes)."""
        from src.api.routers.capabilities import UpdateCapabilityRequest
        request = UpdateCapabilityRequest()
        assert request.spec_yaml is None
        assert request.tags is None
        assert request.is_active is None

    def test_update_capability_request_valid_yaml(self):
        """Should accept valid YAML."""
        from src.api.routers.capabilities import UpdateCapabilityRequest
        yaml_spec = """
agent_type: updated_agent
system_prompt: Updated prompt
inputs:
  data:
    type: string
"""
        request = UpdateCapabilityRequest(spec_yaml=yaml_spec)
        assert "updated_agent" in request.spec_yaml

    def test_update_capability_request_invalid_yaml(self):
        """Should reject invalid YAML."""
        from src.api.routers.capabilities import UpdateCapabilityRequest
        invalid_yaml = """
agent_type: test
  bad_indent: true
"""
        with pytest.raises(ValueError, match="Invalid YAML"):
            UpdateCapabilityRequest(spec_yaml=invalid_yaml)

    def test_update_capability_request_with_all_fields(self):
        """Should accept all optional fields."""
        from src.api.routers.capabilities import UpdateCapabilityRequest
        yaml_spec = """
agent_type: test_agent
system_prompt: Test prompt
inputs:
  data:
    type: string
"""
        request = UpdateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["updated", "custom"],
            is_active=False
        )
        assert request.tags == ["updated", "custom"]
        assert request.is_active is False

    def test_update_capability_response_model(self):
        """Should create UpdateCapabilityResponse with version_created flag."""
        from src.api.routers.capabilities import UpdateCapabilityResponse, CapabilityDetail
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        detail = CapabilityDetail(
            id=cap_id,
            agent_type="test_agent",
            name="Test Agent",
            task_type="general",
            system_prompt="Test prompt",
            is_system=False,
            is_active=True,
            version=2,
            is_latest=True,
            usage_count=0,
            success_count=0,
            failure_count=0,
            created_at=now,
            updated_at=now,
            can_edit=True,
        )

        response = UpdateCapabilityResponse(
            capability=detail,
            message="New version 2 created",
            version_created=True
        )

        assert response.version_created is True
        assert response.capability.version == 2


@pytest.mark.asyncio
class TestUpdateCapability:
    """Tests for update_capability endpoint."""

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_metadata_only(self, mock_db):
        """Should update metadata without creating new version."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock existing capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "test_agent"
        mock_cap.name = "Test Agent"
        mock_cap.description = "Original description"
        mock_cap.domain = "test"
        mock_cap.task_type = "general"
        mock_cap.system_prompt = "Original prompt"
        mock_cap.inputs_schema = {"data": {"type": "string"}}
        mock_cap.outputs_schema = {}
        mock_cap.examples = []
        mock_cap.execution_hints = {}
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.created_by = user_id
        mock_cap.tags = ["old-tag"]
        mock_cap.spec_yaml = "agent_type: test_agent"
        mock_cap.usage_count = 10
        mock_cap.success_count = 8
        mock_cap.failure_count = 2
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock fetch capability
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        # Update only tags (no spec change)
        request = UpdateCapabilityRequest(
            tags=["new-tag", "updated"]
        )

        result = await update_capability(
            capability_id=cap_id,
            request=request,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.version_created is False
        assert mock_cap.tags == ["new-tag", "updated"]

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_not_found(self, mock_db):
        """Should return 404 for non-existent capability."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
        from fastapi import HTTPException

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock no capability found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(tags=["test"])

        with pytest.raises(HTTPException) as exc_info:
            await update_capability(
                capability_id=cap_id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_system_capability_rejected(self, mock_db):
        """Should reject updates to system capabilities."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
        from fastapi import HTTPException

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock system capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.is_system = True
        mock_cap.organization_id = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(tags=["test"])

        with pytest.raises(HTTPException) as exc_info:
            await update_capability(
                capability_id=cap_id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "system capabilities" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_wrong_organization_rejected(self, mock_db):
        """Should reject updates from different organization."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
        from fastapi import HTTPException

        org_id = uuid4()
        other_org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock capability from different org
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.is_system = False
        mock_cap.organization_id = other_org_id  # Different org!

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(tags=["test"])

        with pytest.raises(HTTPException) as exc_info:
            await update_capability(
                capability_id=cap_id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "your organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_no_organization_rejected(self, mock_db):
        """Should reject if user has no organization."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
        from fastapi import HTTPException

        user_id = uuid4()
        cap_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {}  # No organization_id

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(tags=["test"])

        with pytest.raises(HTTPException) as exc_info:
            await update_capability(
                capability_id=cap_id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_spec_creates_new_version(self, mock_db):
        """Should create new version when spec_yaml changes."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()
        new_cap_id = uuid4()
        now = datetime.now(timezone.utc)

        original_yaml = """agent_type: test_agent
system_prompt: Original prompt
inputs:
  data:
    type: string
"""
        new_yaml = """agent_type: test_agent
system_prompt: Updated prompt
inputs:
  data:
    type: string
  extra:
    type: string
"""

        # Mock existing capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "test_agent"
        mock_cap.name = "Test Agent"
        mock_cap.description = "Original description"
        mock_cap.domain = "test"
        mock_cap.task_type = "general"
        mock_cap.system_prompt = "Original prompt"
        mock_cap.inputs_schema = {"data": {"type": "string"}}
        mock_cap.outputs_schema = {}
        mock_cap.examples = []
        mock_cap.execution_hints = {}
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.created_by = user_id
        mock_cap.tags = ["original"]
        mock_cap.spec_yaml = original_yaml
        mock_cap.usage_count = 10
        mock_cap.success_count = 8
        mock_cap.failure_count = 2
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock fetch capability (first call)
        mock_fetch_result = MagicMock()
        mock_fetch_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_fetch_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        # Capture the new capability added
        added_capability = None
        def capture_add(cap):
            nonlocal added_capability
            added_capability = cap
            cap.id = new_cap_id
            cap.created_at = now
            cap.updated_at = now
        mock_session.add = capture_add
        mock_session.refresh = AsyncMock()

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(spec_yaml=new_yaml)

        result = await update_capability(
            capability_id=cap_id,
            request=request,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.version_created is True
        assert "version 2" in result.message.lower()
        # Original should be marked not latest
        assert mock_cap.is_latest is False
        # New capability should have incremented version
        assert added_capability is not None
        assert added_capability.version == 2
        assert added_capability.is_latest is True
        # Analytics should be reset for new version
        assert added_capability.usage_count == 0
        assert added_capability.success_count == 0
        assert added_capability.failure_count == 0

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_invalid_spec_rejected(self, mock_db):
        """Should reject invalid YAML spec."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest
        from fastapi import HTTPException

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock existing capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.is_system = False
        mock_cap.organization_id = org_id
        mock_cap.spec_yaml = "original: yaml"

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        # Missing required fields in spec
        invalid_yaml = """
agent_type: test_agent
name: Missing system_prompt and inputs
"""
        request = UpdateCapabilityRequest(spec_yaml=invalid_yaml)

        with pytest.raises(HTTPException) as exc_info:
            await update_capability(
                capability_id=cap_id,
                request=request,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid capability specification" in str(exc_info.value.detail)

    @patch("src.api.routers.capabilities.database")
    async def test_update_capability_is_active_update(self, mock_db):
        """Should update is_active flag without creating new version."""
        from src.api.routers.capabilities import update_capability, UpdateCapabilityRequest

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "test_agent"
        mock_cap.name = "Test Agent"
        mock_cap.description = None
        mock_cap.domain = None
        mock_cap.task_type = "general"
        mock_cap.system_prompt = "Test"
        mock_cap.inputs_schema = {}
        mock_cap.outputs_schema = {}
        mock_cap.examples = []
        mock_cap.execution_hints = {}
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.created_by = user_id
        mock_cap.tags = []
        mock_cap.spec_yaml = None
        mock_cap.usage_count = 0
        mock_cap.success_count = 0
        mock_cap.failure_count = 0
        mock_cap.last_used_at = None
        mock_cap.created_at = now
        mock_cap.updated_at = now

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        request = UpdateCapabilityRequest(is_active=False)

        result = await update_capability(
            capability_id=cap_id,
            request=request,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.version_created is False
        assert mock_cap.is_active is False


# Tests for CAP-007: Delete Capability Endpoint

class TestDeleteCapabilityModels:
    """Tests for delete capability response model."""

    def test_delete_capability_response_model(self):
        """Should create DeleteCapabilityResponse with all fields."""
        from src.api.routers.capabilities import DeleteCapabilityResponse
        cap_id = uuid4()

        response = DeleteCapabilityResponse(
            id=cap_id,
            agent_type="test_agent",
            message="Capability deleted successfully"
        )

        assert response.id == cap_id
        assert response.agent_type == "test_agent"
        assert response.message == "Capability deleted successfully"

    def test_delete_capability_response_default_message(self):
        """Should have default message."""
        from src.api.routers.capabilities import DeleteCapabilityResponse
        cap_id = uuid4()

        response = DeleteCapabilityResponse(
            id=cap_id,
            agent_type="test_agent"
        )

        assert response.message == "Capability deleted successfully"


@pytest.mark.asyncio
class TestDeleteCapability:
    """Tests for delete_capability endpoint."""

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_success(self, mock_db):
        """Should soft-delete capability by setting is_active=false."""
        from src.api.routers.capabilities import delete_capability

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock existing capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "test_agent"
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await delete_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.id == cap_id
        assert result.agent_type == "test_agent"
        assert result.message == "Capability deleted successfully"
        # Verify is_active was set to False
        assert mock_cap.is_active is False
        mock_session.commit.assert_called_once()

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_not_found(self, mock_db):
        """Should return 404 for non-existent capability."""
        from src.api.routers.capabilities import delete_capability
        from fastapi import HTTPException

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock database session with no result
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_system_capability_rejected(self, mock_db):
        """Should reject deletion of system capabilities."""
        from src.api.routers.capabilities import delete_capability
        from fastapi import HTTPException

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock system capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.is_system = True
        mock_cap.organization_id = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "system capabilities" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_wrong_organization_rejected(self, mock_db):
        """Should reject deletion from different organization."""
        from src.api.routers.capabilities import delete_capability
        from fastapi import HTTPException

        org_id = uuid4()
        other_org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock capability from different org
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.is_system = False
        mock_cap.organization_id = other_org_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "your organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_no_organization_rejected(self, mock_db):
        """Should reject if user has no organization."""
        from src.api.routers.capabilities import delete_capability
        from fastapi import HTTPException

        user_id = uuid4()
        cap_id = uuid4()

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {}  # No organization_id

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await delete_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_delete_capability_already_inactive(self, mock_db):
        """Should still succeed even if capability is already inactive."""
        from src.api.routers.capabilities import delete_capability

        org_id = uuid4()
        user_id = uuid4()
        cap_id = uuid4()

        # Mock already inactive capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "test_agent"
        mock_cap.is_system = False
        mock_cap.is_active = False  # Already inactive
        mock_cap.organization_id = org_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await delete_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        # Should succeed (idempotent operation)
        assert result.id == cap_id
        assert result.message == "Capability deleted successfully"


# Tests for CAP-008: Get Single Capability Endpoint

class TestGetCapabilityModels:
    """Tests for get capability response model."""

    def test_get_capability_response_model(self):
        """Should create GetCapabilityResponse with full CapabilityDetail."""
        from src.api.routers.capabilities import GetCapabilityResponse, CapabilityDetail
        cap_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        detail = CapabilityDetail(
            id=cap_id,
            agent_type="test_agent",
            name="Test Agent",
            description="A test agent",
            domain="testing",
            task_type="general",
            system_prompt="You are a test agent.",
            inputs_schema={"data": {"type": "string"}},
            outputs_schema={"result": {"type": "string"}},
            examples=[{"input": "test", "output": "result"}],
            execution_hints={"speed": "fast", "cost": "low"},
            is_system=False,
            is_active=True,
            organization_id=org_id,
            version=1,
            is_latest=True,
            created_by=user_id,
            tags=["test", "unit"],
            spec_yaml="agent_type: test_agent\nname: Test Agent",
            usage_count=100,
            success_count=95,
            failure_count=5,
            last_used_at=now,
            created_at=now,
            updated_at=now,
            can_edit=True,
        )

        response = GetCapabilityResponse(capability=detail)

        assert response.capability.id == cap_id
        assert response.capability.agent_type == "test_agent"
        assert response.capability.execution_hints == {"speed": "fast", "cost": "low"}
        assert response.capability.spec_yaml == "agent_type: test_agent\nname: Test Agent"
        assert response.capability.usage_count == 100


@pytest.mark.asyncio
class TestGetCapability:
    """Tests for get_capability endpoint."""

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_system_success(self, mock_db):
        """Should return system capability for any authenticated user."""
        from src.api.routers.capabilities import get_capability

        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock system capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "summarize"
        mock_cap.name = "Summarize Agent"
        mock_cap.description = "Summarizes content"
        mock_cap.domain = "content"
        mock_cap.task_type = "general"
        mock_cap.system_prompt = "You are a summarization expert."
        mock_cap.inputs_schema = {"text": {"type": "string"}}
        mock_cap.outputs_schema = {"summary": {"type": "string"}}
        mock_cap.examples = [{"input": "long text", "output": "short summary"}]
        mock_cap.execution_hints = {"deterministic": False}
        mock_cap.is_system = True
        mock_cap.is_active = True
        mock_cap.organization_id = None
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.created_by = None
        mock_cap.tags = ["content", "summarization"]
        mock_cap.spec_yaml = None
        mock_cap.usage_count = 500
        mock_cap.success_count = 490
        mock_cap.failure_count = 10
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user without organization (should still see system caps)
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await get_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.capability.id == cap_id
        assert result.capability.agent_type == "summarize"
        assert result.capability.is_system is True
        assert result.capability.system_prompt == "You are a summarization expert."
        assert result.capability.execution_hints == {"deterministic": False}
        assert result.capability.usage_count == 500
        assert result.capability.can_edit is False  # System caps can't be edited

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_user_owned_success(self, mock_db):
        """Should return user-owned capability with can_edit=True."""
        from src.api.routers.capabilities import get_capability

        cap_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock user-owned capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "custom_agent"
        mock_cap.name = "Custom Agent"
        mock_cap.description = "My custom agent"
        mock_cap.domain = "custom"
        mock_cap.task_type = "reasoning"
        mock_cap.system_prompt = "You are my custom agent."
        mock_cap.inputs_schema = {"query": {"type": "string"}}
        mock_cap.outputs_schema = {"answer": {"type": "string"}}
        mock_cap.examples = []
        mock_cap.execution_hints = {"speed": "fast"}
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id
        mock_cap.version = 2
        mock_cap.is_latest = True
        mock_cap.created_by = user_id
        mock_cap.tags = ["custom", "personal"]
        mock_cap.spec_yaml = "agent_type: custom_agent\nname: Custom Agent"
        mock_cap.usage_count = 25
        mock_cap.success_count = 24
        mock_cap.failure_count = 1
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user from same org
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await get_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.capability.id == cap_id
        assert result.capability.agent_type == "custom_agent"
        assert result.capability.is_system is False
        assert result.capability.spec_yaml == "agent_type: custom_agent\nname: Custom Agent"
        assert result.capability.version == 2
        assert result.capability.can_edit is True  # User can edit their own

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_not_found(self, mock_db):
        """Should return 404 for non-existent capability."""
        from src.api.routers.capabilities import get_capability
        from fastapi import HTTPException

        cap_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(uuid4())}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await get_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_wrong_org_rejected(self, mock_db):
        """Should reject access to capability from different organization."""
        from src.api.routers.capabilities import get_capability
        from fastapi import HTTPException

        cap_id = uuid4()
        cap_org_id = uuid4()
        user_org_id = uuid4()  # Different org

        # Mock capability from different org
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "other_agent"
        mock_cap.is_system = False
        mock_cap.organization_id = cap_org_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(user_org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await get_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403
        assert "your organization" in exc_info.value.detail.lower()

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_no_org_user_can_see_system(self, mock_db):
        """User without org can still see system capabilities."""
        from src.api.routers.capabilities import get_capability

        cap_id = uuid4()

        # Mock system capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "system_agent"
        mock_cap.name = "System Agent"
        mock_cap.description = "A system agent"
        mock_cap.domain = "system"
        mock_cap.task_type = "general"
        mock_cap.system_prompt = "System prompt"
        mock_cap.inputs_schema = {}
        mock_cap.outputs_schema = {}
        mock_cap.examples = []
        mock_cap.execution_hints = {}
        mock_cap.is_system = True
        mock_cap.is_active = True
        mock_cap.organization_id = None
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.created_by = None
        mock_cap.tags = []
        mock_cap.spec_yaml = None
        mock_cap.usage_count = 0
        mock_cap.success_count = 0
        mock_cap.failure_count = 0
        mock_cap.last_used_at = None
        mock_cap.created_at = datetime.now(timezone.utc)
        mock_cap.updated_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        # User without organization
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {}  # No org

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await get_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.capability.id == cap_id
        assert result.capability.is_system is True
        assert result.capability.can_edit is False

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_no_org_user_cannot_see_user_caps(self, mock_db):
        """User without org cannot see user-defined capabilities."""
        from src.api.routers.capabilities import get_capability
        from fastapi import HTTPException

        cap_id = uuid4()
        cap_org_id = uuid4()

        # Mock user-owned capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "user_agent"
        mock_cap.is_system = False
        mock_cap.organization_id = cap_org_id

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        # User without organization
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {}  # No org

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        with pytest.raises(HTTPException) as exc_info:
            await get_capability(
                capability_id=cap_id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 403

    @patch("src.api.routers.capabilities.database")
    async def test_get_capability_returns_all_fields(self, mock_db):
        """Should return all capability fields including spec_yaml and execution_hints."""
        from src.api.routers.capabilities import get_capability

        cap_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock capability with all fields populated
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "full_agent"
        mock_cap.name = "Full Agent"
        mock_cap.description = "An agent with all fields"
        mock_cap.domain = "testing"
        mock_cap.task_type = "analysis"
        mock_cap.system_prompt = "You analyze data thoroughly."
        mock_cap.inputs_schema = {
            "data": {"type": "object", "description": "Data to analyze"},
            "format": {"type": "string", "enum": ["json", "csv"]}
        }
        mock_cap.outputs_schema = {
            "analysis": {"type": "object"},
            "confidence": {"type": "number"}
        }
        mock_cap.examples = [
            {"input": {"data": {}, "format": "json"}, "output": {"analysis": {}, "confidence": 0.95}}
        ]
        mock_cap.execution_hints = {
            "deterministic": True,
            "speed": "medium",
            "cost": "medium",
            "requires_context": True
        }
        mock_cap.is_system = False
        mock_cap.is_active = True
        mock_cap.organization_id = org_id
        mock_cap.version = 3
        mock_cap.is_latest = True
        mock_cap.created_by = user_id
        mock_cap.tags = ["analysis", "data", "testing"]
        mock_cap.spec_yaml = """agent_type: full_agent
name: Full Agent
description: An agent with all fields
domain: testing
task_type: analysis
system_prompt: You analyze data thoroughly.
inputs:
  data:
    type: object
    description: Data to analyze
  format:
    type: string
    enum: [json, csv]
outputs:
  analysis:
    type: object
  confidence:
    type: number
execution_hints:
  deterministic: true
  speed: medium
"""
        mock_cap.usage_count = 1000
        mock_cap.success_count = 950
        mock_cap.failure_count = 50
        mock_cap.last_used_at = now
        mock_cap.created_at = now
        mock_cap.updated_at = now

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cap
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await get_capability(
            capability_id=cap_id,
            db=mock_db,
            current_user=mock_user,
        )

        # Verify all fields are returned
        cap = result.capability
        assert cap.id == cap_id
        assert cap.agent_type == "full_agent"
        assert cap.name == "Full Agent"
        assert cap.description == "An agent with all fields"
        assert cap.domain == "testing"
        assert cap.task_type == "analysis"
        assert cap.system_prompt == "You analyze data thoroughly."
        assert "data" in cap.inputs_schema
        assert "analysis" in cap.outputs_schema
        assert len(cap.examples) == 1
        assert cap.execution_hints["deterministic"] is True
        assert cap.execution_hints["speed"] == "medium"
        assert cap.is_system is False
        assert cap.is_active is True
        assert cap.organization_id == org_id
        assert cap.version == 3
        assert cap.is_latest is True
        assert cap.created_by == user_id
        assert "analysis" in cap.tags
        assert "full_agent" in cap.spec_yaml
        assert cap.usage_count == 1000
        assert cap.success_count == 950
        assert cap.failure_count == 50
        assert cap.last_used_at == now
        assert cap.can_edit is True


# Tests for CAP-013: Search Capability Endpoint

class TestSearchCapabilityModels:
    """Tests for search capability request/response models."""

    def test_search_capability_item_model(self):
        """Should create SearchCapabilityItem with all fields."""
        from src.api.routers.capabilities import SearchCapabilityItem
        cap_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        item = SearchCapabilityItem(
            id=cap_id,
            agent_type="summarize",
            name="Summarize Agent",
            description="Summarizes content",
            domain="content",
            task_type="general",
            is_system=True,
            is_active=True,
            organization_id=org_id,
            version=1,
            is_latest=True,
            tags=["content", "summary"],
            keywords=["summarize", "content", "text"],
            usage_count=100,
            success_count=95,
            failure_count=5,
            last_used_at=now,
            similarity=0.85,
            match_type="semantic",
            can_edit=False,
        )

        assert item.id == cap_id
        assert item.similarity == 0.85
        assert item.match_type == "semantic"
        assert item.keywords == ["summarize", "content", "text"]

    def test_search_capability_item_defaults(self):
        """Should have proper defaults."""
        from src.api.routers.capabilities import SearchCapabilityItem
        cap_id = uuid4()

        item = SearchCapabilityItem(
            id=cap_id,
            agent_type="test",
            name="Test Agent",
            task_type="general",
            is_system=True,
            is_active=True,
            version=1,
            is_latest=True,
            usage_count=0,
            success_count=0,
            failure_count=0,
        )

        assert item.similarity == 0.0
        assert item.match_type == "keyword"
        assert item.tags == []
        assert item.keywords == []
        assert item.can_edit is False

    def test_search_capabilities_response_model(self):
        """Should create SearchCapabilitiesResponse correctly."""
        from src.api.routers.capabilities import SearchCapabilitiesResponse, SearchCapabilityItem
        cap_id = uuid4()

        response = SearchCapabilitiesResponse(
            results=[
                SearchCapabilityItem(
                    id=cap_id,
                    agent_type="summarize",
                    name="Summarize Agent",
                    task_type="general",
                    is_system=True,
                    is_active=True,
                    version=1,
                    is_latest=True,
                    usage_count=100,
                    success_count=95,
                    failure_count=5,
                    similarity=0.92,
                    match_type="semantic",
                )
            ],
            count=1,
            query="summarize text",
            search_type="semantic",
        )

        assert response.count == 1
        assert response.query == "summarize text"
        assert response.search_type == "semantic"
        assert len(response.results) == 1
        assert response.results[0].similarity == 0.92


class TestKeywordSearchLogic:
    """Tests for keyword search helper function logic."""

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.database")
    async def test_keyword_search_returns_results(self, mock_db):
        """Should return matching capabilities based on keywords."""
        from src.api.routers.capabilities import _keyword_search

        cap_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock matching capability
        mock_cap = MagicMock()
        mock_cap.id = cap_id
        mock_cap.agent_type = "summarize"
        mock_cap.name = "Summarize Agent"
        mock_cap.description = "Summarizes text content into brief summaries"
        mock_cap.domain = "content"
        mock_cap.task_type = "general"
        mock_cap.is_system = True
        mock_cap.is_active = True
        mock_cap.organization_id = None
        mock_cap.version = 1
        mock_cap.is_latest = True
        mock_cap.tags = ["content", "summary"]
        mock_cap.keywords = ["summarize", "brief", "text"]
        mock_cap.usage_count = 100
        mock_cap.success_count = 95
        mock_cap.failure_count = 5
        mock_cap.last_used_at = now

        # Mock database session
        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_cap]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await _keyword_search(
            session=mock_session,
            query="summarize text",
            org_id=str(org_id),
            include_system=True,
            active_only=True,
            domain=None,
            tags=None,
            limit=20,
        )

        assert len(results) == 1
        assert results[0]["agent_type"] == "summarize"
        assert results[0]["match_type"] == "keyword"
        assert results[0]["similarity"] > 0  # Should have relevance score

    @pytest.mark.asyncio
    async def test_keyword_search_empty_query(self):
        """Should return empty for empty query."""
        from src.api.routers.capabilities import _keyword_search

        mock_session = AsyncMock()

        results = await _keyword_search(
            session=mock_session,
            query="   ",  # Just whitespace
            org_id=str(uuid4()),
            include_system=True,
            active_only=True,
            domain=None,
            tags=None,
            limit=20,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_keyword_search_no_system_no_org(self):
        """Should return empty when no system caps and no org_id."""
        from src.api.routers.capabilities import _keyword_search

        mock_session = AsyncMock()

        results = await _keyword_search(
            session=mock_session,
            query="summarize",
            org_id=None,
            include_system=False,  # No system caps
            active_only=True,
            domain=None,
            tags=None,
            limit=20,
        )

        assert results == []


class TestSemanticSearchLogic:
    """Tests for semantic search helper function logic."""

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.database")
    async def test_semantic_search_returns_results(self, mock_db):
        """Should return matching capabilities using vector similarity."""
        from src.api.routers.capabilities import _semantic_search

        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        # Mock a database row result
        mock_row = MagicMock()
        mock_row.id = cap_id
        mock_row.agent_type = "summarize"
        mock_row.name = "Summarize Agent"
        mock_row.description = "Summarizes content"
        mock_row.domain = "content"
        mock_row.task_type = "general"
        mock_row.is_system = True
        mock_row.is_active = True
        mock_row.organization_id = None
        mock_row.version = 1
        mock_row.is_latest = True
        mock_row.tags = ["content"]
        mock_row.keywords = ["summarize"]
        mock_row.usage_count = 100
        mock_row.success_count = 95
        mock_row.failure_count = 5
        mock_row.last_used_at = now
        mock_row.similarity = 0.92

        # Mock database session with column check
        mock_session = AsyncMock()

        # First execute call checks for column existence
        mock_column_check = MagicMock()
        mock_column_check.fetchone.return_value = MagicMock()  # Column exists

        # Second execute call returns actual results
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        mock_session.execute = AsyncMock(side_effect=[mock_column_check, mock_result])

        # Create a fake embedding (1536 dimensions)
        fake_embedding = [0.1] * 1536

        results = await _semantic_search(
            session=mock_session,
            query_embedding=fake_embedding,
            org_id=None,
            include_system=True,
            active_only=True,
            domain=None,
            tags=None,
            limit=20,
            min_similarity=0.5,
        )

        assert len(results) == 1
        assert results[0]["agent_type"] == "summarize"
        assert results[0]["similarity"] == 0.92
        assert results[0]["match_type"] == "semantic"

    @pytest.mark.asyncio
    async def test_semantic_search_no_system_no_org(self):
        """Should return empty when no system caps and no org_id."""
        from src.api.routers.capabilities import _semantic_search

        mock_session = AsyncMock()
        fake_embedding = [0.1] * 1536

        results = await _semantic_search(
            session=mock_session,
            query_embedding=fake_embedding,
            org_id=None,
            include_system=False,
            active_only=True,
            domain=None,
            tags=None,
            limit=20,
            min_similarity=0.5,
        )

        assert results == []


class TestGenerateQueryEmbedding:
    """Tests for query embedding generation."""

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.get_embedding_client")
    async def test_generate_embedding_disabled(self, mock_get_client):
        """Should return None when embeddings are disabled."""
        from src.api.routers.capabilities import _generate_query_embedding

        mock_client = MagicMock()
        mock_client.is_configured = False
        mock_get_client.return_value = mock_client

        result = await _generate_query_embedding("test query")

        assert result is None

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.get_embedding_client")
    async def test_generate_embedding_success(self, mock_get_client):
        """Should return embedding when successful."""
        from src.api.routers.capabilities import _generate_query_embedding

        fake_embedding = [0.1] * 1536

        mock_result = MagicMock()
        mock_result.embedding = fake_embedding

        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.create_embedding = AsyncMock(return_value=mock_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_get_client.return_value = mock_client

        result = await _generate_query_embedding("summarize text")

        assert result == fake_embedding

    @pytest.mark.asyncio
    @patch("src.api.routers.capabilities.get_embedding_client")
    async def test_generate_embedding_exception(self, mock_get_client):
        """Should return None on exception."""
        from src.api.routers.capabilities import _generate_query_embedding

        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("API error"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_get_client.return_value = mock_client

        result = await _generate_query_embedding("test query")

        assert result is None


@pytest.mark.asyncio
class TestSearchCapabilities:
    """Tests for search_capabilities endpoint."""

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._generate_query_embedding")
    @patch("src.api.routers.capabilities._keyword_search")
    async def test_search_fallback_to_keyword(self, mock_keyword_search, mock_gen_embedding, mock_db):
        """Should fall back to keyword search when embeddings unavailable."""
        from src.api.routers.capabilities import search_capabilities

        org_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        # No embeddings available
        mock_gen_embedding.return_value = None

        # Keyword search returns results
        mock_keyword_search.return_value = [
            {
                "id": cap_id,
                "agent_type": "summarize",
                "name": "Summarize Agent",
                "description": "Summarizes content",
                "domain": "content",
                "task_type": "general",
                "is_system": True,
                "is_active": True,
                "organization_id": None,
                "version": 1,
                "is_latest": True,
                "tags": ["content"],
                "keywords": ["summarize"],
                "usage_count": 100,
                "success_count": 95,
                "failure_count": 5,
                "last_used_at": now,
                "similarity": 0.75,
                "match_type": "keyword",
            }
        ]

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="summarize",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.search_type == "keyword"
        assert result.count == 1
        assert result.results[0].agent_type == "summarize"
        assert result.results[0].match_type == "keyword"

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._generate_query_embedding")
    @patch("src.api.routers.capabilities._semantic_search")
    async def test_search_uses_semantic_when_available(self, mock_semantic_search, mock_gen_embedding, mock_db):
        """Should use semantic search when embeddings are available."""
        from src.api.routers.capabilities import search_capabilities

        org_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        # Embeddings available
        fake_embedding = [0.1] * 1536
        mock_gen_embedding.return_value = fake_embedding

        # Semantic search returns results
        mock_semantic_search.return_value = [
            {
                "id": cap_id,
                "agent_type": "summarize",
                "name": "Summarize Agent",
                "description": "Summarizes content",
                "domain": "content",
                "task_type": "general",
                "is_system": True,
                "is_active": True,
                "organization_id": None,
                "version": 1,
                "is_latest": True,
                "tags": ["content"],
                "keywords": ["summarize"],
                "usage_count": 100,
                "success_count": 95,
                "failure_count": 5,
                "last_used_at": now,
                "similarity": 0.92,
                "match_type": "semantic",
            }
        ]

        # Mock database session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        # Mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="summarize text",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.search_type == "semantic"
        assert result.count == 1
        assert result.results[0].agent_type == "summarize"
        assert result.results[0].similarity == 0.92
        assert result.results[0].match_type == "semantic"

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._keyword_search")
    async def test_search_keyword_only_mode(self, mock_keyword_search, mock_db):
        """Should use keyword search when prefer_semantic=False."""
        from src.api.routers.capabilities import search_capabilities

        org_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_keyword_search.return_value = [
            {
                "id": cap_id,
                "agent_type": "web_search",
                "name": "Web Search Agent",
                "description": "Searches the web",
                "domain": "research",
                "task_type": "general",
                "is_system": True,
                "is_active": True,
                "organization_id": None,
                "version": 1,
                "is_latest": True,
                "tags": ["web"],
                "keywords": ["search", "web"],
                "usage_count": 50,
                "success_count": 45,
                "failure_count": 5,
                "last_used_at": now,
                "similarity": 0.6,
                "match_type": "keyword",
            }
        ]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="web search",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=False,  # Force keyword mode
            db=mock_db,
            current_user=mock_user,
        )

        assert result.search_type == "keyword"
        assert result.count == 1
        assert result.results[0].agent_type == "web_search"

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._generate_query_embedding")
    @patch("src.api.routers.capabilities._semantic_search")
    @patch("src.api.routers.capabilities._keyword_search")
    async def test_search_semantic_fallback_empty(self, mock_keyword_search, mock_semantic_search, mock_gen_embedding, mock_db):
        """Should fall back to keyword search when semantic returns no results."""
        from src.api.routers.capabilities import search_capabilities

        org_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        fake_embedding = [0.1] * 1536
        mock_gen_embedding.return_value = fake_embedding
        mock_semantic_search.return_value = []  # No semantic results

        mock_keyword_search.return_value = [
            {
                "id": cap_id,
                "agent_type": "analyzer",
                "name": "Data Analyzer",
                "description": "Analyzes data",
                "domain": "analytics",
                "task_type": "analysis",
                "is_system": True,
                "is_active": True,
                "organization_id": None,
                "version": 1,
                "is_latest": True,
                "tags": ["analytics"],
                "keywords": ["analyze", "data"],
                "usage_count": 30,
                "success_count": 28,
                "failure_count": 2,
                "last_used_at": now,
                "similarity": 0.5,
                "match_type": "keyword",
            }
        ]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="analyze data",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=True,
            db=mock_db,
            current_user=mock_user,
        )

        # Should have fallen back to keyword
        assert result.search_type == "keyword"
        assert result.count == 1

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._keyword_search")
    async def test_search_can_edit_flag(self, mock_keyword_search, mock_db):
        """Should set can_edit=True for user's own capabilities."""
        from src.api.routers.capabilities import search_capabilities

        org_id = uuid4()
        cap_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_keyword_search.return_value = [
            {
                "id": cap_id,
                "agent_type": "custom_agent",
                "name": "Custom Agent",
                "description": "My custom agent",
                "domain": "custom",
                "task_type": "general",
                "is_system": False,  # User-owned
                "is_active": True,
                "organization_id": org_id,  # Same org as user
                "version": 1,
                "is_latest": True,
                "tags": ["custom"],
                "keywords": ["custom"],
                "usage_count": 10,
                "success_count": 9,
                "failure_count": 1,
                "last_used_at": now,
                "similarity": 0.8,
                "match_type": "keyword",
            }
        ]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(org_id)}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="custom",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=False,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.count == 1
        assert result.results[0].can_edit is True  # User can edit their own

    @patch("src.api.routers.capabilities.database")
    @patch("src.api.routers.capabilities._keyword_search")
    async def test_search_empty_results(self, mock_keyword_search, mock_db):
        """Should return empty results when no matches found."""
        from src.api.routers.capabilities import search_capabilities

        mock_keyword_search.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db.get_session = MagicMock(return_value=mock_session)

        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.metadata = {"organization_id": str(uuid4())}

        from src.api.routers import capabilities as cap_module
        cap_module.database = mock_db

        result = await search_capabilities(
            query="nonexistent capability",
            domain=None,
            tags=None,
            include_system=True,
            active_only=True,
            limit=20,
            min_similarity=0.5,
            prefer_semantic=False,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.count == 0
        assert result.results == []
        assert result.query == "nonexistent capability"
