from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, AsyncIterator
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class LLMMessage:
    """Standard message format for LLM interactions.

    ``content`` may be a plain string or a list of content parts for
    multimodal messages (e.g. text + inline images).  OpenRouter natively
    accepts both formats.
    """
    role: str  # "user", "assistant", "system"
    content: Union[str, List[Dict[str, Any]]]


@dataclass
class LLMResponse:
    """Standard response format from LLM"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMInterface(ABC):
    """Abstract interface for LLM providers"""
    
    @abstractmethod
    async def create_completion(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """Create a completion from messages"""
        pass
    
    @abstractmethod
    async def create_completion_stream(
        self,
        messages: List[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Create a streaming completion from messages"""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM service is available"""
        pass


class LLMClientInterface(ABC):
    """Interface for LLM client implementations"""
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a completion from messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Response dictionary with at least 'choices' field
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream a completion from messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Response chunks as strings
        """
        pass