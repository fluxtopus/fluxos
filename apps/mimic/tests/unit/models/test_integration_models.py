"""Unit tests for Integration models (INT-001 through INT-004)"""

import pytest
from datetime import datetime, timedelta

from src.database.models import (
    Integration,
    IntegrationCredential,
    IntegrationInboundConfig,
    IntegrationOutboundConfig,
    IntegrationProvider,
    IntegrationDirection,
    IntegrationStatus,
    CredentialType,
    InboundAuthMethod,
    DestinationService,
    OutboundActionType,
)
from src.services.key_encryption import KeyEncryptionService


class TestIntegrationModel:
    """Tests for Integration model (INT-001)"""

    def test_integration_creation_with_defaults(self, db_session):
        """Test creating integration with default values"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Team Discord",
            provider=IntegrationProvider.discord,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        assert integration.id is not None
        assert integration.organization_id == "org-123"
        assert integration.user_id == "user-456"
        assert integration.name == "Team Discord"
        assert integration.provider == IntegrationProvider.discord
        assert integration.direction == IntegrationDirection.bidirectional  # default
        assert integration.status == IntegrationStatus.active  # default
        assert integration.deleted_at is None
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_integration_all_providers(self, db_session):
        """Test all provider enum values"""
        providers = [
            IntegrationProvider.discord,
            IntegrationProvider.slack,
            IntegrationProvider.github,
            IntegrationProvider.stripe,
            IntegrationProvider.custom_webhook,
        ]

        for i, provider in enumerate(providers):
            integration = Integration(
                organization_id=f"org-{i}",
                user_id=f"user-{i}",
                name=f"Test {provider.value}",
                provider=provider,
            )
            db_session.add(integration)

        db_session.commit()
        assert db_session.query(Integration).count() == len(providers)

    def test_integration_directions(self, db_session):
        """Test all direction enum values"""
        directions = [
            IntegrationDirection.inbound,
            IntegrationDirection.outbound,
            IntegrationDirection.bidirectional,
        ]

        for i, direction in enumerate(directions):
            integration = Integration(
                organization_id=f"org-{i}",
                user_id=f"user-{i}",
                name=f"Test {direction.value}",
                provider=IntegrationProvider.slack,
                direction=direction,
            )
            db_session.add(integration)

        db_session.commit()
        assert db_session.query(Integration).count() == len(directions)

    def test_integration_statuses(self, db_session):
        """Test all status enum values"""
        statuses = [
            IntegrationStatus.active,
            IntegrationStatus.paused,
            IntegrationStatus.error,
        ]

        for i, status in enumerate(statuses):
            integration = Integration(
                organization_id=f"org-{i}",
                user_id=f"user-{i}",
                name=f"Test {status.value}",
                provider=IntegrationProvider.discord,
                status=status,
            )
            db_session.add(integration)

        db_session.commit()
        assert db_session.query(Integration).count() == len(statuses)

    def test_integration_soft_delete(self, db_session):
        """Test soft delete functionality"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="To Delete",
            provider=IntegrationProvider.discord,
        )
        db_session.add(integration)
        db_session.commit()

        # Soft delete
        integration.deleted_at = datetime.utcnow()
        db_session.commit()
        db_session.refresh(integration)

        assert integration.deleted_at is not None


