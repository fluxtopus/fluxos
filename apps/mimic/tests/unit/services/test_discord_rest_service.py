"""Unit tests for DiscordRestService."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.discord_rest_service import DiscordRestService, DISCORD_API_BASE


@pytest.fixture
def service():
    return DiscordRestService()


class TestSendFollowup:
    @pytest.mark.asyncio
    async def test_send_followup_success(self, service):
        """Verify URL construction, payload, and successful response."""
        app_id = "123456789"
        token = "interaction-token-abc"
        content = "Hello from Tentackl!"
        expected_url = f"{DISCORD_API_BASE}/webhooks/{app_id}/{token}"
        mock_response_data = {"id": "msg-1", "content": content}

        with patch("src.services.discord_rest_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            # httpx.Response methods are synchronous, so use MagicMock
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response_data
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.send_followup(
                application_id=app_id,
                interaction_token=token,
                content=content,
            )

            mock_client.post.assert_called_once_with(
                expected_url,
                json={"content": content},
            )
            mock_resp.raise_for_status.assert_called_once()
            assert result == mock_response_data

    @pytest.mark.asyncio
    async def test_send_followup_with_embeds(self, service):
        """Verify embeds are included in the payload."""
        app_id = "123456789"
        token = "interaction-token-abc"
        content = "Results:"
        embeds = [{"title": "Test", "description": "Embed content"}]

        with patch("src.services.discord_rest_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "msg-2"}
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await service.send_followup(
                application_id=app_id,
                interaction_token=token,
                content=content,
                embeds=embeds,
            )

            mock_client.post.assert_called_once_with(
                f"{DISCORD_API_BASE}/webhooks/{app_id}/{token}",
                json={"content": content, "embeds": embeds},
            )
            assert result == {"id": "msg-2"}

    @pytest.mark.asyncio
    async def test_send_followup_http_error(self, service):
        """Verify httpx.HTTPStatusError propagates on non-2xx."""
        app_id = "123456789"
        token = "interaction-token-abc"

        with patch("src.services.discord_rest_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(404),
            )
            mock_client.post.return_value = mock_resp
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(httpx.HTTPStatusError):
                await service.send_followup(
                    application_id=app_id,
                    interaction_token=token,
                    content="test",
                )
