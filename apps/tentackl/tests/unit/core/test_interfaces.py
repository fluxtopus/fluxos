import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from src.interfaces.redis import RedisCache
from src.interfaces.external_api import HTTPClient, OpenAIClient, AnthropicClient


class TestRedisCache:
    
    @pytest.fixture
    def cache(self):
        return RedisCache()
    
    @pytest.fixture
    def mock_redis_client(self):
        mock = AsyncMock()
        mock.ping = AsyncMock()
        mock.get = AsyncMock()
        mock.set = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.exists = AsyncMock()
        mock.expire = AsyncMock()
        mock.lpush = AsyncMock()
        mock.lrange = AsyncMock()
        mock.close = AsyncMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_connect(self, cache, mock_redis_client):
        with patch('redis.asyncio.from_url', return_value=mock_redis_client):
            await cache.connect()
            
            assert cache.client is not None
            mock_redis_client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disconnect(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        await cache.disconnect()
        
        mock_redis_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_json_value(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        mock_redis_client.get.return_value = '{"key": "value"}'
        
        result = await cache.get("test_key")
        
        assert result == {"key": "value"}
        mock_redis_client.get.assert_called_with("test_key")
    
    @pytest.mark.asyncio
    async def test_get_none_value(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        mock_redis_client.get.return_value = None
        
        result = await cache.get("test_key")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        
        await cache.set("test_key", {"data": "test"}, ttl=60)
        
        mock_redis_client.setex.assert_called_with(
            "test_key", 60, '{"data": "test"}'
        )
    
    @pytest.mark.asyncio
    async def test_set_without_ttl(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        
        await cache.set("test_key", {"data": "test"})
        
        mock_redis_client.set.assert_called_with(
            "test_key", '{"data": "test"}'
        )
    
    @pytest.mark.asyncio
    async def test_delete(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        mock_redis_client.delete.return_value = 1
        
        result = await cache.delete("test_key")
        
        assert result is True
        mock_redis_client.delete.assert_called_with("test_key")
    
    @pytest.mark.asyncio
    async def test_exists(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        mock_redis_client.exists.return_value = 1
        
        result = await cache.exists("test_key")
        
        assert result is True
        mock_redis_client.exists.assert_called_with("test_key")
    
    @pytest.mark.asyncio
    async def test_expire(self, cache, mock_redis_client):
        cache.client = mock_redis_client
        mock_redis_client.expire.return_value = 1
        
        result = await cache.expire("test_key", 60)
        
        assert result is True
        mock_redis_client.expire.assert_called_with("test_key", 60)


class TestHTTPClient:
    
    @pytest.fixture
    def client(self):
        return HTTPClient(base_url="https://api.example.com")
    
    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        async with client as http_client:
            assert http_client.client is not None
        
        # Client should be closed after context
        assert http_client.client.is_closed
    
    @pytest.mark.asyncio
    async def test_request(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch('httpx.AsyncClient.request', return_value=mock_response) as mock_request:
            async with client:
                response = await client.request(
                    "GET",
                    "/test",
                    headers={"Authorization": "Bearer token"},
                    params={"q": "test"}
                )
                
                assert response.status_code == 200
                mock_request.assert_called_once()


class TestOpenAIClient:

    @pytest.fixture
    def client(self):
        # Patch where settings is used (in the external_api module)
        with patch('src.interfaces.external_api.settings') as mock_settings:
            mock_settings.OPENAI_API_KEY = 'test-key'
            return OpenAIClient()
    
    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(HTTPClient, 'request', new=AsyncMock(return_value=mock_response)) as mock_request:
            async with client:
                await client.request("GET", "/models")
                
                # Check that auth header was added
                call_args = mock_request.call_args
                headers = call_args[1]['headers']
                assert headers["Authorization"] == "Bearer test-key"
    
    @pytest.mark.asyncio
    async def test_create_completion(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, 'request', new=AsyncMock(return_value=mock_response)):
            async with client:
                result = await client.create_completion(
                    "gpt-4",
                    [{"role": "user", "content": "Hello"}]
                )
                
                assert "choices" in result


class TestAnthropicClient:

    @pytest.fixture
    def client(self):
        # Patch where settings is used (in the external_api module)
        with patch('src.interfaces.external_api.settings') as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = 'test-key'
            return AnthropicClient()
    
    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(HTTPClient, 'request', new=AsyncMock(return_value=mock_response)) as mock_request:
            async with client:
                await client.request("GET", "/models")
                
                # Check that auth header was added
                call_args = mock_request.call_args
                headers = call_args[1]['headers']
                assert headers["x-api-key"] == "test-key"
                assert headers["anthropic-version"] == "2023-06-01"