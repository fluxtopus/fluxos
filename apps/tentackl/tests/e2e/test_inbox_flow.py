"""
End-to-End Test: Full Inbox Flow (INBOX-036)

Validates the complete inbox lifecycle against real Docker services:
1. Authenticate as the test user via InkPass
2. Create a task via POST /api/tasks/with-steps
3. Start the task via POST /api/tasks/{id}/start
4. Verify GET /api/inbox returns the task's conversation (UNREAD)
5. Verify GET /api/inbox/unread-count returns >= 1
6. GET /api/inbox/{conversation_id}/thread — verify messages exist
7. PATCH /api/inbox/{conversation_id} with read_status='read'
8. Verify thread shows read_status='read'
9. POST /api/inbox/{conversation_id}/follow-up — verify new task created
10. PATCH /api/inbox/{conversation_id} with read_status='archived'
11. Verify archived item handling in inbox list

Requires: inkpass, tentackl, postgres, redis all running.

NOTE: This test runs INSIDE the tentackl container via
`docker compose exec tentackl python -m pytest tests/e2e/test_inbox_flow.py`.
It uses Docker service names (not localhost) for inter-service HTTP calls.

Task execution requires an LLM (OpenRouter); the inbox conversation is created
when the task starts, so the test does NOT wait for task completion.
"""

import os
import time
import uuid

import httpx
import pytest

# URLs configurable via env vars.  Defaults are for running on the host
# machine with Docker Compose port-forwarding.
INKPASS_URL = os.environ.get("INKPASS_URL", "http://localhost:8004")
TENTACKL_URL = os.environ.get("TENTACKL_URL", "http://localhost:8005")

