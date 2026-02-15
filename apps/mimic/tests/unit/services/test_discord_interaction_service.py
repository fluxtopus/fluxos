"""Unit tests for DiscordInteractionService."""

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.services.discord_interaction_service import DiscordInteractionService


@pytest.fixture
def service():
    return DiscordInteractionService()


@pytest.fixture
def ed25519_keypair():
    """Generate an Ed25519 keypair for testing."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes_raw()
    return private_key, public_key_bytes.hex()


class TestVerifySignature:
    def test_valid_signature(self, service, ed25519_keypair):
        private_key, public_key_hex = ed25519_keypair
        timestamp = "1234567890"
        body = b'{"type": 1}'

        message = timestamp.encode() + body
        signature = private_key.sign(message)
        signature_hex = signature.hex()

        assert service.verify_signature(
            public_key_hex=public_key_hex,
            signature_hex=signature_hex,
            timestamp=timestamp,
            body=body,
        ) is True

    def test_invalid_signature(self, service, ed25519_keypair):
        _, public_key_hex = ed25519_keypair

        assert service.verify_signature(
            public_key_hex=public_key_hex,
            signature_hex="aa" * 64,
            timestamp="1234567890",
            body=b'{"type": 1}',
        ) is False

    def test_invalid_public_key(self, service):
        assert service.verify_signature(
            public_key_hex="notavalidhexkey",
            signature_hex="aa" * 64,
            timestamp="1234567890",
            body=b'{"type": 1}',
        ) is False

    def test_wrong_body_fails(self, service, ed25519_keypair):
        private_key, public_key_hex = ed25519_keypair
        timestamp = "1234567890"
        body = b'{"type": 1}'

        message = timestamp.encode() + body
        signature = private_key.sign(message)
        signature_hex = signature.hex()

        # Verify with different body
        assert service.verify_signature(
            public_key_hex=public_key_hex,
            signature_hex=signature_hex,
            timestamp=timestamp,
            body=b'{"type": 2}',
        ) is False

    def test_wrong_timestamp_fails(self, service, ed25519_keypair):
        private_key, public_key_hex = ed25519_keypair
        timestamp = "1234567890"
        body = b'{"type": 1}'

        message = timestamp.encode() + body
        signature = private_key.sign(message)
        signature_hex = signature.hex()

        # Verify with different timestamp
        assert service.verify_signature(
            public_key_hex=public_key_hex,
            signature_hex=signature_hex,
            timestamp="9999999999",
            body=body,
        ) is False


class TestValidatePublicKey:
    def test_valid_key(self, service, ed25519_keypair):
        _, public_key_hex = ed25519_keypair
        assert service.validate_public_key(public_key_hex) is True

    def test_invalid_short_hex(self, service):
        assert service.validate_public_key("abcd") is False

    def test_invalid_not_hex(self, service):
        assert service.validate_public_key("not_a_hex_string_at_all!!!") is False

    def test_invalid_empty(self, service):
        assert service.validate_public_key("") is False

    def test_invalid_wrong_length(self, service):
        # 31 bytes instead of 32
        assert service.validate_public_key("aa" * 31) is False


class TestIsPing:
    def test_ping_type_1(self, service):
        assert service.is_ping({"type": 1}) is True

    def test_not_ping_type_2(self, service):
        assert service.is_ping({"type": 2}) is False

    def test_not_ping_empty(self, service):
        assert service.is_ping({}) is False

    def test_not_ping_none(self, service):
        assert service.is_ping(None) is False

    def test_not_ping_string_type(self, service):
        assert service.is_ping({"type": "1"}) is False


class TestPongResponse:
    def test_returns_type_1(self, service):
        assert service.pong_response() == {"type": 1}


class TestIsInteraction:
    def test_application_command_type_2(self, service):
        assert service.is_interaction({"type": 2}) is True

    def test_message_component_type_3(self, service):
        assert service.is_interaction({"type": 3}) is True

    def test_ping_type_1_is_not_interaction(self, service):
        assert service.is_interaction({"type": 1}) is False

    def test_other_type_4_is_not_interaction(self, service):
        assert service.is_interaction({"type": 4}) is False

    def test_empty_dict(self, service):
        assert service.is_interaction({}) is False

    def test_none(self, service):
        assert service.is_interaction(None) is False

    def test_string_type(self, service):
        assert service.is_interaction({"type": "2"}) is False


class TestDeferredResponse:
    def test_returns_type_5(self, service):
        assert service.deferred_response() == {"type": 5}
