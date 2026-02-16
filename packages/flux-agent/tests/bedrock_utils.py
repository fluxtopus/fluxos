"""Utility helpers for Amazon Bedrock tests."""

from __future__ import annotations

import os


def has_bedrock_credentials() -> bool:
    """Return True when Bedrock credential env vars are configured."""
    return bool(
        os.getenv("AWS_PROFILE")
        or (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
        or os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    )
