# REVIEW: This module mixes interface definitions with concrete HTTP clients
# REVIEW: for OpenAI/Anthropic, which blurs abstraction boundaries. Consider
# REVIEW: moving concrete clients to a `clients` package and keeping interfaces
# REVIEW: pure. Also lacks retry/backoff policies.
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import httpx
import structlog
from src.core.config import settings

logger = structlog.get_logger()


class ExternalAPIInterface(ABC):
    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        pass


class HTTPClient(ExternalAPIInterface):
    """HTTP client for external API calls"""
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make HTTP request"""
        if not self.client:
            raise RuntimeError("Client not initialized. Use async with context.")
        
        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=headers,
                json=data if data and method != "GET" else None,
                params=params
            )
            
            logger.debug(
                "External API request",
                method=method,
                url=url,
                status=response.status_code
            )
            
            return response
            
        except httpx.TimeoutException as e:
            msg = f"Request timed out after {self.timeout}s"
            logger.error("request_timeout", url=url, timeout=self.timeout)
            raise httpx.TimeoutException(msg, request=getattr(e, 'request', None)) from e
        except Exception as e:
            logger.error(f"Request error", url=url, error=str(e))
            raise


class OpenAIClient(HTTPClient):
    """OpenAI API client"""
    
    def __init__(self):
        super().__init__(
            base_url="https://api.openai.com/v1",
            timeout=60
        )
        self.api_key = settings.OPENAI_API_KEY
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make OpenAI API request"""
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        headers = headers or {}
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        
        return await super().request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            params=params,
        )
    
    async def create_completion(self, model: str, messages: List[Dict]) -> Dict:
        """Create chat completion"""
        response = await self.request(
            "POST",
            "/chat/completions",
            data={
                "model": model,
                "messages": messages
            }
        )
        
        response.raise_for_status()
        return response.json()


class AnthropicClient(HTTPClient):
    """Anthropic API client"""
    
    def __init__(self):
        super().__init__(
            base_url="https://api.anthropic.com/v1",
            timeout=60
        )
        self.api_key = settings.ANTHROPIC_API_KEY
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make Anthropic API request"""
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")
        
        headers = headers or {}
        headers["x-api-key"] = self.api_key
        headers["anthropic-version"] = "2023-06-01"
        headers["Content-Type"] = "application/json"
        
        return await super().request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            params=params,
        )
    
    async def create_message(self, model: str, messages: List[Dict]) -> Dict:
        """Create message"""
        response = await self.request(
            "POST",
            "/messages",
            data={
                "model": model,
                "messages": messages,
                "max_tokens": 1024
            }
        )
        
        response.raise_for_status()
        return response.json()
