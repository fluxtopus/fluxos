"""
Unit tests for Twitter Plugin.

Tests Twitter/X API v2 plugin functionality with mocking.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import os

from src.plugins.twitter_plugin import (
    fetch_user_tweets_handler,
    create_tweet_handler,
    check_daily_limit_handler,
    TwitterPluginError,
    _get_auth_headers
)


@pytest.fixture
def mock_http_handler():
    """Mock HTTP handler for testing."""
    async def mock_handler(inputs):
        if inputs.get("method") == "GET":
            return {
                "status": 200,
                "json": {
                    "data": [
                        {"id": "123", "text": "Test tweet 1", "created_at": "2024-01-01T00:00:00Z"},
                        {"id": "124", "text": "Test tweet 2", "created_at": "2024-01-02T00:00:00Z"}
                    ],
                    "meta": {"result_count": 2}
                }
            }
        elif inputs.get("method") == "POST":
            return {
                "status": 201,
                "json": {
                    "data": {
                        "id": "125",
                        "text": inputs.get("body", {}).get("text", "")
                    }
                }
            }
    return mock_handler


@pytest.mark.asyncio
async def test_fetch_user_tweets_success(mock_http_handler):
    """Test successful tweet fetching."""
    with patch("src.plugins.twitter_plugin.http_request_handler", mock_http_handler):
        with patch("src.plugins.twitter_plugin._get_auth_headers", return_value={"Authorization": "Bearer token"}):
            result = await fetch_user_tweets_handler({
                "user_id": "me",
                "max_results": 5
            })
            
            assert result["success"] is True
            assert len(result["tweets"]) == 2
            assert result["tweets"][0]["id"] == "123"


@pytest.mark.asyncio
async def test_fetch_user_tweets_with_defaults(mock_http_handler):
    """Test tweet fetching with default parameters."""
    with patch("src.plugins.twitter_plugin.http_request_handler", mock_http_handler):
        with patch("src.plugins.twitter_plugin._get_auth_headers", return_value={"Authorization": "Bearer token"}):
            result = await fetch_user_tweets_handler({})
            
            assert result["success"] is True
            assert "tweets" in result


@pytest.mark.asyncio
async def test_create_tweet_success(mock_http_handler):
    """Test successful tweet creation."""
    with patch("src.plugins.twitter_plugin.http_request_handler", mock_http_handler):
        with patch("src.plugins.twitter_plugin._get_auth_headers", return_value={"Authorization": "Bearer token"}):
            with patch("src.plugins.twitter_plugin._get_state_tracker") as mock_tracker:
                mock_tracker_instance = MagicMock()
                mock_tracker_instance.check_daily_limit = AsyncMock(return_value=True)
                mock_tracker_instance.increment_post_count = AsyncMock(return_value=1)
                mock_tracker_instance.get_remaining_posts = AsyncMock(return_value=2)
                mock_tracker.return_value = mock_tracker_instance
                
                result = await create_tweet_handler({
                    "text": "Test tweet"
                })
                
                assert result["success"] is True
                assert result["tweet_id"] == "125"
                assert result["text"] == "Test tweet"
                assert result["post_count"] == 1
                assert result["remaining_posts"] == 2


@pytest.mark.asyncio
async def test_create_tweet_exceeds_daily_limit():
    """Test tweet creation when daily limit is exceeded."""
    with patch("src.plugins.twitter_plugin._get_state_tracker") as mock_tracker:
        mock_tracker_instance = MagicMock()
        mock_tracker_instance.check_daily_limit = AsyncMock(return_value=False)
        mock_tracker_instance.get_remaining_posts = AsyncMock(return_value=0)
        mock_tracker.return_value = mock_tracker_instance
        
        with pytest.raises(TwitterPluginError, match="Daily post limit reached"):
            await create_tweet_handler({
                "text": "Test tweet"
            })


@pytest.mark.asyncio
async def test_create_tweet_text_too_long():
    """Test tweet creation with text exceeding 280 characters."""
    long_text = "x" * 281
    
    with pytest.raises(TwitterPluginError, match="exceeds 280 characters"):
        await create_tweet_handler({
            "text": long_text
        })


@pytest.mark.asyncio
async def test_create_tweet_missing_text():
    """Test tweet creation without text."""
    with pytest.raises(TwitterPluginError, match="'text' is required"):
        await create_tweet_handler({})


@pytest.mark.asyncio
async def test_check_daily_limit():
    """Test checking daily limit status."""
    with patch("src.plugins.twitter_plugin._get_state_tracker") as mock_tracker:
        mock_tracker_instance = MagicMock()
        mock_tracker_instance.check_daily_limit = AsyncMock(return_value=True)
        mock_tracker_instance.get_remaining_posts = AsyncMock(return_value=2)
        mock_tracker_instance.get_post_count = AsyncMock(return_value=1)
        mock_tracker_instance.daily_limit = 3
        mock_tracker.return_value = mock_tracker_instance
        
        result = await check_daily_limit_handler({})
        
        assert result["can_post"] is True
        assert result["remaining_posts"] == 2
        assert result["current_count"] == 1
        assert result["daily_limit"] == 3


@pytest.mark.asyncio
async def test_get_auth_headers_oauth2():
    """Test OAuth 2.0 authentication header generation."""
    with patch.dict(os.environ, {"X_API_USER_ACCESS_TOKEN": "test_token"}):
        headers = _get_auth_headers()
        assert headers["Authorization"] == "Bearer test_token"


@pytest.mark.asyncio
async def test_get_auth_headers_no_credentials():
    """Test authentication header generation without credentials."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(TwitterPluginError, match="No authentication credentials"):
            _get_auth_headers()


@pytest.mark.asyncio
async def test_create_tweet_without_limit_check(mock_http_handler):
    """Test tweet creation without limit check."""
    with patch("src.plugins.twitter_plugin.http_request_handler", mock_http_handler):
        with patch("src.plugins.twitter_plugin._get_auth_headers", return_value={"Authorization": "Bearer token"}):
            result = await create_tweet_handler({
                "text": "Test tweet",
                "check_limit": False
            })
            
            assert result["success"] is True
            assert result["tweet_id"] == "125"


@pytest.mark.asyncio
async def test_fetch_user_tweets_api_error():
    """Test handling of API errors when fetching tweets."""
    async def error_handler(inputs):
        return {
            "status": 401,
            "json": {"error": "Unauthorized"},
            "text": "Unauthorized"
        }
    
    with patch("src.plugins.twitter_plugin.http_request_handler", error_handler):
        with patch("src.plugins.twitter_plugin._get_auth_headers", return_value={"Authorization": "Bearer token"}):
            with pytest.raises(TwitterPluginError, match="X API error"):
                await fetch_user_tweets_handler({
                    "user_id": "me",
                    "max_results": 5
                })

