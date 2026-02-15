"""
Twitter/X API v2 Plugin for Tentackl workflows.

This plugin provides Twitter-specific operations including:
- Fetching user tweets
- Creating tweets with daily limit enforcement
- OAuth 2.0 and OAuth 1.0a authentication support
"""

from typing import Any, Dict, Optional
import os
import structlog
import hmac
import hashlib
import base64
import time
import secrets
from urllib.parse import urlparse, urlencode, parse_qs, quote

# Note: This plugin exports handlers for explicit registration in registry.py
# to avoid circular dependencies
from .http_plugin import http_request_handler, HttpPluginError
from ..state.twitter_state_tracker import TwitterStateTracker

logger = structlog.get_logger()


class TwitterPluginError(Exception):
    """Twitter plugin specific errors."""
    pass


# Initialize state tracker (singleton pattern)
_state_tracker: Optional[TwitterStateTracker] = None


def _get_state_tracker() -> TwitterStateTracker:
    """Get or create Twitter state tracker singleton."""
    global _state_tracker
    if _state_tracker is None:
        _state_tracker = TwitterStateTracker(
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            db=0,
            daily_limit=int(os.getenv("TWITTER_DAILY_POST_LIMIT", "3"))
        )
    return _state_tracker


def _generate_oauth1_signature(
    method: str,
    url: str,
    params: Dict[str, Any],
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str
) -> str:
    """
    Generate OAuth 1.0a signature for request signing.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        params: Request parameters
        consumer_key: OAuth consumer key (API Key)
        consumer_secret: OAuth consumer secret (API Secret)
        token: OAuth access token
        token_secret: OAuth access token secret
    
    Returns:
        OAuth 1.0a signature string
    """
    # Collect all parameters
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_token": token,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_urlsafe(16),
        "oauth_version": "1.0",
    }
    
    # Merge with request parameters
    all_params = {**oauth_params, **params}
    
    # Sort and encode parameters
    sorted_params = sorted(all_params.items())
    encoded_params = urlencode(sorted_params, quote_via=quote)
    
    # Create signature base string
    base_url = url.split("?")[0]  # Remove query string if present
    signature_base = f"{method.upper()}&{quote(base_url, safe='')}&{quote(encoded_params, safe='')}"
    
    # Create signing key
    signing_key = f"{quote(consumer_secret, safe='')}&{quote(token_secret, safe='')}"
    
    # Generate signature
    signature = hmac.new(
        signing_key.encode("utf-8"),
        signature_base.encode("utf-8"),
        hashlib.sha1
    ).digest()
    
    # Base64 encode signature
    oauth_signature = base64.b64encode(signature).decode("utf-8")
    
    # Add signature to OAuth params
    oauth_params["oauth_signature"] = oauth_signature
    
    # Create Authorization header
    auth_parts = [f'{k}="{quote(str(v), safe="")}"' for k, v in sorted(oauth_params.items())]
    auth_header = "OAuth " + ", ".join(auth_parts)
    
    return auth_header


async def _get_oauth2_user_token() -> Optional[str]:
    """
    Get OAuth 2.0 User Access Token using Client ID and Secret.
    
    This attempts to exchange credentials for a User Access Token.
    Note: Full OAuth 2.0 flow requires user authorization, but we can try
    to use existing token or get one via client credentials if available.
    
    Returns:
        User Access Token if available, None otherwise
    """
    # First, check if we already have a User Access Token
    user_token = os.getenv("X_OAUTH2_USER_ACCESS_TOKEN") or os.getenv("X_BEARER_TOKEN")
    if user_token:
        return user_token
    
    # Try to get token using Client ID/Secret (requires OAuth 2.0 PKCE flow)
    # For now, we'll require the user to provide the token directly
    # Full OAuth 2.0 flow would require browser redirect which isn't feasible here
    client_id = os.getenv("X_OAUTH2_CLIENT_ID")
    client_secret = os.getenv("X_OAUTH2_CLIENT_SECRET")
    
    if client_id and client_secret:
        # Note: To get a User Access Token, you need to complete the OAuth 2.0 flow:
        # 1. Generate authorization URL
        # 2. User authorizes in browser
        # 3. Exchange authorization code for access token
        # This requires user interaction, so we can't automate it here.
        # The user should set X_OAUTH2_USER_ACCESS_TOKEN with the token from the OAuth flow.
        logger.warning(
            "OAuth 2.0 Client ID/Secret found, but User Access Token required. "
            "Complete OAuth 2.0 flow to get X_OAUTH2_USER_ACCESS_TOKEN. "
            "See: https://docs.x.com/x-api/getting-started/getting-access"
        )
    
    return None


