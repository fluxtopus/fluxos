"""
Conversation Tracking Capability Implementation

Provides conversation tracking for agents, capturing:
- LLM prompts and responses
- State changes
- Errors
- Inter-agent messages

Extracted from StatefulAgent._start_conversation, _end_conversation, etc.
"""

import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import structlog

from src.capabilities.protocols import ConversationTrackingCapability, ConversationInfo
from src.database.conversation_store import ConversationStore, ConversationTrigger
from src.database.conversation_interceptor import (
    ConversationInterceptor,
    current_conversation_id,
    current_agent_id,
)
from src.database.models import ConversationStatus, TriggerType
from src.interfaces.database import Database
from src.interfaces.llm import LLMInterface, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


@dataclass
class InterceptionResult:
    """Result from intercepting an LLM call."""
    message_id: Optional[str] = None


class ConversationAwareLLMWrapper:
    """
    Wrapper for LLM clients that intercepts calls for conversation tracking.

    This is the same wrapper from llm_agent.py, moved here for capability use.
    """

    def __init__(
        self,
        client: LLMInterface,
        tracking: 'ConversationTrackingImpl',
        agent_id: str,
        default_model: str,
        agent_ref: Any = None
    ):
        self.client = client
        self.tracking = tracking
        self.agent_id = agent_id
        self.default_model = default_model
        self.agent_ref = agent_ref

    async def create_completion(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        """Create completion with conversation tracking."""
        start_time = time.time()

        # Extract the prompt (last user message)
        prompt = messages[-1].content if messages else ""
        model = kwargs.get("model", self.default_model)

        # Check if context needs to be set from parent agent
        if self.agent_ref and hasattr(self.agent_ref, 'current_conversation_id'):
            conv_id = self.agent_ref.current_conversation_id
            if conv_id and not current_conversation_id.get():
                current_conversation_id.set(conv_id)
                current_agent_id.set(self.agent_id)

        # Intercept outgoing call
        kwargs_copy = kwargs.copy()
        kwargs_copy.pop('model', None)

        interception = await self.tracking.intercept_llm_call(
            agent_id=self.agent_id,
            prompt=prompt,
            model=model,
            **kwargs_copy
        )

        try:
            # Make actual LLM call
            response = await self.client.create_completion(messages, **kwargs)

            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)

            # Intercept response
            await self.tracking.intercept_llm_response(
                agent_id=self.agent_id,
                response=response,
                latency_ms=latency_ms,
                parent_message_id=interception.message_id if interception else None
            )

            return response

        except Exception as e:
            # Intercept error
            await self.tracking.intercept_error(
                self.agent_id,
                e,
                {"messages": [{"role": m.role, "content": m.content} for m in messages], "kwargs": kwargs}
            )
            raise

    async def create_completion_stream(self, messages: List[LLMMessage], **kwargs):
        """Pass through streaming (not tracked yet)."""
        async for chunk in self.client.create_completion_stream(messages, **kwargs):
            yield chunk

    async def list_models(self) -> List[Dict[str, Any]]:
        """Pass through model listing."""
        return await self.client.list_models()

    async def health_check(self) -> bool:
        """Pass through health check."""
        return await self.client.health_check()


