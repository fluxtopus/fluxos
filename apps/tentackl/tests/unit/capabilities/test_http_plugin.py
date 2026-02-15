import pytest
import asyncio

from src.plugins.http_plugin import http_request_handler, HttpPluginError


@pytest.mark.asyncio
async def test_http_plugin_disallow_host():
    with pytest.raises(HttpPluginError):
        await http_request_handler({
            "url": "https://example.com/",  # not in default allowlist
            "timeout": 1,
        })


@pytest.mark.asyncio
async def test_http_plugin_allowed_host_and_mock(monkeypatch):
    class MockResp:
        def __init__(self):
            self.status_code = 200
            self.headers = {"content-type": "application/json"}
        def json(self):
            return {"name": "pikachu"}
        @property
        def text(self):
            return "{\"name\": \"pikachu\"}"

    class MockClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def request(self, method, url, headers=None, params=None, json=None, data=None):
            assert "pokeapi.co" in url
            return MockResp()

    import src.plugins.http_plugin as hp
    monkeypatch.setattr(hp.httpx, "AsyncClient", MockClient)

    # Mock the DB-based allowlist check
    from unittest.mock import AsyncMock
    mock_service = AsyncMock()
    mock_service.is_host_allowed = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(hp, "AllowedHostService", lambda: mock_service)

    res = await http_request_handler({
        "url": "https://pokeapi.co/api/v2/pokemon/pikachu",
        "timeout": 1,
    })
    assert res["status"] == 200
    assert res["json"]["name"] == "pikachu"

