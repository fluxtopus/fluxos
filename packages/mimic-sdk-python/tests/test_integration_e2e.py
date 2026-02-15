"""
Integration/E2E tests for Mimic SDK against real Mimic API (INT-017).

These tests require:
1. Mimic service running at http://localhost:8006
2. InkPass service running at http://localhost:8004
3. Admin user credentials: admin@fluxtopus.com / AiosAdmin123!

Run with: pytest tests/test_integration_e2e.py -v --no-cov -s
"""

import asyncio
import os
import pytest
import httpx

# Import the SDK
from mimic import (
    MimicIntegrationClient,
    MimicConfig,
    IntegrationCreate,
    IntegrationUpdate,
    CredentialCreate,
    InboundConfigCreate,
    OutboundConfigCreate,
    IntegrationProvider,
    IntegrationDirection,
    IntegrationStatus,
    CredentialType,
    InboundAuthMethod,
    DestinationService,
    OutboundActionType,
    ResourceNotFoundError,
)


# =============================================================================
# Configuration
# =============================================================================

MIMIC_URL = os.environ.get("MIMIC_URL", "http://localhost:8006")
INKPASS_URL = os.environ.get("INKPASS_URL", "http://localhost:8004")
ADMIN_EMAIL = "admin@fluxtopus.com"
ADMIN_PASSWORD = "AiosAdmin123!"