class ConversationTrackingImpl:
    """
    Implementation of conversation tracking capability.

    Wraps ConversationStore and ConversationInterceptor to provide
    a clean interface for tracking agent conversations.
    """

    def __init__(self, database: Optional[Database] = None):
        """
        Initialize conversation tracking.

        Args:
            database: Optional database instance. Creates one if not provided.
        """
        self._db = database
        self._owns_db = database is None  # Track if we created the DB
        self._store: Optional[ConversationStore] = None
        self._interceptor: Optional[ConversationInterceptor] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the conversation tracking system."""
        if self._initialized:
            return

        try:
            # Create database if not provided
            if self._db is None:
                self._db = Database()
                await self._db.connect()

            # Create store and interceptor
            self._store = ConversationStore(self._db)
            self._interceptor = ConversationInterceptor(self._store)

            self._initialized = True
            logger.info("Conversation tracking initialized")

        except Exception as e:
            logger.error("Failed to initialize conversation tracking", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown and cleanup resources."""
        if self._owns_db and self._db:
            try:
                await self._db.disconnect()
            except Exception as e:
                logger.error("Error disconnecting database", error=str(e))

        self._store = None
        self._interceptor = None
        self._initialized = False
        logger.info("Conversation tracking shutdown complete")

    async def start_conversation(
        self,
        workflow_id: str,
        agent_id: str,
        trigger_type: str = "API_CALL",
        trigger_source: str = "direct",
        trigger_details: Optional[Dict[str, Any]] = None,
        parent_conversation_id: Optional[str] = None
    ) -> str:
        """Start tracking a new conversation."""
        if not self._store:
            raise RuntimeError("Conversation tracking not initialized")

        try:
            # Convert string trigger type to enum
            try:
                tt = TriggerType[trigger_type.upper()]
            except KeyError:
                tt = TriggerType.API_CALL

            trigger = ConversationTrigger(
                type=tt,
                source=trigger_source,
                details=trigger_details or {},
                conversation_source="workflow"
            )

            conversation = await self._store.start_conversation(
                workflow_id=workflow_id,
                root_agent_id=agent_id,
                trigger=trigger,
                parent_conversation_id=parent_conversation_id
            )

            conversation_id = str(conversation.id)

            # Set context
            self.set_context(conversation_id, agent_id)

            logger.info(
                "Started conversation",
                conversation_id=conversation_id,
                agent_id=agent_id,
                workflow_id=workflow_id
            )

            return conversation_id

        except Exception as e:
            logger.error("Failed to start conversation", error=str(e))
            raise

    async def end_conversation(self, conversation_id: str, status: str) -> bool:
        """End a conversation with the given status."""
        if not self._store:
            return False

        try:
            # Convert string status to enum
            try:
                cs = ConversationStatus[status.upper()]
            except KeyError:
                cs = ConversationStatus.COMPLETED

            success = await self._store.end_conversation(conversation_id, cs)

            if success:
                logger.info(
                    "Ended conversation",
                    conversation_id=conversation_id,
                    status=status
                )

            return success

        except Exception as e:
            logger.error("Failed to end conversation", error=str(e))
            return False

    async def intercept_llm_call(
        self,
        agent_id: str,
        prompt: str,
        model: str,
        **kwargs
    ) -> InterceptionResult:
        """Intercept an outgoing LLM call for logging."""
        if not self._interceptor:
            return InterceptionResult()

        try:
            result = await self._interceptor.intercept_llm_call(
                agent_id=agent_id,
                prompt=prompt,
                model=model,
                **kwargs
            )
            return InterceptionResult(
                message_id=result.message_id if hasattr(result, 'message_id') else None
            )
        except Exception as e:
            logger.warning("Failed to intercept LLM call", error=str(e))
            return InterceptionResult()

    async def intercept_llm_response(
        self,
        agent_id: str,
        response: Any,
        latency_ms: int,
        parent_message_id: Optional[str] = None
    ) -> None:
        """Log an LLM response."""
        if not self._interceptor:
            return

        try:
            await self._interceptor.intercept_llm_response(
                agent_id=agent_id,
                response=response,
                latency_ms=latency_ms,
                parent_message_id=parent_message_id
            )
        except Exception as e:
            logger.warning("Failed to intercept LLM response", error=str(e))

    async def intercept_state_update(
        self,
        agent_id: str,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any],
        changed_fields: List[str]
    ) -> None:
        """Log a state change."""
        if not self._interceptor:
            return

        try:
            await self._interceptor.intercept_state_update(
                agent_id=agent_id,
                old_state=old_state,
                new_state=new_state,
                changed_fields=changed_fields
            )
        except Exception as e:
            logger.warning("Failed to intercept state update", error=str(e))

    async def intercept_error(
        self,
        agent_id: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an error."""
        if not self._interceptor:
            return

        try:
            await self._interceptor.intercept_error(
                agent_id=agent_id,
                error=error,
                context=context or {}
            )
        except Exception as e:
            logger.warning("Failed to intercept error", error=str(e))

    def wrap_llm_client(self, client: Any, agent_id: str, model: str, agent_ref: Any = None) -> Any:
        """Wrap an LLM client to automatically intercept calls."""
        return ConversationAwareLLMWrapper(
            client=client,
            tracking=self,
            agent_id=agent_id,
            default_model=model,
            agent_ref=agent_ref
        )

    def set_context(self, conversation_id: str, agent_id: str) -> None:
        """Set the current conversation context for this thread/task."""
        if self._interceptor:
            self._interceptor.set_context(conversation_id, agent_id)

        # Also set context vars directly
        current_conversation_id.set(conversation_id)
        current_agent_id.set(agent_id)

    def get_current_conversation_id(self) -> Optional[str]:
        """Get the current conversation ID from context."""
        return current_conversation_id.get()

    @property
    def store(self) -> Optional[ConversationStore]:
        """Access the underlying conversation store."""
        return self._store

    @property
    def interceptor(self) -> Optional[ConversationInterceptor]:
        """Access the underlying interceptor."""
        return self._interceptor
