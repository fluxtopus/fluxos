from types import SimpleNamespace

import pytest

from src.infrastructure.inbox.inbox_chat_service import _call_openrouter_llm


@pytest.mark.asyncio
async def test_call_openrouter_llm_raises_when_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.infrastructure.inbox.inbox_chat_service.settings.OPENROUTER_API_KEY",
        None,
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY not configured"):
        await _call_openrouter_llm(system_prompt="You are a helpful assistant.")


@pytest.mark.asyncio
async def test_call_openrouter_llm_uses_settings_key_and_returns_response(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.infrastructure.inbox.inbox_chat_service.settings.OPENROUTER_API_KEY",
        "test-openrouter-key",
    )

    routing = SimpleNamespace(models=["openai/gpt-4o-mini"], provider=None)
    monkeypatch.setattr(
        "src.llm.model_selector.ModelSelector.for_inbox_chat",
        staticmethod(lambda: routing),
    )

    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {"content": "hello", "tool_calls": []},
                        "finish_reason": "stop",
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "src.infrastructure.inbox.inbox_chat_service.httpx.AsyncClient",
        FakeAsyncClient,
    )

    result = await _call_openrouter_llm(
        system_prompt="System prompt",
        user_message="User message",
    )

    assert result == {"message": "hello", "tool_calls": [], "finish_reason": "stop"}
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-openrouter-key"
    assert captured["payload"]["model"] == "openai/gpt-4o-mini"
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "System prompt",
    }
    assert captured["payload"]["messages"][1] == {
        "role": "user",
        "content": "User message",
    }
