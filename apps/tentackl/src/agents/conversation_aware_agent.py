# REVIEW:
# - Conversation tracking is tightly coupled to agent execution; consider isolating
#   persistence/logging concerns to simplify testing and reuse.
"""Base class for agents with conversation tracking capabilities."""

from typing import Any, Dict, Optional
from abc import abstractmethod
import uuid
import structlog

from src.agents.stateful_agent import StatefulAgent, StatefulAgentConfig
from src.database.conversation_store import ConversationStore, ConversationTrigger
from src.database.conversation_interceptor import ConversationInterceptor, current_conversation_id, current_agent_id
from src.database.models import ConversationStatus, TriggerType
from src.interfaces.database import Database

logger = structlog.get_logger()


class ConversationAwareAgent(StatefulAgent):
    """
    Base agent class with integrated conversation tracking.
    
    Automatically captures all agent communications including:
    - LLM calls and responses
    - Tool invocations
    - Inter-agent messages
    - State updates
    - Errors
    """
    
    def __init__(self, config: StatefulAgentConfig, enable_conversation_tracking: bool = True):
        """
        Initialize conversation-aware agent.
        
        Args:
            config: Agent configuration
            enable_conversation_tracking: Whether to enable conversation tracking
        """
        super().__init__(config)
        
        self.enable_conversation_tracking = enable_conversation_tracking
        self.conversation_store: Optional[ConversationStore] = None
        self.conversation_interceptor: Optional[ConversationInterceptor] = None
        self.current_conversation_id: Optional[str] = None
        # Retains the most recently created conversation id even after completion
        self.last_conversation_id: Optional[str] = None
        self._db: Optional[Database] = None
        
        # Workflow integration removed (tasks + flux only)
        
    async def initialize(
        self,
        context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        execution_node_id: Optional[str] = None
    ) -> None:
        """Initialize agent with conversation tracking."""
        await super().initialize(context_id, tree_id, execution_node_id)
        
        # Conversation tracking is initialized in StatefulAgent.initialize
    
    async def cleanup(self) -> None:
        """Cleanup resources including database connections."""
        try:
            if self._db:
                await self._db.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting database: {e}")
    
    async def shutdown(self) -> None:
        """Shutdown agent and cleanup resources."""
        try:
            # Cleanup conversation resources
            await self.cleanup()
            # Call parent shutdown
            await super().shutdown()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    async def start_conversation(
        self,
        workflow_id: str,
        trigger_type: TriggerType,
        trigger_source: str,
        trigger_details: Dict[str, Any],
        parent_conversation_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Start a new conversation for this agent's execution.
        
        Args:
            workflow_id: ID of the workflow
            trigger_type: Type of trigger that started the conversation
            trigger_source: Source of the trigger
            trigger_details: Additional trigger details
            parent_conversation_id: Optional parent conversation for sub-agents
            
        Returns:
            Conversation ID if tracking is enabled, None otherwise
        """
        if not self.enable_conversation_tracking or not self.conversation_store:
            return None
        
        try:
            trigger = ConversationTrigger(
                type=trigger_type,
                source=trigger_source,
                details=trigger_details,
                conversation_source="workflow"  # Mark as workflow/agent-generated conversation
            )

            conversation = await self.conversation_store.start_conversation(
                workflow_id=workflow_id,
                root_agent_id=self.agent_id,
                trigger=trigger,
                parent_conversation_id=parent_conversation_id
            )
            
            self.current_conversation_id = str(conversation.id)
            self.last_conversation_id = self.current_conversation_id
            
            # Set context for interceptor
            self.conversation_interceptor.set_context(
                self.current_conversation_id,
                self.agent_id
            )
            
            # Also set the context vars directly for child operations
            current_conversation_id.set(self.current_conversation_id)
            current_agent_id.set(self.agent_id)
            
            logger.info(
                "Started conversation",
                conversation_id=self.current_conversation_id,
                agent_id=self.agent_id,
                workflow_id=workflow_id
            )
            
            return self.current_conversation_id
            
        except Exception as e:
            logger.error(f"Failed to start conversation: {e}")
            return None
    
    async def end_conversation(self, status: ConversationStatus) -> bool:
        """
        End the current conversation.
        
        Args:
            status: Final status of the conversation
            
        Returns:
            True if successful, False otherwise
        """
        if not self.current_conversation_id or not self.conversation_store:
            return False
        
        try:
            success = await self.conversation_store.end_conversation(
                self.current_conversation_id,
                status
            )
            
            if success:
                logger.info(
                    "Ended conversation",
                    conversation_id=self.current_conversation_id,
                    status=status.value
                )
                # Keep current_conversation_id available for callers after execute
                # Context variables are cleared by interceptor when appropriate
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to end conversation: {e}")
            return False
    
    async def execute(self, task: Dict[str, Any]) -> Any:
        """
        Execute task with automatic conversation tracking.
        
        If no conversation is active, starts a new one.
        """
        # Always start a new conversation per execute when tracking is enabled
        if self.enable_conversation_tracking:
            # Generate a workflow_id if not provided
            workflow_id = task.get("workflow_id")
            if not workflow_id:
                workflow_id = str(uuid.uuid4())
                task["workflow_id"] = workflow_id
            
            await self.start_conversation(
                workflow_id=workflow_id,
                trigger_type=TriggerType.API_CALL,
                trigger_source="direct_execution",
                trigger_details=task,
                parent_conversation_id=task.get("parent_conversation_id")
            )
        
        # Indicate to downstream LLM paths that errors should propagate up when using execute
        setattr(self, "_raise_on_llm_error", True)
        try:
            # Execute the actual task
            result = await super().execute(task)
            
            # Check if result indicates an error
            if isinstance(result, dict) and result.get("status") == "error":
                # End conversation as failed if result indicates error
                if self.current_conversation_id:
                    await self.end_conversation(ConversationStatus.FAILED)
            else:
                # End conversation on success
                if self.current_conversation_id:
                    await self.end_conversation(ConversationStatus.COMPLETED)
            
            return result
            
        except Exception as e:
            # Log error to conversation
            if self.conversation_interceptor:
                await self.conversation_interceptor.intercept_error(
                    self.agent_id,
                    e,
                    {"task": task}
                )
            
            # End conversation as failed
            if self.current_conversation_id:
                await self.end_conversation(ConversationStatus.FAILED)
            
            raise
        finally:
            try:
                delattr(self, "_raise_on_llm_error")
            except Exception:
                pass
    
    def get_conversation_interceptor(self) -> Optional[ConversationInterceptor]:
        """Get the conversation interceptor for manual message logging."""
        return self.conversation_interceptor
    
    async def log_state_change(self, old_state: Dict[str, Any], new_state: Dict[str, Any]):
        """Log state changes to conversation."""
        if not self.conversation_interceptor:
            return
        
        # Find changed fields
        changed_fields = []
        for key in set(old_state.keys()) | set(new_state.keys()):
            if old_state.get(key) != new_state.get(key):
                changed_fields.append(key)
        
        if changed_fields:
            await self.conversation_interceptor.intercept_state_update(
                self.agent_id,
                old_state,
                new_state,
                changed_fields
            )
    
    @abstractmethod
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """
        Execute the agent's stateful logic.
        
        Subclasses must implement this method.
        """
        pass
    
