"""
End-to-End Test: Inbox chat stream emits tool execution SSE events.

Validates that Flux chat streaming through `/api/inbox/chat/stream` emits
`tool_execution` events when tool calling is needed.

Requires:
- inkpass and tentackl services running
- OPENROUTER_API_KEY configured in tentackl runtime
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, List, Optional

import httpx
import pytest

_RUN_LOCAL_E2E = os.environ.get("RUN_LOCAL_E2E", "").lower() in {"1", "true", "yes"}
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _RUN_LOCAL_E2E,
        reason="Local-only E2E test. Set RUN_LOCAL_E2E=1 to execute.",
    ),
]


def _get_default_inkpass_url() -> str:
    try:
        socket.gethostbyname("inkpass")
        return "http://inkpass:8000"
    except socket.gaierror:
        return "http://localhost:8004"


def _get_default_tentackl_url() -> str:
    try:
        socket.gethostbyname("tentackl")
        return "http://tentackl:8000"
    except socket.gaierror:
        return "http://localhost:8005"


INKPASS_URL = os.environ.get("INKPASS_URL", _get_default_inkpass_url())
TENTACKL_URL = os.environ.get("TENTACKL_URL", _get_default_tentackl_url())

TEST_EMAIL = "admin@fluxtopus.com"
TEST_PASSWORD = "AiosAdmin123!"


@pytest.fixture(scope="module")
def auth_token() -> Optional[str]:
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{INKPASS_URL}/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        if response.status_code != 200:
            return None
        token = response.json().get("access_token")
        return token if isinstance(token, str) and token else None


def _parse_sse_events(lines: List[str]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in lines:
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


class TestInboxChatStreamToolsE2E:
    def test_chat_stream_emits_tool_execution_event(self, auth_token: Optional[str]) -> None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        body = {
            "message": (
                "Use web_search to find the latest OpenAI API updates from the last 7 days, "
                "then answer in 2 bullet points with 1 source URL."
            ),
            "onboarding": False,
        }

        timeout = httpx.Timeout(connect=20.0, read=120.0, write=20.0, pool=20.0)
        stream_lines: List[str] = []

        with httpx.Client(timeout=timeout, headers=headers) as client:
            with client.stream(
                "POST",
                f"{TENTACKL_URL}/api/inbox/chat/stream",
                json=body,
            ) as response:
                assert response.status_code == 200, response.text
                for line in response.iter_lines():
                    if not line:
                        continue
                    stream_lines.append(line)
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict) and event.get("done") is True:
                            break

        events = _parse_sse_events(stream_lines)
        assert events, "No SSE events received from inbox chat stream"

        has_tool_execution = any(
            event.get("status") == "tool_execution" for event in events
        )
        assert has_tool_execution, f"Expected tool_execution event. Events: {events}"

        assert any(event.get("done") is True for event in events), (
            f"Expected final done event. Events: {events}"
        )