class TestIntegrationCredentialModel:
    """Tests for IntegrationCredential model (INT-002)"""

    def test_credential_creation(self, db_session):
        """Test creating credential for integration"""
        # Create integration first
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Test Integration",
            provider=IntegrationProvider.discord,
        )
        db_session.add(integration)
        db_session.commit()

        # Create credential
        encryption_service = KeyEncryptionService()
        encrypted_value = encryption_service.encrypt("test-webhook-url")

        credential = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.webhook_url,
            encrypted_value=encrypted_value,
            credential_metadata={"channel_id": "123456"},
        )
        db_session.add(credential)
        db_session.commit()
        db_session.refresh(credential)

        assert credential.id is not None
        assert credential.integration_id == integration.id
        assert credential.credential_type == CredentialType.webhook_url
        assert credential.credential_metadata == {"channel_id": "123456"}
        assert encryption_service.decrypt(credential.encrypted_value) == "test-webhook-url"

    def test_multiple_credentials_per_integration(self, db_session):
        """Test that an integration can have multiple credentials"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Multi-Cred Integration",
            provider=IntegrationProvider.discord,
        )
        db_session.add(integration)
        db_session.commit()

        encryption_service = KeyEncryptionService()

        # Add multiple credentials
        cred1 = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.webhook_url,
            encrypted_value=encryption_service.encrypt("webhook-url"),
        )
        cred2 = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.api_key,
            encrypted_value=encryption_service.encrypt("api-key"),
        )
        db_session.add_all([cred1, cred2])
        db_session.commit()

        # Verify both credentials exist
        db_session.refresh(integration)
        assert len(integration.credentials) == 2

    def test_credential_with_expiration(self, db_session):
        """Test credential with OAuth token expiration"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="OAuth Integration",
            provider=IntegrationProvider.slack,
        )
        db_session.add(integration)
        db_session.commit()

        encryption_service = KeyEncryptionService()
        expires_at = datetime.utcnow() + timedelta(hours=1)

        credential = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.oauth_token,
            encrypted_value=encryption_service.encrypt("oauth-token"),
            expires_at=expires_at,
        )
        db_session.add(credential)
        db_session.commit()
        db_session.refresh(credential)

        assert credential.expires_at == expires_at

    def test_credential_cascade_delete(self, db_session):
        """Test that credentials are deleted when integration is deleted"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Cascade Test",
            provider=IntegrationProvider.discord,
        )
        db_session.add(integration)
        db_session.commit()

        encryption_service = KeyEncryptionService()
        credential = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.webhook_url,
            encrypted_value=encryption_service.encrypt("url"),
        )
        db_session.add(credential)
        db_session.commit()

        # Delete integration
        db_session.delete(integration)
        db_session.commit()

        # Verify credential was cascade deleted
        assert db_session.query(IntegrationCredential).count() == 0


class TestIntegrationInboundConfigModel:
    """Tests for IntegrationInboundConfig model (INT-003)"""

    def test_inbound_config_creation(self, db_session):
        """Test creating inbound config"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Inbound Test",
            provider=IntegrationProvider.github,
            direction=IntegrationDirection.inbound,
        )
        db_session.add(integration)
        db_session.commit()

        inbound_config = IntegrationInboundConfig(
            integration_id=integration.id,
            webhook_path="gh-webhooks-abc123",
            auth_method=InboundAuthMethod.signature,
            event_filters=["push", "pull_request"],
            destination_service=DestinationService.tentackl,
            destination_config={"task_template_id": "tmpl-123"},
        )
        db_session.add(inbound_config)
        db_session.commit()
        db_session.refresh(inbound_config)

        assert inbound_config.id is not None
        assert inbound_config.webhook_path == "gh-webhooks-abc123"
        assert inbound_config.auth_method == InboundAuthMethod.signature
        assert inbound_config.event_filters == ["push", "pull_request"]
        assert inbound_config.destination_service == DestinationService.tentackl

    def test_inbound_config_with_transform_template(self, db_session):
        """Test inbound config with Jinja2 transform template"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Transform Test",
            provider=IntegrationProvider.stripe,
            direction=IntegrationDirection.inbound,
        )
        db_session.add(integration)
        db_session.commit()

        transform_template = """
        {
            "event_type": "{{ type }}",
            "timestamp": "{{ created }}",
            "source": "stripe",
            "data": {{ data | tojson }}
        }
        """

        inbound_config = IntegrationInboundConfig(
            integration_id=integration.id,
            webhook_path="stripe-wh-xyz",
            auth_method=InboundAuthMethod.signature,
            transform_template=transform_template,
            destination_service=DestinationService.tentackl,
        )
        db_session.add(inbound_config)
        db_session.commit()
        db_session.refresh(inbound_config)

        assert "event_type" in inbound_config.transform_template

    def test_unique_webhook_path(self, db_session):
        """Test that webhook_path must be unique"""
        integration1 = Integration(
            organization_id="org-1",
            user_id="user-1",
            name="First",
            provider=IntegrationProvider.github,
        )
        integration2 = Integration(
            organization_id="org-2",
            user_id="user-2",
            name="Second",
            provider=IntegrationProvider.github,
        )
        db_session.add_all([integration1, integration2])
        db_session.commit()

        inbound1 = IntegrationInboundConfig(
            integration_id=integration1.id,
            webhook_path="unique-path",
            auth_method=InboundAuthMethod.none,
            destination_service=DestinationService.tentackl,
        )
        db_session.add(inbound1)
        db_session.commit()

        # Attempt to create another with same path should fail
        inbound2 = IntegrationInboundConfig(
            integration_id=integration2.id,
            webhook_path="unique-path",
            auth_method=InboundAuthMethod.none,
            destination_service=DestinationService.tentackl,
        )
        db_session.add(inbound2)

        with pytest.raises(Exception):  # SQLAlchemy will raise an IntegrityError
            db_session.commit()


class TestIntegrationOutboundConfigModel:
    """Tests for IntegrationOutboundConfig model (INT-004)"""

    def test_outbound_config_creation(self, db_session):
        """Test creating outbound config"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Outbound Test",
            provider=IntegrationProvider.discord,
            direction=IntegrationDirection.outbound,
        )
        db_session.add(integration)
        db_session.commit()

        outbound_config = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_message,
            default_template={"content": "Hello from Tentackl!"},
            rate_limit_requests=10,
            rate_limit_window_seconds=60,
        )
        db_session.add(outbound_config)
        db_session.commit()
        db_session.refresh(outbound_config)

        assert outbound_config.id is not None
        assert outbound_config.action_type == OutboundActionType.send_message
        assert outbound_config.default_template == {"content": "Hello from Tentackl!"}
        assert outbound_config.rate_limit_requests == 10
        assert outbound_config.rate_limit_window_seconds == 60

    def test_outbound_config_embed(self, db_session):
        """Test outbound config for Discord embed"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Embed Test",
            provider=IntegrationProvider.discord,
            direction=IntegrationDirection.outbound,
        )
        db_session.add(integration)
        db_session.commit()

        outbound_config = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_embed,
            default_template={
                "title": "Alert",
                "color": 0xFF0000,
                "fields": [
                    {"name": "Status", "value": "Error", "inline": True}
                ],
            },
        )
        db_session.add(outbound_config)
        db_session.commit()
        db_session.refresh(outbound_config)

        assert outbound_config.action_type == OutboundActionType.send_embed
        assert outbound_config.default_template["title"] == "Alert"

    def test_one_outbound_per_integration(self, db_session):
        """Test that only one outbound config per integration"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Single Outbound",
            provider=IntegrationProvider.slack,
        )
        db_session.add(integration)
        db_session.commit()

        outbound1 = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_message,
        )
        db_session.add(outbound1)
        db_session.commit()

        # Attempt to add another should fail due to unique constraint
        outbound2 = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_blocks,
        )
        db_session.add(outbound2)

        with pytest.raises(Exception):
            db_session.commit()


