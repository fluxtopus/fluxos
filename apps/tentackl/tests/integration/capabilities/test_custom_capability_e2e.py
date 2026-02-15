"""E2E test for custom capability creation and usage (CAP-025).

Tests the full end-to-end flow:
1. Creates a custom capability via API
2. Creates a task that uses the custom capability
3. Executes the task
4. Verifies the custom capability was used and analytics updated
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import select

from src.database.capability_models import AgentCapability
from src.api.routers.capabilities import (
    CreateCapabilityRequest,
    create_capability,
)
from src.infrastructure.execution_runtime.plugin_executor import (
    execute_step,
    ExecutionResult,
    track_capability_usage,
)
from src.domain.tasks.models import TaskStep


class TestCustomCapabilityE2E:
    """End-to-end tests for custom capability lifecycle."""

    @pytest_asyncio.fixture
    async def create_custom_capability(self, test_db):
        """Create a custom capability via API and return its details."""
        org_id = uuid4()
        user_id = uuid4()
        unique_suffix = uuid4().hex[:8]
        agent_type = f"e2e_custom_agent_{unique_suffix}"

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        yaml_spec = f"""
agent_type: {agent_type}
name: E2E Custom Agent
description: A custom agent created for E2E testing of capability workflow
domain: testing
task_type: general
system_prompt: |
  You are a test agent for E2E integration testing.
  When given input, respond with a confirmation message.
inputs:
  test_input:
    type: string
    required: true
    description: Input for testing
outputs:
  result:
    type: string
    description: Test result output
execution_hints:
  deterministic: false
  speed: fast
  cost: low
"""

        request = CreateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["e2e-test", "custom", "integration"]
        )

        result = await create_capability(
            request=request,
            db=test_db,
            current_user=mock_user,
        )

        return {
            "capability_id": result.capability.id,
            "agent_type": agent_type,
            "org_id": org_id,
            "user_id": user_id,
            "unique_suffix": unique_suffix,
        }

    @pytest.mark.asyncio
    async def test_create_custom_capability_via_api(
        self, test_db, create_custom_capability
    ):
        """Step 1: Verify custom capability is created successfully via API."""
        cap_id = create_custom_capability["capability_id"]
        agent_type = create_custom_capability["agent_type"]
        org_id = create_custom_capability["org_id"]

        # Verify capability exists in database
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one_or_none()

            assert cap is not None
            assert cap.agent_type == agent_type
            assert cap.organization_id == org_id
            assert cap.is_system is False
            assert cap.is_active is True
            assert cap.is_latest is True
            assert cap.version == 1
            # Initial analytics should be zero
            assert cap.usage_count == 0
            assert cap.success_count == 0
            assert cap.failure_count == 0
            assert cap.last_used_at is None

    @pytest.mark.asyncio
    async def test_track_usage_for_custom_capability(
        self, test_db, create_custom_capability
    ):
        """Step 2: Verify usage tracking works for custom capabilities."""
        cap_id = create_custom_capability["capability_id"]
        agent_type = create_custom_capability["agent_type"]
        org_id = str(create_custom_capability["org_id"])

        # Track a successful execution
        await track_capability_usage(
            agent_type=agent_type,
            success=True,
            organization_id=org_id,
        )

        # Verify analytics were updated
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 1
            assert cap.success_count == 1
            assert cap.failure_count == 0
            assert cap.last_used_at is not None

    @pytest.mark.asyncio
    async def test_track_failure_for_custom_capability(
        self, test_db, create_custom_capability
    ):
        """Step 3: Verify failure tracking works for custom capabilities."""
        cap_id = create_custom_capability["capability_id"]
        agent_type = create_custom_capability["agent_type"]
        org_id = str(create_custom_capability["org_id"])

        # Track a failed execution
        await track_capability_usage(
            agent_type=agent_type,
            success=False,
            organization_id=org_id,
        )

        # Verify analytics were updated
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 1
            assert cap.success_count == 0
            assert cap.failure_count == 1
            assert cap.last_used_at is not None

    @pytest.mark.asyncio
    async def test_execute_step_with_custom_capability(
        self, test_db, create_custom_capability
    ):
        """Step 4: Verify execute_step integrates with custom capabilities."""
        cap_id = create_custom_capability["capability_id"]
        agent_type = create_custom_capability["agent_type"]
        org_id = str(create_custom_capability["org_id"])

        # Create a mock step
        mock_step = MagicMock(spec=TaskStep)
        mock_step.agent_type = agent_type
        mock_step.id = f"step_{uuid4().hex[:8]}"
        mock_step.inputs = {"test_input": "Hello E2E test!"}

        # Mock the agent execution to avoid actual LLM calls
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=ExecutionResult(
            status="success",
            output={"result": "Test passed!"},
        ))
        # Remove optional methods so hasattr returns False
        del mock_agent.execute_validated
        del mock_agent.initialize
        del mock_agent.cleanup

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(return_value=mock_agent)

        async def mock_get_registry():
            return mock_registry

        with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
            result = await execute_step(
                step=mock_step,
                organization_id=org_id,
            )

        # Verify step execution succeeded
        assert result.success
        assert result.output == {"result": "Test passed!"}

        # Verify analytics were updated
        async with test_db.get_session() as session:
            db_result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = db_result.scalar_one()

            assert cap.usage_count == 1
            assert cap.success_count == 1
            assert cap.failure_count == 0
            assert cap.last_used_at is not None

    @pytest.mark.asyncio
    async def test_full_e2e_custom_capability_workflow(
        self, test_db
    ):
        """
        Full E2E test: Create capability -> Execute step -> Verify analytics.

        This test verifies the complete workflow for CAP-025:
        1. Creates a custom capability via API
        2. Creates a task step that uses the custom capability
        3. Executes the task step (mocked agent execution)
        4. Verifies the custom capability analytics are updated
        """
        # Setup
        org_id = uuid4()
        user_id = uuid4()
        unique_suffix = uuid4().hex[:8]
        agent_type = f"e2e_full_workflow_{unique_suffix}"

        # Step 1: Create custom capability via API
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        yaml_spec = f"""
agent_type: {agent_type}
name: Full E2E Workflow Agent
description: Tests the complete custom capability workflow
domain: testing
task_type: general
system_prompt: You are a test agent for full E2E workflow testing.
inputs:
  message:
    type: string
    required: true