async def get_auth_token() -> str:
    """Get authentication token from InkPass."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{INKPASS_URL}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code != 200:
            raise Exception(f"Login failed: {response.text}")
        return response.json()["access_token"]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def auth_token(event_loop):
    """Get auth token for all tests (sync wrapper for async function)."""
    return event_loop.run_until_complete(get_auth_token())


@pytest.fixture
def sdk_config():
    """Create SDK configuration."""
    return MimicConfig(
        base_url=MIMIC_URL,
        timeout=10.0,
    )


@pytest.fixture
def sdk_client(sdk_config):
    """Create SDK client."""
    return MimicIntegrationClient(sdk_config)


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
class TestSDKIntegration:
    """Integration tests for Mimic SDK against real API."""

    async def test_list_integrations_empty(self, sdk_client, auth_token):
        """Test listing integrations (may be empty or have existing data)."""
        result = await sdk_client.list_integrations(token=auth_token)

        assert result is not None
        assert hasattr(result, "items")
        assert hasattr(result, "total")
        assert isinstance(result.items, list)
        print(f"Found {result.total} integrations")

    async def test_full_integration_lifecycle(self, sdk_client, auth_token):
        """Test complete integration lifecycle: create, read, update, delete."""
        # 1. Create integration
        created = await sdk_client.create_integration(
            IntegrationCreate(
                name="SDK Test Integration",
                provider=IntegrationProvider.custom_webhook,
                direction=IntegrationDirection.bidirectional,
            ),
            token=auth_token,
        )

        assert created.id is not None
        assert created.name == "SDK Test Integration"
        assert created.provider == "custom_webhook"
        assert created.direction == "bidirectional"
        assert created.status == "active"
        integration_id = created.id
        print(f"Created integration: {integration_id}")

        try:
            # 2. Get integration details
            detail = await sdk_client.get_integration(integration_id, token=auth_token)
            assert detail.id == integration_id
            assert detail.name == "SDK Test Integration"
            assert detail.credentials == []
            assert detail.inbound_config is None
            assert detail.outbound_config is None
            print(f"Got integration detail: {detail.name}")

            # 3. Update integration
            updated = await sdk_client.update_integration(
                integration_id,
                IntegrationUpdate(
                    name="SDK Test Integration Updated",
                    status=IntegrationStatus.paused,
                ),
                token=auth_token,
            )
            assert updated.name == "SDK Test Integration Updated"
            assert updated.status == "paused"
            print(f"Updated integration: {updated.name}")

            # Restore to active for cleanup
            await sdk_client.update_integration(
                integration_id,
                IntegrationUpdate(status=IntegrationStatus.active),
                token=auth_token,
            )

        finally:
            # 4. Delete integration
            deleted = await sdk_client.delete_integration(integration_id, token=auth_token)
            assert deleted is True
            print(f"Deleted integration: {integration_id}")

            # Verify deletion
            with pytest.raises(ResourceNotFoundError):
                await sdk_client.get_integration(integration_id, token=auth_token)
            print("Verified integration was deleted")

    async def test_credential_management(self, sdk_client, auth_token):
        """Test credential CRUD operations."""
        # Create integration first
        created = await sdk_client.create_integration(
            IntegrationCreate(
                name="SDK Credential Test",
                provider=IntegrationProvider.custom_webhook,
                direction=IntegrationDirection.bidirectional,
            ),
            token=auth_token,
        )
        integration_id = created.id

        try:
            # 1. Add credential
            credential = await sdk_client.add_credential(
                integration_id,
                CredentialCreate(
                    credential_type=CredentialType.webhook_url,
                    value="https://httpbin.org/post",
                    metadata={"description": "Test webhook"},
                ),
                token=auth_token,
            )
            assert credential.id is not None
            assert credential.credential_type == "webhook_url"
            assert credential.has_value is True
            credential_id = credential.id
            print(f"Added credential: {credential_id}")

            # 2. List credentials
            credentials = await sdk_client.list_credentials(integration_id, token=auth_token)
            assert len(credentials) == 1
            assert credentials[0].id == credential_id
            print(f"Listed {len(credentials)} credentials")

            # 3. Test credential
            test_result = await sdk_client.test_credential(
                integration_id, credential_id, token=auth_token
            )
            # Note: This may fail if httpbin.org is not reachable
            print(f"Credential test result: {test_result.success} - {test_result.message}")

            # 4. Delete credential
            deleted = await sdk_client.delete_credential(
                integration_id, credential_id, token=auth_token
            )
            assert deleted is True
            print(f"Deleted credential: {credential_id}")

        finally:
            # Cleanup
            await sdk_client.delete_integration(integration_id, token=auth_token)

    async def test_inbound_config_management(self, sdk_client, auth_token):
        """Test inbound webhook config management."""
        # Create integration first
        created = await sdk_client.create_integration(
            IntegrationCreate(
                name="SDK Inbound Test",
                provider=IntegrationProvider.custom_webhook,
                direction=IntegrationDirection.inbound,
            ),
            token=auth_token,
        )
        integration_id = created.id

        try:
            # 1. Set inbound config (auto-generated webhook path)
            inbound = await sdk_client.set_inbound_config(
                integration_id,
                InboundConfigCreate(
                    auth_method=InboundAuthMethod.none,
                    destination_service=DestinationService.tentackl,
                    destination_config={"agent_id": "test-agent"},
                ),
                token=auth_token,
            )
            assert inbound.webhook_path is not None
            assert inbound.webhook_url is not None
            assert "gateway/integrations" in inbound.webhook_url
            assert inbound.auth_method == "none"
            assert inbound.is_active is True
            print(f"Set inbound config with webhook URL: {inbound.webhook_url}")

            # 2. Get inbound config
            config = await sdk_client.get_inbound_config(integration_id, token=auth_token)
            assert config.webhook_path == inbound.webhook_path
            print(f"Got inbound config: {config.webhook_path}")

            # 3. Get webhook URL via dedicated method
            webhook_url = await sdk_client.get_inbound_webhook_url(
                integration_id, token=auth_token
            )
            assert webhook_url == inbound.webhook_url
            print(f"Got webhook URL: {webhook_url}")

            # 4. Delete inbound config
            deleted = await sdk_client.delete_inbound_config(integration_id, token=auth_token)
            assert deleted is True
            print("Deleted inbound config")

        finally:
            # Cleanup
            await sdk_client.delete_integration(integration_id, token=auth_token)

    async def test_outbound_config_management(self, sdk_client, auth_token):
        """Test outbound action config management."""
        # Create integration first
        created = await sdk_client.create_integration(
            IntegrationCreate(
                name="SDK Outbound Test",
                provider=IntegrationProvider.custom_webhook,
                direction=IntegrationDirection.outbound,
            ),
            token=auth_token,
        )
        integration_id = created.id

        try:
            # 1. Set outbound config
            outbound = await sdk_client.set_outbound_config(
                integration_id,
                OutboundConfigCreate(
                    action_type=OutboundActionType.post,
                    default_template={"content_type": "application/json"},
                    rate_limit_requests=100,
                    rate_limit_window_seconds=60,
                ),
                token=auth_token,
            )
            assert outbound.action_type == "post"
            assert outbound.rate_limit_requests == 100
            assert outbound.rate_limit_window_seconds == 60
            assert outbound.is_active is True
            print(f"Set outbound config: {outbound.action_type}")

            # 2. Get outbound config
            config = await sdk_client.get_outbound_config(integration_id, token=auth_token)
            assert config.action_type == "post"
            print(f"Got outbound config: {config.action_type}")

            # 3. Delete outbound config
            deleted = await sdk_client.delete_outbound_config(integration_id, token=auth_token)
            assert deleted is True
            print("Deleted outbound config")

        finally:
            # Cleanup
            await sdk_client.delete_integration(integration_id, token=auth_token)

    async def test_execute_action_e2e(self, sdk_client, auth_token):
        """Test executing an outbound action end-to-end."""
        # Create integration with webhook credential and outbound config
        created = await sdk_client.create_integration(
            IntegrationCreate(
                name="SDK Action Test",
                provider=IntegrationProvider.custom_webhook,
                direction=IntegrationDirection.outbound,
            ),
            token=auth_token,
        )
        integration_id = created.id

        try:
            # Add webhook_url credential
            credential = await sdk_client.add_credential(
                integration_id,
                CredentialCreate(
                    credential_type=CredentialType.webhook_url,
                    value="https://httpbin.org/post",
                ),
                token=auth_token,
            )
            print(f"Added webhook credential: {credential.id}")

            # Set outbound config
            outbound = await sdk_client.set_outbound_config(
                integration_id,
                OutboundConfigCreate(action_type=OutboundActionType.post),
                token=auth_token,
            )
            print(f"Set outbound config: {outbound.action_type}")

            # Execute action
            result = await sdk_client.execute_action(
                integration_id,
                "post",
                {"payload": {"test": "Hello from Mimic SDK!"}},
                token=auth_token,
            )

            assert result.success is True
            assert result.integration_id == integration_id
            assert result.action_type == "post"
            print(f"Action executed successfully: {result.message}")
            if result.result:
                print(f"Result: {result.result}")

        finally:
            # Cleanup
            await sdk_client.delete_integration(integration_id, token=auth_token)

    async def test_list_integrations_with_filters(self, sdk_client, auth_token):
        """Test listing integrations with various filters."""
        # Create integrations with different providers
        discord_int = await sdk_client.create_integration(
            IntegrationCreate(
                name="Filter Test Discord",
                provider=IntegrationProvider.discord,
                direction=IntegrationDirection.bidirectional,
            ),
            token=auth_token,
        )
        slack_int = await sdk_client.create_integration(
            IntegrationCreate(
                name="Filter Test Slack",
                provider=IntegrationProvider.slack,
                direction=IntegrationDirection.inbound,
            ),
            token=auth_token,
        )

        try:
            # Filter by provider
            discord_results = await sdk_client.list_integrations(
                provider="discord", token=auth_token
            )
            print(f"Found {discord_results.total} Discord integrations")
            assert any(i.id == discord_int.id for i in discord_results.items)

            # Filter by direction
            inbound_results = await sdk_client.list_integrations(
                direction="inbound", token=auth_token
            )
            print(f"Found {inbound_results.total} inbound integrations")
            assert any(i.id == slack_int.id for i in inbound_results.items)

        finally:
            # Cleanup
            await sdk_client.delete_integration(discord_int.id, token=auth_token)
            await sdk_client.delete_integration(slack_int.id, token=auth_token)


# =============================================================================
# Run tests directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov", "-s"])
