"""Unit tests for config.py webhook_base_url computed property."""
import pytest
from unittest.mock import patch
import os


class TestWebhookBaseUrl:
    """Test webhook_base_url computed property with different environment configurations."""

    def test_localhost_fallback_when_no_env_vars_set(self):
        """When API_BASE_URL is unset, use localhost."""
        env = {"PORT": "8000", "API_BASE_URL": ""}
        with patch.dict(os.environ, env, clear=True):
            # Need to reimport to pick up new environment
            from importlib import reload
            from src.core import config
            reload(config)

            # Default APP_PORT is 8000
            assert config.settings.webhook_base_url == "http://localhost:8000"

    def test_api_base_url_takes_highest_priority(self):
        """API_BASE_URL should override the localhost fallback."""
        env = {
            "API_BASE_URL": "https://api.fluxtopus.com",
        }
        with patch.dict(os.environ, env, clear=True):
            from importlib import reload
            from src.core import config
            reload(config)

            assert config.settings.webhook_base_url == "https://api.fluxtopus.com"

    def test_trailing_slash_stripped_from_api_base_url(self):
        """Trailing slashes should be stripped to prevent double slashes in URLs."""
        env = {
            "API_BASE_URL": "https://api.fluxtopus.com/"
        }
        with patch.dict(os.environ, env, clear=True):
            from importlib import reload
            from src.core import config
            reload(config)

            assert config.settings.webhook_base_url == "https://api.fluxtopus.com"
            # Verify no double slash when building full URL
            webhook_url = f"{config.settings.webhook_base_url}/api/events/webhook/test-id"
            assert "//" not in webhook_url.replace("https://", "")

    def test_localhost_fallback_uses_app_port(self):
        """Localhost fallback should use APP_PORT value."""
        # Note: APP_PORT defaults to 8000 when PORT env var is not set
        # The default behavior uses localhost with the configured port
        env = {"PORT": "8000", "API_BASE_URL": ""}
        with patch.dict(os.environ, env, clear=True):
            from importlib import reload
            from src.core import config
            reload(config)

            # Default port is 8000
            assert config.settings.webhook_base_url == "http://localhost:8000"
            # Verify it's using APP_PORT
            assert str(config.settings.APP_PORT) in config.settings.webhook_base_url