def _get_auth_headers(method: str = "GET", url: str = "", params: Dict[str, Any] = None) -> Dict[str, str]:
    """
    Get authentication headers for X API v2.
    
    Priority order:
    1. OAuth 2.0 User Context token (X_OAUTH2_USER_ACCESS_TOKEN) - preferred for posting
    2. OAuth 1.0a (if all credentials available) - reliable for posting
    3. OAuth 2.0 Bearer token (X_BEARER_TOKEN) - may be App-Only, can't post
    
    OAuth 2.0 User Context:
    - X_OAUTH2_USER_ACCESS_TOKEN (preferred) - User Access Token from OAuth 2.0 flow
    
    OAuth 1.0a:
    - X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, X_API_KEY, X_API_SECRET (all required)
    
    OAuth 2.0 App-Only (fallback, read-only):
    - X_BEARER_TOKEN - App-Only token, cannot post tweets
    
    Args:
        method: HTTP method (required for OAuth 1.0a)
        url: Request URL (required for OAuth 1.0a)
        params: Request parameters (required for OAuth 1.0a)
    
    Returns:
        Dictionary with Authorization header
    """
    headers: Dict[str, str] = {}
    params = params or {}
    
    # Check if we have complete OAuth 1.0a credentials (most reliable for posting)
    access_token = os.getenv("X_ACCESS_TOKEN") or os.getenv("X_API_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET") or os.getenv("X_API_ACCESS_TOKEN_SECRET")
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET") or os.getenv("X_API_KEY_SECRET")  # Support both names
    
    has_oauth1a = access_token and access_token_secret and api_key and api_secret
    
    # Try OAuth 2.0 User Context token first (best for posting)
    oauth2_user_token = os.getenv("X_OAUTH2_USER_ACCESS_TOKEN")
    if oauth2_user_token:
        headers["Authorization"] = f"Bearer {oauth2_user_token}"
        return headers
    
    # If we have complete OAuth 1.0a credentials, use them (reliable for posting)
    if has_oauth1a:
        auth_header = _generate_oauth1_signature(
            method=method,
            url=url,
            params=params,
            consumer_key=api_key,
            consumer_secret=api_secret,
            token=access_token,
            token_secret=access_token_secret
        )
        headers["Authorization"] = auth_header
        return headers
    
    # Fall back to Bearer token (may be App-Only, read-only)
    bearer_token = os.getenv("X_BEARER_TOKEN") or os.getenv("X_API_USER_ACCESS_TOKEN")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
        return headers
    
    raise TwitterPluginError(
        "No authentication credentials found. For posting tweets, set either:\n"
        "  - OAuth 2.0: X_OAUTH2_USER_ACCESS_TOKEN (User Context token)\n"
        "  - OAuth 1.0a: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET\n"
        "See docs/twitter_x_api_integration.md for setup instructions."
    )


