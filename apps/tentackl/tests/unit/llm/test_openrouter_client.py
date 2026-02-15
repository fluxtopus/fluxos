import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import httpx
from src.llm.openrouter_client import OpenRouterClient
from src.interfaces.llm import LLMMessage, LLMResponse


@pytest.fixture
def mock_response():
    """Create a mock HTTP response"""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture
def openrouter_client():
    """Create OpenRouterClient instance"""
    return OpenRouterClient(api_key="test-key")


class TestOpenRouterClient:
    """Test OpenRouter client functionality"""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test client initialization"""
        client = OpenRouterClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.base_url == "https://openrouter.ai/api/v1"
        assert client.timeout == 120
    
    @pytest.mark.asyncio
    async def test_request_headers(self, openrouter_client):
        """Test request headers are set correctly"""
        # Mock the parent class request method
        with patch('src.interfaces.external_api.HTTPClient.request') as mock_request:
            mock_request.return_value = AsyncMock()
            
            async with openrouter_client:
                await openrouter_client.request("GET", "/test")
                
                # Check headers - they're passed as the 3rd positional argument
                call_args = mock_request.call_args
                headers = call_args[0][2]  # method, url, headers
                
                assert headers['Authorization'] == 'Bearer test-key'
                assert headers['Content-Type'] == 'application/json'
    
    @pytest.mark.asyncio
    async def test_create_completion(self, openrouter_client, mock_response):
        """Test creating a completion"""
        mock_response.json.return_value = {
            "id": "test-id",
            "model": "openai/gpt-4o",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }
        
        with patch.object(openrouter_client, 'request', return_value=mock_response):
            async with openrouter_client:
                messages = [
                    LLMMessage(role="user", content="Hello")
                ]
                
                response = await openrouter_client.create_completion(
                    messages=messages,
                    model="openai/gpt-4o",
                    temperature=0.7
                )
                
                assert isinstance(response, LLMResponse)
                assert response.content == "Test response"
                assert response.model == "openai/gpt-4o"
                assert response.usage['total_tokens'] == 15
    
    @pytest.mark.asyncio
    async def test_create_completion_error(self, openrouter_client):
        """Test error handling in create_completion"""
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 400
        error_response.text = "Bad request"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Bad request",
            request=MagicMock(),
            response=error_response
        )
        
        with patch.object(openrouter_client, 'request', return_value=error_response):
            async with openrouter_client:
                messages = [LLMMessage(role="user", content="Hello")]
                
                with pytest.raises(httpx.HTTPStatusError):
                    await openrouter_client.create_completion(
                        messages=messages,
                        model="test-model"
                    )
    
    @pytest.mark.asyncio
    async def test_streaming_completion(self, openrouter_client):
        """Test streaming completion"""
        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            chunks = [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                'data: [DONE]'
            ]
            for chunk in chunks:
                yield chunk
        
        with patch.object(openrouter_client, '_stream_request', side_effect=mock_stream):
            async with openrouter_client:
                messages = [LLMMessage(role="user", content="Hi")]
                
                chunks = []
                async for chunk in openrouter_client.create_completion_stream(
                    messages=messages,
                    model="test-model"
                ):
                    chunks.append(chunk)
                
                assert chunks == ["Hello", " world"]
    
    @pytest.mark.asyncio
    async def test_list_models(self, openrouter_client, mock_response):
        """Test listing available models"""
        mock_response.json.return_value = {
            "data": [
                {"id": "openai/gpt-4", "name": "GPT-4"},
                {"id": "anthropic/claude-2", "name": "Claude 2"}
            ]
        }
        
        with patch.object(openrouter_client, 'request', return_value=mock_response):
            async with openrouter_client:
                models = await openrouter_client.list_models()
                
                assert len(models) == 2
                assert models[0]['id'] == "openai/gpt-4"
                assert models[1]['id'] == "anthropic/claude-2"
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, openrouter_client, mock_response):
        """Test successful health check"""
        mock_response.status_code = 200
        
        with patch.object(openrouter_client, 'request', return_value=mock_response):
            async with openrouter_client:
                health = await openrouter_client.health_check()
                assert health is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, openrouter_client):
        """Test failed health check"""
        with patch.object(openrouter_client, 'request', side_effect=Exception("Connection error")):
            async with openrouter_client:
                health = await openrouter_client.health_check()
                assert health is False
    
    @pytest.mark.asyncio
    async def test_no_api_key_error(self):
        """Test error when no API key is provided"""
        with patch('src.llm.openrouter_client.settings') as mock_settings:
            mock_settings.OPENROUTER_API_KEY = None
            client = OpenRouterClient(api_key=None)
            
            async with client:
                with pytest.raises(ValueError, match="OpenRouter API key not configured"):
                    await client.request("GET", "/test")
    
    @pytest.mark.asyncio
    async def test_site_attribution_headers(self):
        """Test site attribution headers"""
        client = OpenRouterClient(api_key="test-key")
        client.site_url = "https://example.com"
        client.site_name = "Test App"
        
        # Mock the parent class request method
        with patch('src.interfaces.external_api.HTTPClient.request') as mock_request:
            mock_request.return_value = AsyncMock()
            
            async with client:
                await client.request("GET", "/test")
                
                # Check headers - they're passed as the 3rd positional argument
                call_args = mock_request.call_args
                headers = call_args[0][2]  # method, url, headers
                
                assert headers['HTTP-Referer'] == 'https://example.com'
                assert headers['X-Title'] == 'Test App'