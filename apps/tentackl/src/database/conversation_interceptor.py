# REVIEW: Interceptor relies on global ContextVar state and auto-creates
# REVIEW: conversations when missing, which can hide upstream bugs. It also
# REVIEW: stores raw response payloads in DB, potentially large/sensitive.
"""Interceptor for capturing agent communications."""

from typing import Any, Dict, Optional, List
from datetime import datetime
import time
import json
import structlog
from contextvars import ContextVar

from src.database.conversation_store import (
    ConversationStore, MessageData, MessageContent, MessageMetadata, Cost, ConversationTrigger
)
from src.database.models import MessageType, MessageDirection, TriggerType
import uuid

logger = structlog.get_logger()

# Context variable to track current conversation
current_conversation_id: ContextVar[Optional[str]] = ContextVar('current_conversation_id', default=None)
current_agent_id: ContextVar[Optional[str]] = ContextVar('current_agent_id', default=None)


class MessageInterception:
    """Result of message interception."""
    def __init__(self, message_id: str, intercepted_at: datetime):
        self.message_id = message_id
        self.intercepted_at = intercepted_at


class ConversationInterceptor:
    """Intercepts and stores agent communications."""
    
    def __init__(self, conversation_store: ConversationStore):
        self.store = conversation_store
    
    def set_context(self, conversation_id: str, agent_id: str):
        """Set the current conversation context."""
        current_conversation_id.set(conversation_id)
        current_agent_id.set(agent_id)
    
    async def intercept_llm_call(
        self,
        agent_id: str,
        prompt: str,
        model: str,
        **kwargs
    ) -> MessageInterception:
        """Intercept outgoing LLM call."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for LLM call")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Ensure backing conversation exists when context was set manually
        try:
            convo = await self.store.get_conversation(conversation_id, include_messages=False)
        except Exception:
            convo = None
        if not convo:
            try:
                wf_id = str(uuid.uuid4())
                trigger = ConversationTrigger(
                    type=TriggerType.API_CALL,
                    source="manual_context",
                    details={"note": "autocreated by interceptor"}
                )
                created = await self.store.start_conversation(
                    workflow_id=wf_id,
                    root_agent_id=agent_id or current_agent_id.get() or "unknown",
                    trigger=trigger,
                    parent_conversation_id=None
                )
                # Update context to persisted conversation id
                conversation_id = str(created.id)
                current_conversation_id.set(conversation_id)
            except Exception as e:
                logger.error("Failed to create conversation for manual context", error=str(e))
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.LLM_PROMPT,
            direction=MessageDirection.OUTBOUND,
            content=MessageContent(
                role="user",
                text=prompt,
                data={"model": model, "parameters": kwargs}
            ),
            metadata=MessageMetadata(
                model=model,
                temperature=kwargs.get('temperature'),
                tokens=None  # Will be updated in response
            )
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted LLM call",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    model=model)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_llm_response(
        self,
        agent_id: str,
        response: Any,
        latency_ms: int,
        parent_message_id: Optional[str] = None
    ) -> MessageInterception:
        """Intercept incoming LLM response."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for LLM response")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Extract response data based on provider format
        response_text = None
        tokens = None
        cost = None
        model = None
        
        # Prefer OpenAI-like format detection first to avoid Mock attribute traps
        if hasattr(response, 'choices') and response.choices:
            # OpenAI format
            response_text = response.choices[0].message.content
            # Coerce to string if mock/object slipped in
            if not isinstance(response_text, str):
                try:
                    # Common cases: objects with 'text' or 'content' attributes
                    if hasattr(response_text, 'text') and isinstance(response_text.text, str):
                        response_text = response_text.text
                    elif hasattr(response_text, 'content') and isinstance(response_text.content, str):
                        response_text = response_text.content
                    else:
                        response_text = str(response_text)
                except Exception:
                    response_text = str(response_text)
            if hasattr(response, 'usage'):
                tokens = {
                    'prompt': getattr(response.usage, 'prompt_tokens', None),
                    'completion': getattr(response.usage, 'completion_tokens', None),
                    'total': getattr(response.usage, 'total_tokens', None)
                }
            model = getattr(response, 'model', None)
        
        # Check if it's an LLMResponse-like object with direct content/model
        elif hasattr(response, 'content') and hasattr(response, 'model'):
            response_text = response.content
            if not isinstance(response_text, str):
                try:
                    response_text = str(response_text)
                except Exception:
                    response_text = None
            model = response.model
            usage = getattr(response, 'usage', None)
            tokens = None
            if usage is not None:
                # Support both attr-object and dict usage
                try:
                    tokens = {
                        'prompt': getattr(usage, 'prompt_tokens'),
                        'completion': getattr(usage, 'completion_tokens'),
                        'total': getattr(usage, 'total_tokens')
                    }
                except Exception:
                    if isinstance(usage, dict):
                        tokens = {
                            'prompt': usage.get('prompt_tokens'),
                            'completion': usage.get('completion_tokens'),
                            'total': usage.get('total_tokens')
                        }
                    else:
                        tokens = None
            model = getattr(response, 'model', None)
        
        elif isinstance(response, dict):
            # Generic format
            response_text = response.get('content') or response.get('text') or str(response)
            tokens = response.get('usage')
            model = response.get('model')
            
            # Calculate cost if available
            if 'cost' in response:
                cost = Cost(amount=response['cost'])
        
        else:
            # Fallback
            response_text = str(response)
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.LLM_RESPONSE,
            direction=MessageDirection.INBOUND,
            content=MessageContent(
                role="assistant",
                text=response_text,
                data={"raw_response": response if isinstance(response, dict) else {"content": str(response), "type": type(response).__name__}}
            ),
            metadata=MessageMetadata(
                model=model,
                tokens=tokens,
                latency_ms=latency_ms
            ),
            cost=cost,
            parent_message_id=parent_message_id
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted LLM response",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    latency_ms=latency_ms)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> MessageInterception:
        """Intercept tool invocation."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for tool call")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.TOOL_CALL,
            direction=MessageDirection.OUTBOUND,
            content=MessageContent(
                role="tool",
                text=f"Calling tool: {tool_name}",
                data={"tool": tool_name, "parameters": parameters},
                tool_calls=[{
                    "tool": tool_name,
                    "parameters": parameters,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            ),
            metadata=MessageMetadata()
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted tool call",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    tool_name=tool_name)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_tool_response(
        self,
        agent_id: str,
        tool_name: str,
        response: Any,
        latency_ms: int,
        parent_message_id: Optional[str] = None,
        error: Optional[str] = None
    ) -> MessageInterception:
        """Intercept tool response."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for tool response")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.TOOL_RESPONSE,
            direction=MessageDirection.INBOUND,
            content=MessageContent(
                role="tool",
                text=f"Tool response from: {tool_name}",
                data={
                    "tool": tool_name,
                    "response": response if isinstance(response, (dict, list)) else str(response)
                }
            ),
            metadata=MessageMetadata(
                latency_ms=latency_ms,
                error=error
            ),
            parent_message_id=parent_message_id
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted tool response",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    has_error=bool(error))
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_inter_agent_message(
        self,
        from_agent_id: str,
        to_agent_id: str,
        message: Dict[str, Any]
    ) -> MessageInterception:
        """Intercept inter-agent communication."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for inter-agent message")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Create message data
        message_data = MessageData(
            agent_id=from_agent_id,
            message_type=MessageType.INTER_AGENT,
            direction=MessageDirection.INTERNAL,
            content=MessageContent(
                role="agent",
                text=f"Message from {from_agent_id} to {to_agent_id}",
                data={
                    "from_agent": from_agent_id,
                    "to_agent": to_agent_id,
                    "message": message
                }
            ),
            metadata=MessageMetadata()
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted inter-agent message",
                    conversation_id=conversation_id,
                    from_agent=from_agent_id,
                    to_agent=to_agent_id)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_state_update(
        self,
        agent_id: str,
        state_before: Dict[str, Any],
        state_after: Dict[str, Any],
        changed_fields: List[str]
    ) -> MessageInterception:
        """Intercept state changes."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for state update")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.STATE_UPDATE,
            direction=MessageDirection.INTERNAL,
            content=MessageContent(
                role="system",
                text=f"State updated: {', '.join(changed_fields)}",
                data={
                    "state_before": state_before,
                    "state_after": state_after,
                    "changed_fields": changed_fields
                }
            ),
            metadata=MessageMetadata()
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.debug("Intercepted state update",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    changed_fields=changed_fields)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    async def intercept_error(
        self,
        agent_id: str,
        error: Exception,
        context: Dict[str, Any]
    ) -> MessageInterception:
        """Intercept errors."""
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            logger.warning("No conversation context set for error")
            return MessageInterception("no-context", datetime.utcnow())
        
        # Create message data
        message_data = MessageData(
            agent_id=agent_id or current_agent_id.get() or "unknown",
            message_type=MessageType.ERROR,
            direction=MessageDirection.INTERNAL,
            content=MessageContent(
                role="system",
                text=f"Error: {type(error).__name__}: {str(error)}",
                data={
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "context": context,
                    "traceback": None  # Could add traceback if needed
                }
            ),
            metadata=MessageMetadata(
                error=str(error)
            )
        )
        
        # Store the message
        await self.store.add_message(conversation_id, message_data)
        
        logger.error("Intercepted error",
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    error_type=type(error).__name__)
        
        return MessageInterception(message_data.id, datetime.utcnow())
    
    def wrap_llm_client(self, llm_client: Any) -> Any:
        """Wrap an LLM client to intercept calls."""
        # This would return a wrapped version of the LLM client
        # that automatically calls the interceptor methods
        # Implementation depends on the specific LLM client interface
        return LLMClientWrapper(llm_client, self)


class LLMClientWrapper:
    """Wrapper for LLM clients to intercept calls."""
    
    def __init__(self, client: Any, interceptor: ConversationInterceptor):
        self.client = client
        self.interceptor = interceptor
        self.agent_id = current_agent_id.get() or "unknown"
    
    async def __call__(self, prompt: str, **kwargs) -> Any:
        """Intercept LLM calls."""
        # Record start time
        start_time = time.time()
        
        # Intercept the outgoing call
        prompt_interception = await self.interceptor.intercept_llm_call(
            self.agent_id,
            prompt,
            kwargs.get('model', 'unknown'),
            **kwargs
        )
        
        try:
            # Make the actual call
            response = await self.client(prompt, **kwargs)
            
            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Intercept the response
            await self.interceptor.intercept_llm_response(
                self.agent_id,
                response,
                latency_ms,
                parent_message_id=prompt_interception.message_id
            )
            
            return response
            
        except Exception as e:
            # Intercept errors
            await self.interceptor.intercept_error(
                self.agent_id,
                e,
                {"prompt": prompt, "kwargs": kwargs}
            )
            raise