async def fetch_user_tweets_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch user tweets from X API v2.
    
    Inputs:
        user_id: X user ID (optional, defaults to "me" with OAuth 2.0)
        max_results: Maximum number of tweets to fetch (default: 5, max: 100)
        tweet_fields: Comma-separated list of fields to include (optional)
        pagination_token: Token for pagination (optional)
    
    Returns:
        Dictionary with tweets data from X API
    """
    # Support both naming conventions for user ID
    user_id = inputs.get("user_id") or os.getenv("X_USER_ID") or os.getenv("X_API_USER_ID", "me")
    max_results = int(inputs.get("max_results", 5))
    tweet_fields = inputs.get("tweet_fields", "created_at,text,id,public_metrics")
    
    # Build URL
    url = f"https://api.x.com/2/users/{user_id}/tweets"
    
    # Build query parameters
    params: Dict[str, Any] = {
        "max_results": min(max_results, 100),  # API limit is 100
        "tweet.fields": tweet_fields
    }
    
    if inputs.get("pagination_token"):
        params["pagination_token"] = inputs["pagination_token"]
    
    # Get auth headers
    headers = _get_auth_headers(method="GET", url=url, params=params)
    headers["Content-Type"] = "application/json"
    
    # Use HTTP plugin
    try:
        result = await http_request_handler({
            "method": "GET",
            "url": url,
            "headers": headers,
            "params": params,
            "allow_hosts": ["api.x.com"],
            "timeout": 30
        })
        
        if result.get("status") != 200:
            error_data = result.get("json", {}) or result.get("text", "")
            raise TwitterPluginError(
                f"X API error: {result.get('status')} - {error_data}"
            )
        
        return {
            "success": True,
            "data": result.get("json", {}),
            "tweets": result.get("json", {}).get("data", []),
            "meta": result.get("json", {}).get("meta", {})
        }
    except HttpPluginError as e:
        raise TwitterPluginError(f"HTTP error: {str(e)}")
    except Exception as e:
        logger.error("Failed to fetch user tweets", error=str(e))
        raise TwitterPluginError(f"Failed to fetch tweets: {str(e)}")


async def create_tweet_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a tweet via X API v2 with daily limit enforcement.
    
    Inputs:
        text: Tweet text (required, max 280 characters)
        reply: Reply configuration (optional)
        media: Media configuration (optional)
        poll: Poll configuration (optional)
        check_limit: Whether to check daily limit before posting (default: True)
    
    Returns:
        Dictionary with created tweet data and remaining quota
    """
    text = inputs.get("text")
    if not text:
        raise TwitterPluginError("'text' is required for creating a tweet")
    
    if len(text) > 280:
        raise TwitterPluginError(f"Tweet text exceeds 280 characters (got {len(text)})")
    
    # Check daily limit if enabled
    check_limit = inputs.get("check_limit", True)
    if check_limit:
        state_tracker = _get_state_tracker()
        can_post = await state_tracker.check_daily_limit()
        if not can_post:
            remaining = await state_tracker.get_remaining_posts()
            raise TwitterPluginError(
                f"Daily post limit reached (3 posts/day). "
                f"Remaining posts: {remaining}. Try again tomorrow."
            )
    
    # Build request body
    body: Dict[str, Any] = {"text": text}
    
    # Add optional fields
    if inputs.get("reply"):
        body["reply"] = inputs["reply"]
    if inputs.get("media"):
        body["media"] = inputs["media"]
    if inputs.get("poll"):
        body["poll"] = inputs["poll"]
    
    # Get auth headers
    # For OAuth 1.0a with POST + JSON body, signature is based on URL only (no body params)
    # The body is sent separately as JSON
    headers = _get_auth_headers(method="POST", url="https://api.x.com/2/tweets", params={})
    headers["Content-Type"] = "application/json"
    
    # Use HTTP plugin
    try:
        result = await http_request_handler({
            "method": "POST",
            "url": "https://api.x.com/2/tweets",
            "headers": headers,
            "body": body,
            "allow_hosts": ["api.x.com"],
            "timeout": 30
        })
        
        if result.get("status") not in [200, 201]:
            error_data = result.get("json", {}) or result.get("text", "")
            raise TwitterPluginError(
                f"X API error: {result.get('status')} - {error_data}"
            )
        
        # Increment post count on success
        if check_limit:
            state_tracker = _get_state_tracker()
            new_count = await state_tracker.increment_post_count()
            remaining = await state_tracker.get_remaining_posts()
        else:
            new_count = None
            remaining = None
        
        response_data = result.get("json", {})
        tweet_data = response_data.get("data", {})
        
        return {
            "success": True,
            "tweet_id": tweet_data.get("id"),
            "text": tweet_data.get("text"),
            "data": tweet_data,
            "post_count": new_count,
            "remaining_posts": remaining
        }
    except HttpPluginError as e:
        raise TwitterPluginError(f"HTTP error: {str(e)}")
    except Exception as e:
        logger.error("Failed to create tweet", error=str(e))
        raise TwitterPluginError(f"Failed to create tweet: {str(e)}")


async def check_daily_limit_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check daily post limit status.
    
    Inputs:
        (none required)
    
    Returns:
        Dictionary with limit status and remaining posts
    """
    try:
        state_tracker = _get_state_tracker()
        can_post = await state_tracker.check_daily_limit()
        remaining = await state_tracker.get_remaining_posts()
        current_count = await state_tracker.get_post_count()
        
        return {
            "can_post": can_post,
            "remaining_posts": remaining,
            "current_count": current_count,
            "daily_limit": state_tracker.daily_limit
        }
    except Exception as e:
        logger.error("Failed to check daily limit", error=str(e))
        raise TwitterPluginError(f"Failed to check daily limit: {str(e)}")


# Export plugin handlers for explicit registration in registry.py
PLUGIN_HANDLERS = {
    "twitter_fetch_tweets": fetch_user_tweets_handler,
    "twitter_create_tweet": create_tweet_handler,
    "twitter_check_limit": check_daily_limit_handler,
}

# Plugin metadata for registration
TWITTER_PLUGIN_DEFINITIONS = [
    {
        "name": "twitter_fetch_tweets",
        "description": "Fetch user tweets from X API v2",
        "handler": fetch_user_tweets_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 100},
                "tweet_fields": {"type": "string"},
                "pagination_token": {"type": "string"}
            },
            "required": []
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "tweets": {"type": "array"},
                "data": {"type": "object"},
                "meta": {"type": "object"}
            }
        },
        "category": "social_media",
    },
    {
        "name": "twitter_create_tweet",
        "description": "Create a tweet via X API v2 with daily limit enforcement",
        "handler": create_tweet_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": 280},
                "reply": {"type": "object"},
                "media": {"type": "object"},
                "poll": {"type": "object"},
                "check_limit": {"type": "boolean", "default": True}
            },
            "required": ["text"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "tweet_id": {"type": "string"},
                "text": {"type": "string"},
                "post_count": {"type": "integer"},
                "remaining_posts": {"type": "integer"}
            }
        },
        "category": "social_media",
    },
    {
        "name": "twitter_check_limit",
        "description": "Check daily post limit status for X API",
        "handler": check_daily_limit_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {}
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "can_post": {"type": "boolean"},
                "remaining_posts": {"type": "integer"},
                "current_count": {"type": "integer"},
                "daily_limit": {"type": "integer"}
            }
        },
        "category": "social_media",
    },
]