TEST_EMAIL = "admin@fluxtopus.com"
TEST_PASSWORD = "AiosAdmin123!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_token():
    """Authenticate once for all tests in this module."""
    with httpx.Client(timeout=15) as c:
        resp = c.post(
            f"{INKPASS_URL}/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        token = resp.json().get("access_token")
        assert token, "No access_token in login response"
        return token


@pytest.fixture(scope="module")
def api(auth_token):
    """Shared httpx client with auth headers."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120, headers=headers) as c:
        yield c


@pytest.fixture(scope="module")
def task_and_inbox(api):
    """Create a task, start it, and return the task + inbox conversation data.

    The inbox conversation is created when the task starts (before execution).
    We do NOT wait for task completion — that requires a configured LLM.
    """
    goal = f"E2E inbox test {uuid.uuid4().hex[:8]}"

    # 1. Create a task with pre-defined steps
    create_resp = api.post(
        f"{TENTACKL_URL}/api/tasks/with-steps",
        json={
            "goal": goal,
            "steps": [
                {
                    "name": "Gather data",
                    "description": "Gather initial data for the report",
                    "agent_type": "data_processor",
                },
                {
                    "name": "Analyze findings",
                    "description": "Analyze gathered data and produce summary",
                    "agent_type": "analyzer",
                },
            ],
        },
    )
    assert create_resp.status_code == 201, (
        f"Task creation failed ({create_resp.status_code}): {create_resp.text}"
    )
    task = create_resp.json()
    task_id = task["id"]

    # 2. Start the task (creates inbox conversation as a side effect)
    start_resp = api.post(f"{TENTACKL_URL}/api/tasks/{task_id}/start")
    assert start_resp.status_code in (200, 409), (
        f"Task start failed ({start_resp.status_code}): {start_resp.text}"
    )

    # 3. Brief wait for the inbox conversation to be created
    time.sleep(2)

    # 4. Find our task's inbox conversation
    inbox_resp = api.get(f"{TENTACKL_URL}/api/inbox")
    assert inbox_resp.status_code == 200, f"Inbox list failed: {inbox_resp.text}"
    inbox_data = inbox_resp.json()

    # The inbox API returns {"items": [...], "total": N, "limit": N, "offset": N}
    items = inbox_data.get("items", inbox_data) if isinstance(inbox_data, dict) else inbox_data
    matching = [item for item in items if item.get("task_id") == task_id]
    assert len(matching) >= 1, (
        f"No inbox item found for task {task_id}. "
        f"Inbox has {len(items)} items with task_ids: "
        f"{[i.get('task_id') for i in items]}"
    )

    inbox_item = matching[0]
    return {
        "task_id": task_id,
        "goal": goal,
        "conversation_id": inbox_item["conversation_id"],
        "inbox_item": inbox_item,
    }


# ---------------------------------------------------------------------------
# Tests — ordered by the PRD flow (steps 5-11)
# ---------------------------------------------------------------------------

class TestInboxFlowE2E:
    """End-to-end tests for the full inbox flow.

    Tests run in order within the class (pytest default: definition order).
    """

    def test_01_inbox_item_has_unread_status(self, task_and_inbox):
        """(5) Inbox item created on task start should be UNREAD."""
        assert task_and_inbox["inbox_item"]["read_status"] == "unread"

    def test_02_inbox_item_has_last_message(self, task_and_inbox):
        """(5) Inbox item should have a last_message_text preview."""
        text = task_and_inbox["inbox_item"].get("last_message_text", "")
        assert text, "Inbox item should have last_message_text"

    def test_03_inbox_item_has_normal_priority(self, task_and_inbox):
        """(5) A just-started task should have priority=normal."""
        assert task_and_inbox["inbox_item"]["priority"] == "normal"

    def test_04_unread_count_at_least_one(self, api, task_and_inbox):
        """(6) GET /api/inbox/unread-count should return count >= 1."""
        resp = api.get(f"{TENTACKL_URL}/api/inbox/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("count", 0) >= 1, (
            f"Expected unread count >= 1, got {data}"
        )

    def test_05_thread_has_messages(self, api, task_and_inbox):
        """(7) Thread should have at least 1 message (the 'Started working on' message)."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.get(f"{TENTACKL_URL}/api/inbox/{conv_id}/thread")
        assert resp.status_code == 200
        thread = resp.json()
        assert "messages" in thread
        assert len(thread["messages"]) >= 1

    def test_06_thread_messages_chronological(self, api, task_and_inbox):
        """(7) Thread messages should be in chronological order."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.get(f"{TENTACKL_URL}/api/inbox/{conv_id}/thread")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        if len(messages) >= 2:
            timestamps = [
                m.get("timestamp", m.get("created_at", ""))
                for m in messages
            ]
            assert timestamps == sorted(timestamps), (
                "Messages should be in chronological order"
            )

    def test_07_thread_has_task_data(self, api, task_and_inbox):
        """(7) Thread should include linked task data with matching goal."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.get(f"{TENTACKL_URL}/api/inbox/{conv_id}/thread")
        assert resp.status_code == 200
        thread = resp.json()
        assert thread.get("task") is not None, "Thread should include task data"
        assert thread["task"].get("goal") == task_and_inbox["goal"]

    def test_08_mark_as_read(self, api, task_and_inbox):
        """(8) PATCH read_status='read' should succeed."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.patch(
            f"{TENTACKL_URL}/api/inbox/{conv_id}",
            json={"read_status": "read"},
        )
        assert resp.status_code == 200, f"Mark as read failed: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("read_status") == "read"

    def test_09_thread_shows_read_after_mark(self, api, task_and_inbox):
        """(9) After marking as read, thread should reflect read_status='read'."""
        conv_id = task_and_inbox["conversation_id"]

        # Ensure it's marked read
        api.patch(
            f"{TENTACKL_URL}/api/inbox/{conv_id}",
            json={"read_status": "read"},
        )

        resp = api.get(f"{TENTACKL_URL}/api/inbox/{conv_id}/thread")
        assert resp.status_code == 200
        assert resp.json().get("read_status") == "read"

    def test_10_follow_up_creates_new_task(self, api, task_and_inbox):
        """(10) POST follow-up should create a new task."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.post(
            f"{TENTACKL_URL}/api/inbox/{conv_id}/follow-up",
            json={"text": "Summarize findings from this task in bullet points"},
        )
        assert resp.status_code == 200, f"Follow-up failed: {resp.text}"
        data = resp.json()
        assert "task_id" in data, f"Response should contain task_id: {data}"
        assert data.get("goal"), "Follow-up task should have a goal"

    def test_11_archive_conversation(self, api, task_and_inbox):
        """(11) PATCH read_status='archived' should succeed."""
        conv_id = task_and_inbox["conversation_id"]
        resp = api.patch(
            f"{TENTACKL_URL}/api/inbox/{conv_id}",
            json={"read_status": "archived"},
        )
        assert resp.status_code == 200, f"Archive failed: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert data.get("read_status") == "archived"

    def test_12_archived_excluded_from_default_list(self, api, task_and_inbox):
        """(11) Archived item should not appear in the default inbox list,
        or if it does, it should show archived status."""
        conv_id = task_and_inbox["conversation_id"]

        # Ensure archived
        api.patch(
            f"{TENTACKL_URL}/api/inbox/{conv_id}",
            json={"read_status": "archived"},
        )

        resp = api.get(f"{TENTACKL_URL}/api/inbox")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        matching = [i for i in items if i["conversation_id"] == conv_id]

        # Default list may or may not filter archived.
        # If archived items appear, they must show archived status.
        if matching:
            assert matching[0]["read_status"] == "archived"
