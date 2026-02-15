# REVIEW: Client mixes HTTP transport, LLM interface, and provider-specific
# REVIEW: routing concerns in one class, with no retry/backoff policy. Consider
# REVIEW: splitting transport from model routing and centralizing error handling.
import httpx
import json
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from dataclasses import dataclass, field
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse, LLMClientInterface
from src.interfaces.external_api import HTTPClient
from src.core.config import settings
import structlog

logger = structlog.get_logger()


@dataclass
class ProviderRouting:
    """
    OpenRouter provider routing configuration.

    See: https://openrouter.ai/docs/guides/routing/provider-selection
    """
    # Provider preferences
    order: Optional[List[str]] = None  # e.g., ["Anthropic", "OpenAI", "Google"]
    only: Optional[List[str]] = None   # Restrict to these providers only
    ignore: Optional[List[str]] = None  # Exclude these providers

    # Sorting priority
    sort: Optional[str] = None  # "price", "throughput", or "latency"

    # Fallback behavior
    allow_fallbacks: bool = True

    # Advanced options
    require_parameters: bool = False  # Only route to providers supporting all params
    data_collection: Optional[str] = None  # "allow" or "deny"
    quantizations: Optional[List[str]] = None  # ["int4", "fp8", etc.]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenRouter API format."""
        result = {}
        if self.order:
            result["order"] = self.order
        if self.only:
            result["only"] = self.only
        if self.ignore:
            result["ignore"] = self.ignore
        if self.sort:
            result["sort"] = self.sort
        if not self.allow_fallbacks:
            result["allow_fallbacks"] = False
        if self.require_parameters:
            result["require_parameters"] = True
        if self.data_collection:
            result["data_collection"] = self.data_collection
        if self.quantizations:
            result["quantizations"] = self.quantizations
        return result


@dataclass
class WebPlugin:
    """
    OpenRouter web search plugin configuration.

    See: https://openrouter.ai/docs/guides/features/plugins/web-search

    Enables real-time web search during LLM completion. Results are returned
    as citations in the response annotations.
    """
    id: str = "web"
    engine: Optional[str] = None  # "native", "exa", or None (auto-select)
    max_results: int = 5
    search_prompt: Optional[str] = None  # Custom search query (default: inferred from messages)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenRouter API format."""
        result = {"id": self.id}
        if self.engine:
            result["engine"] = self.engine
        if self.max_results != 5:
            result["max_results"] = self.max_results
        if self.search_prompt:
            result["search_prompt"] = self.search_prompt
        return result


@dataclass
class ModelRouting:
    """
    Complete model routing configuration for OpenRouter.

    Supports:
    - Single model with optional suffix (:nitro, :floor)
    - Multiple models for fallback
    - Provider routing preferences
    """
    # Primary model or list of fallback models
    models: List[str] = field(default_factory=lambda: ["openrouter/auto"])

    # Provider routing configuration
    provider: Optional[ProviderRouting] = None

    @classmethod
    def single(cls, model: str, provider: Optional[ProviderRouting] = None) -> "ModelRouting":
        """Create routing for a single model."""
        return cls(models=[model], provider=provider)

    @classmethod
    def with_fallbacks(
        cls,
        models: List[str],
        provider: Optional[ProviderRouting] = None
    ) -> "ModelRouting":
        """Create routing with fallback models."""
        return cls(models=models, provider=provider)

    @classmethod
    def auto(cls, provider: Optional[ProviderRouting] = None) -> "ModelRouting":
        """Use OpenRouter's auto model selection."""
        return cls(models=["openrouter/auto"], provider=provider)

    @classmethod
    def speed_optimized(cls, models: List[str]) -> "ModelRouting":
        """Create routing optimized for speed/throughput."""
        # Add :nitro suffix for speed optimization
        nitro_models = [f"{m}:nitro" if ":" not in m else m for m in models]
        return cls(
            models=nitro_models,
            provider=ProviderRouting(sort="throughput")
        )

    @classmethod
    def cost_optimized(cls, models: List[str]) -> "ModelRouting":
        """Create routing optimized for cost."""
        # Add :floor suffix for cost optimization
        floor_models = [f"{m}:floor" if ":" not in m else m for m in models]
        return cls(
            models=floor_models,
            provider=ProviderRouting(sort="price")
        )


