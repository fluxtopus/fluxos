"""Unit tests for SEC-003: validate_secrets() startup JWT secret validation."""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestValidateSecrets:
    """Test validate_secrets() function for JWT/secret key validation."""

    def _call_validate_secrets(self, app_env="development", secret_key=None, tentackl_secret_env=None):
        """Helper to call validate_secrets with mocked settings."""
        mock_settings = MagicMock()
        mock_settings.APP_ENV = app_env
        mock_settings.SECRET_KEY = secret_key
        mock_settings.JWT_SECRET = None

        env = {}
        if tentackl_secret_env is not None:
            env["TENTACKL_SECRET_KEY"] = tentackl_secret_env

        with patch("src.core.config.settings", mock_settings), \
             patch.dict(os.environ, env, clear=False):
            # Remove TENTACKL_SECRET_KEY from env if not provided
            if tentackl_secret_env is None and "TENTACKL_SECRET_KEY" in os.environ:
                del os.environ["TENTACKL_SECRET_KEY"]

            from src.core.config import validate_secrets
            validate_secrets()

    def test_production_raises_when_secret_key_is_none(self):
        """In production, None SECRET_KEY should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
            self._call_validate_secrets(app_env="production", secret_key=None)

    def test_production_raises_when_secret_key_is_insecure_default(self):
        """In production, known insecure defaults should raise RuntimeError."""
        insecure_values = [
            "your-secret-key-here-change-in-production",
            "change-this-in-production",
            "changeme",
            "secret",
            "password",
            "your-secret-key",
        ]
        for insecure in insecure_values:
            with pytest.raises(RuntimeError, match="insecure default"):
                self._call_validate_secrets(app_env="production", secret_key=insecure)

    def test_production_raises_when_secret_key_too_short(self):
        """In production, SECRET_KEY shorter than 16 chars should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="too short"):
            self._call_validate_secrets(app_env="production", secret_key="short")

    def test_production_passes_with_secure_key(self):
        """In production, a secure SECRET_KEY should not raise."""
        self._call_validate_secrets(
            app_env="production",
            secret_key="a-very-secure-random-key-that-is-long-enough-1234567890"
        )

    def test_production_raises_when_tentackl_secret_env_is_insecure(self):
        """In production, insecure TENTACKL_SECRET_KEY env var should raise."""
        with pytest.raises(RuntimeError, match="TENTACKL_SECRET_KEY"):
            self._call_validate_secrets(
                app_env="production",
                secret_key="a-very-secure-random-key-that-is-long-enough-1234567890",
                tentackl_secret_env="change-this-in-production"
            )

    def test_production_raises_when_tentackl_secret_env_too_short(self):
        """In production, short TENTACKL_SECRET_KEY should raise."""
        with pytest.raises(RuntimeError, match="TENTACKL_SECRET_KEY"):
            self._call_validate_secrets(
                app_env="production",
                secret_key="a-very-secure-random-key-that-is-long-enough-1234567890",
                tentackl_secret_env="short"
            )

    def test_development_warns_but_does_not_raise_when_none(self):
        """In development, None SECRET_KEY should log a warning, not raise."""
        with patch("src.core.config._logger") as mock_logger:
            self._call_validate_secrets(app_env="development", secret_key=None)
            mock_logger.warning.assert_called_once()
            assert "SECURITY WARNING" in mock_logger.warning.call_args[0][0]

    def test_development_warns_but_does_not_raise_when_insecure(self):
        """In development, insecure SECRET_KEY should log a warning, not raise."""
        with patch("src.core.config._logger") as mock_logger:
            self._call_validate_secrets(
                app_env="development",
                secret_key="your-secret-key-here-change-in-production"
            )
            mock_logger.warning.assert_called_once()

    def test_development_no_warning_with_secure_key(self):
        """In development, a secure key should produce no warning."""
        with patch("src.core.config._logger") as mock_logger:
            self._call_validate_secrets(
                app_env="development",
                secret_key="a-very-secure-random-key-that-is-long-enough-1234567890"
            )
            mock_logger.warning.assert_not_called()

    def test_case_insensitive_pattern_matching(self):
        """Insecure pattern matching should be case-insensitive."""
        with pytest.raises(RuntimeError):
            self._call_validate_secrets(
                app_env="production",
                secret_key="CHANGEME"
            )

    def test_production_passes_when_both_keys_secure(self):
        """Both SECRET_KEY and TENTACKL_SECRET_KEY secure should pass."""
        self._call_validate_secrets(
            app_env="production",
            secret_key="a-very-secure-random-key-that-is-long-enough-1234567890",
            tentackl_secret_env="another-very-secure-key-for-tentackl-middleware"
        )

    def test_staging_env_treated_as_production(self):
        """Non-development environments (staging, production) should raise on insecure keys."""
        with pytest.raises(RuntimeError):
            self._call_validate_secrets(app_env="staging", secret_key=None)