class TestIntegrationRelationships:
    """Tests for Integration model relationships"""

    def test_integration_with_all_configs(self, db_session):
        """Test integration with credentials, inbound, and outbound configs"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Full Integration",
            provider=IntegrationProvider.discord,
            direction=IntegrationDirection.bidirectional,
        )
        db_session.add(integration)
        db_session.commit()

        # Add credential
        encryption_service = KeyEncryptionService()
        credential = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.webhook_url,
            encrypted_value=encryption_service.encrypt("https://discord.com/webhook/123"),
        )

        # Add inbound config
        inbound = IntegrationInboundConfig(
            integration_id=integration.id,
            webhook_path="discord-in-123",
            auth_method=InboundAuthMethod.signature,
            destination_service=DestinationService.tentackl,
        )

        # Add outbound config
        outbound = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_message,
        )

        db_session.add_all([credential, inbound, outbound])
        db_session.commit()
        db_session.refresh(integration)

        # Verify relationships
        assert len(integration.credentials) == 1
        assert integration.inbound_config is not None
        assert integration.outbound_config is not None
        assert integration.credentials[0].credential_type == CredentialType.webhook_url
        assert integration.inbound_config.webhook_path == "discord-in-123"
        assert integration.outbound_config.action_type == OutboundActionType.send_message

    def test_integration_cascade_delete_all(self, db_session):
        """Test that all related configs are deleted when integration is deleted"""
        integration = Integration(
            organization_id="org-123",
            user_id="user-456",
            name="Cascade All",
            provider=IntegrationProvider.slack,
        )
        db_session.add(integration)
        db_session.commit()

        encryption_service = KeyEncryptionService()
        credential = IntegrationCredential(
            integration_id=integration.id,
            credential_type=CredentialType.bot_token,
            encrypted_value=encryption_service.encrypt("xoxb-token"),
        )
        inbound = IntegrationInboundConfig(
            integration_id=integration.id,
            webhook_path="slack-cascade-test",
            auth_method=InboundAuthMethod.signature,
            destination_service=DestinationService.tentackl,
        )
        outbound = IntegrationOutboundConfig(
            integration_id=integration.id,
            action_type=OutboundActionType.send_blocks,
        )

        db_session.add_all([credential, inbound, outbound])
        db_session.commit()

        # Verify items exist
        assert db_session.query(IntegrationCredential).count() == 1
        assert db_session.query(IntegrationInboundConfig).count() == 1
        assert db_session.query(IntegrationOutboundConfig).count() == 1

        # Delete integration
        db_session.delete(integration)
        db_session.commit()

        # Verify all related items were cascade deleted
        assert db_session.query(IntegrationCredential).count() == 0
        assert db_session.query(IntegrationInboundConfig).count() == 0
        assert db_session.query(IntegrationOutboundConfig).count() == 0
