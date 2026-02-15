"""Discord Interaction Endpoint verification service.

Handles Ed25519 signature verification for Discord Interactions Endpoint URL
validation. Discord sends a PING (type=1) request that must be verified with
Ed25519 and responded to with a PONG (type=1).

See: https://discord.com/developers/docs/interactions/receiving-and-responding
"""

import structlog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

logger = structlog.get_logger()


class DiscordInteractionService:
    """Stateless service for Discord interaction verification.

    Public key is passed in from caller (stored encrypted in IntegrationInboundConfig.signature_secret).
    """

    def verify_signature(
        self,
        public_key_hex: str,
        signature_hex: str,
        timestamp: str,
        body: bytes,
    ) -> bool:
        """Verify an Ed25519 signature from Discord.

        Discord signs: timestamp + body
        """
        try:
            logger.info(
                "discord_ed25519_verify_attempt",
                ts=timestamp,
                sig_prefix=signature_hex[:16] if signature_hex else "",
                body_len=len(body) if body else 0,
            )
            public_key_bytes = bytes.fromhex(public_key_hex)
            signature_bytes = bytes.fromhex(signature_hex)
            key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            message = timestamp.encode() + body
            key.verify(signature_bytes, message)
            logger.debug("discord_ed25519_verify_success")
            return True
        except (InvalidSignature, ValueError, Exception) as e:
            logger.warning(
                "discord_ed25519_verify_failed",
                error=type(e).__name__,
                error_msg=str(e),
                public_key_len=len(public_key_hex) if public_key_hex else 0,
                public_key_preview=public_key_hex[:16] + "..." if public_key_hex and len(public_key_hex) > 16 else public_key_hex,
            )
            return False

    def validate_public_key(self, public_key_hex: str) -> bool:
        """Validate that a hex string is a valid 32-byte Ed25519 public key."""
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            Ed25519PublicKey.from_public_bytes(public_key_bytes)
            return True
        except (ValueError, Exception):
            return False

    def is_ping(self, payload: dict) -> bool:
        """Check if the payload is a Discord PING interaction (type=1)."""
        return isinstance(payload, dict) and payload.get("type") == 1

    def pong_response(self) -> dict:
        """Return a Discord PONG response."""
        return {"type": 1}

    def is_interaction(self, payload: dict) -> bool:
        """Check if payload is an APPLICATION_COMMAND (type 2) or MESSAGE_COMPONENT (type 3)."""
        return isinstance(payload, dict) and payload.get("type") in (2, 3)

    def deferred_response(self) -> dict:
        """Return DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE (type 5).

        Discord shows a "thinking..." indicator while the bot processes the command.
        The bot has 15 minutes to send a follow-up message.
        """
        return {"type": 5}