outputs:
  response:
    type: string
"""

        create_request = CreateCapabilityRequest(
            spec_yaml=yaml_spec,
            tags=["e2e-full", "workflow-test"]
        )

        create_result = await create_capability(
            request=create_request,
            db=test_db,
            current_user=mock_user,
        )

        cap_id = create_result.capability.id
        assert create_result.message == "Capability created successfully"

        # Verify initial state
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap_before = result.scalar_one()
            assert cap_before.usage_count == 0
            assert cap_before.success_count == 0
            assert cap_before.failure_count == 0
            assert cap_before.last_used_at is None

        # Step 2: Create a task step using the custom capability
        mock_step = MagicMock(spec=TaskStep)
        mock_step.agent_type = agent_type
        mock_step.id = f"e2e_step_{unique_suffix}"
        mock_step.inputs = {"message": "Test message for E2E workflow"}

        # Step 3: Execute the step (mock the agent to avoid LLM calls)
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=ExecutionResult(
            status="success",
            output={"response": "E2E workflow completed successfully"},
        ))
        del mock_agent.execute_validated
        del mock_agent.initialize
        del mock_agent.cleanup

        mock_registry = AsyncMock()
        mock_registry.create_agent = AsyncMock(return_value=mock_agent)

        async def mock_get_registry():
            return mock_registry

        before_execution = datetime.now(timezone.utc)

        with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
            exec_result = await execute_step(
                step=mock_step,
                organization_id=str(org_id),
            )

        after_execution = datetime.now(timezone.utc)

        # Verify execution succeeded
        assert exec_result.success
        assert exec_result.status == "success"
        assert exec_result.output["response"] == "E2E workflow completed successfully"

        # Step 4: Verify analytics were updated correctly
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap_after = result.scalar_one()

            # Analytics should reflect successful execution
            assert cap_after.usage_count == 1, f"Expected usage_count=1, got {cap_after.usage_count}"
            assert cap_after.success_count == 1, f"Expected success_count=1, got {cap_after.success_count}"
            assert cap_after.failure_count == 0, f"Expected failure_count=0, got {cap_after.failure_count}"
            assert cap_after.last_used_at is not None
            assert before_execution <= cap_after.last_used_at <= after_execution

    @pytest.mark.asyncio
    async def test_multiple_executions_accumulate_analytics(
        self, test_db
    ):
        """Verify multiple executions accumulate analytics correctly."""
        # Create capability
        org_id = uuid4()
        user_id = uuid4()
        unique_suffix = uuid4().hex[:8]
        agent_type = f"e2e_multi_exec_{unique_suffix}"

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.metadata = {"organization_id": str(org_id)}

        yaml_spec = f"""
agent_type: {agent_type}
name: Multi-Execution Test Agent
description: Tests multiple executions accumulating analytics
domain: testing
task_type: general
system_prompt: You are a test agent.
inputs:
  data:
    type: string
    required: true
outputs:
  result:
    type: string
"""

        create_result = await create_capability(
            request=CreateCapabilityRequest(spec_yaml=yaml_spec, tags=["multi-exec"]),
            db=test_db,
            current_user=mock_user,
        )
        cap_id = create_result.capability.id

        # Execute multiple times with mixed success/failure
        execution_results = [
            (True, "success1"),
            (True, "success2"),
            (False, "failure1"),
            (True, "success3"),
            (False, "failure2"),
        ]

        for success, response in execution_results:
            mock_step = MagicMock(spec=TaskStep)
            mock_step.agent_type = agent_type
            mock_step.id = f"step_{uuid4().hex[:8]}"
            mock_step.inputs = {"data": f"test_{response}"}

            mock_agent = MagicMock()
            if success:
                mock_agent.execute = AsyncMock(return_value=ExecutionResult(
                    status="success",
                    output={"result": response},
                ))
            else:
                mock_agent.execute = AsyncMock(return_value=ExecutionResult(
                    status="error",
                    output=None,
                    error="Simulated failure",
                ))
            del mock_agent.execute_validated
            del mock_agent.initialize
            del mock_agent.cleanup

            mock_registry = AsyncMock()
            mock_registry.create_agent = AsyncMock(return_value=mock_agent)

            async def mock_get_registry():
                return mock_registry

            with patch("src.capabilities.unified_registry.get_registry", mock_get_registry):
                await execute_step(
                    step=mock_step,
                    organization_id=str(org_id),
                )

        # Verify accumulated analytics
        async with test_db.get_session() as session:
            result = await session.execute(
                select(AgentCapability).where(AgentCapability.id == cap_id)
            )
            cap = result.scalar_one()

            assert cap.usage_count == 5  # 3 successes + 2 failures
            assert cap.success_count == 3
            assert cap.failure_count == 2
            assert cap.last_used_at is not None
