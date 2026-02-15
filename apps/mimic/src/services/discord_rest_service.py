"""Discord REST API service for sending follow-up messages.

Used to respond to deferred Discord interactions (slash commands, message
components) after async processing. Discord interaction tokens are valid
for 15 minutes and work like temporary webhooks — no bot token needed.

See: https://discord.com/developers/docs/interactions/receiving-and-responding#followup-messages
"""

import httpx
import structlog

logger = structlog.get_logger()

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordRestService:
    """Send follow-up messages to Discord interactions via REST API."""

    async def send_followup(
        self,
        application_id: str,
        interaction_token: str,
        content: str,
        embeds: list[dict] | None = None,
    ) -> dict:
        """Send a follow-up message to a deferred Discord interaction.

        Args:
            application_id: The Discord application (bot) ID.
            interaction_token: The interaction token from the original event.
            content: Text content to send.
            embeds: Optional list of Discord embed objects.

        Returns:
            The Discord API response as a dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx response from Discord.
        """
        url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}"
        payload: dict = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

        logger.info(
            "discord_followup_sent",
            application_id=application_id,
            content_length=len(content),
            has_embeds=bool(embeds),
        )
        return result