class OpenRouterClient(HTTPClient, LLMInterface, LLMClientInterface):
    """OpenRouter API client for multi-LLM access"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            timeout=120  # Longer timeout for LLM requests
        )
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.site_url = settings.SITE_URL
        self.site_name = settings.SITE_NAME
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make OpenRouter API request"""
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
        
        headers = headers or {}
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        
        # Optional headers for app attribution
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name
        
        return await super().request(method, url, headers, data, params)
    
    async def _stream_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """Make streaming OpenRouter API request"""
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
        
        if not self.client:
            raise RuntimeError("Client not initialized. Use async with context.")
        
        headers = headers or {}
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        
        # Optional headers for app attribution
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name
        
        async with self.client.stream(
            method=method,
            url=url,
            headers=headers,
            json=data,
            params=params
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                yield line
    
    async def create_completion(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        routing: Optional[ModelRouting] = None,
        plugins: Optional[List[WebPlugin]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Create a completion from messages.

        Args:
            messages: List of LLMMessage objects
            model: Single model ID (simple usage)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            routing: ModelRouting config for fallbacks and provider selection
            plugins: List of plugins (e.g., WebPlugin for web search)
            **kwargs: Additional OpenRouter parameters

        Note:
            - If `routing` is provided, it takes precedence over `model`
            - If neither is provided, defaults to openrouter/auto
            - If `plugins` includes WebPlugin, response will include citations
        """

        # Convert LLMMessage objects to dict format
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        data = {
            "messages": message_dicts,
            "temperature": temperature,
            "stream": stream
        }

        # Handle model routing
        if routing:
            # Use models array for fallbacks
            if len(routing.models) == 1:
                data["model"] = routing.models[0]
            else:
                data["models"] = routing.models

            # Add provider routing if configured
            if routing.provider:
                provider_dict = routing.provider.to_dict()
                if provider_dict:
                    data["provider"] = provider_dict
        elif model:
            data["model"] = model
        else:
            # Default to auto selection
            data["model"] = "openrouter/auto"

        # For logging, get the primary model
        primary_model = routing.models[0] if routing else (model or "openrouter/auto")

        # Add plugins (e.g., web search)
        if plugins:
            data["plugins"] = [p.to_dict() for p in plugins]

        if max_tokens:
            data["max_tokens"] = max_tokens

        # Add tools if provided in kwargs
        if "tools" in kwargs:
            data["tools"] = kwargs["tools"]

        # Add any additional parameters (excluding tools and routing which we handled)
        excluded_keys = {"tools", "routing"}
        remaining_kwargs = {k: v for k, v in kwargs.items() if k not in excluded_keys}
        data.update(remaining_kwargs)

        # Handle JSON response format if specified
        if kwargs.get("response_format"):
            response_format = kwargs["response_format"]
            format_type = response_format.get("type")

            if format_type == "json_schema":
                # Structured output with JSON schema (OpenAI's newer format)
                if "gpt" in primary_model.lower() or "openai" in primary_model.lower():
                    # OpenAI models support json_schema directly
                    data["response_format"] = response_format
                elif "gemini" in primary_model.lower():
                    # Gemini uses response_schema with the schema nested
                    if "json_schema" in response_format and "schema" in response_format["json_schema"]:
                        data["response_schema"] = response_format["json_schema"]["schema"]
                    else:
                        # Fallback to simple JSON mode
                        data["response_format"] = {"type": "json_object"}
                elif "claude" in primary_model.lower():
                    # Claude doesn't support json_schema yet, fall back to json_object
                    data["response_format"] = {"type": "json_object"}
                elif "grok" in primary_model.lower() or "x-ai" in primary_model.lower():
                    # Grok supports json_schema via OpenAI-compatible format
                    data["response_format"] = response_format
                else:
                    # For other models, try to pass through as-is
                    data["response_format"] = response_format

            elif format_type == "json_object":
                # Simple JSON mode (legacy)
                if "gpt" in primary_model.lower():
                    data["response_format"] = {"type": "json_object"}
                elif "gemini" in primary_model.lower():
                    if "schema" in response_format:
                        data["response_schema"] = response_format["schema"]
                    else:
                        data["response_format"] = {"type": "json_object"}
                elif "claude" in primary_model.lower():
                    data["response_format"] = {"type": "json_object"}
                else:
                    data["response_format"] = response_format

        # DEBUG: Log message sizes to trace token accumulation
        def _content_char_count(content) -> int:
            if isinstance(content, str):
                return len(content)
            if isinstance(content, list):
                return sum(len(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text")
            return 0

        total_chars = sum(_content_char_count(m.content) for m in messages)
        data_json = json.dumps(data)
        logger.info(
            "Creating OpenRouter completion",
            model=primary_model,
            models=routing.models if routing and len(routing.models) > 1 else None,
            provider_sort=routing.provider.sort if routing and routing.provider else None,
            message_count=len(messages),
            total_message_chars=total_chars,
            payload_size=len(data_json),
            temperature=temperature,
        )
        
        try:
            response = await self.request(
                "POST",
                "/chat/completions",
                data=data
            )
            
            response.raise_for_status()
            result = response.json()

            # Debug log the raw response
            logger.debug("OpenRouter raw response", result=result)

            # Extract response content
            message = result["choices"][0]["message"]
            content = message.get("content", "")

            # Log if content is empty
            if not content:
                logger.warning(
                    "OpenRouter returned empty content",
                    model=model,
                    message=message,
                    full_response=result
                )
            tool_calls = message.get("tool_calls")  # Extract tool_calls if present
            annotations = message.get("annotations", [])  # Web search citations
            usage = result.get("usage", {})

            # Store tool_calls in metadata so they can be accessed
            metadata = {
                "id": result.get("id"),
                "created": result.get("created"),
                "provider": result.get("provider", {})
            }
            if tool_calls:
                metadata["tool_calls"] = tool_calls

            # Parse web search citations from annotations
            if annotations:
                citations = []
                for ann in annotations:
                    if ann.get("type") == "url_citation":
                        url_citation = ann.get("url_citation", {})
                        citations.append({
                            "url": url_citation.get("url"),
                            "title": url_citation.get("title"),
                            "start_index": ann.get("start_index"),
                            "end_index": ann.get("end_index")
                        })
                if citations:
                    metadata["citations"] = citations
                    logger.info("Web search returned citations", count=len(citations))
            
            return LLMResponse(
                content=content,
                model=result.get("model", model),
                usage=usage,
                metadata=metadata
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "OpenRouter API error",
                status=e.response.status_code,
                error=e.response.text
            )
            raise
        except Exception as e:
            logger.error("OpenRouter request failed", error=str(e))
            raise
    
    async def create_completion_stream(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Create a streaming completion from messages"""
        
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        data = {
            "model": model,
            "messages": message_dicts,
            "temperature": temperature,
            "stream": True
        }
        
        if max_tokens:
            data["max_tokens"] = max_tokens
        
        data.update(kwargs)
        
        logger.info(
            "Creating streaming OpenRouter completion",
            model=model,
            message_count=len(messages)
        )
        
        try:
            async for line in self._stream_request(
                "POST",
                "/chat/completions",
                data=data
            ):
                if line.startswith("data: "):
                    if line.strip() == "data: [DONE]":
                        break
                    
                    try:
                        chunk = json.loads(line[6:])
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse streaming chunk", line=line)
                        continue
                        
        except Exception as e:
            logger.error("Streaming completion failed", error=str(e))
            raise
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models from OpenRouter"""
        try:
            response = await self.request("GET", "/models")
            response.raise_for_status()
            
            result = response.json()
            models = result.get("data", [])
            
            logger.info(f"Retrieved {len(models)} models from OpenRouter")
            return models
            
        except Exception as e:
            logger.error("Failed to list models", error=str(e))
            raise
    
    async def health_check(self) -> bool:
        """Check if OpenRouter API is accessible"""
        try:
            # Use the models endpoint as a health check
            response = await self.request("GET", "/models")
            return response.status_code == 200
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return False
    
    # LLMClientInterface implementation
    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a completion from messages (LLMClientInterface).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Response dictionary with at least 'choices' field
        """
        # Convert dict messages to LLMMessage objects
        llm_messages = [
            LLMMessage(role=msg["role"], content=msg["content"])
            for msg in messages
        ]
        
        # Call create_completion and convert response to dict format
        response = await self.create_completion(
            messages=llm_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        # Convert LLMResponse to dict format expected by LLMClientInterface
        message_dict = {
            "role": "assistant",
            "content": response.content
        }
        
        # Include tool_calls if present
        if response.metadata and "tool_calls" in response.metadata:
            message_dict["tool_calls"] = response.metadata["tool_calls"]
        
        return {
            "choices": [{
                "message": message_dict
            }],
            "model": response.model,
            "usage": response.usage or {},
            "metadata": response.metadata or {}
        }
    
    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream a completion from messages (LLMClientInterface).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Response chunks as strings
        """
        # Convert dict messages to LLMMessage objects
        llm_messages = [
            LLMMessage(role=msg["role"], content=msg["content"])
            for msg in messages
        ]
        
        # Call create_completion_stream and yield chunks
        async for chunk in self.create_completion_stream(
            messages=llm_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ):
            yield chunk
