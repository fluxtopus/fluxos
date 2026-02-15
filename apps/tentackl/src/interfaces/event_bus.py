"""Event Bus interfaces for Tentackl's event-driven architecture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import uuid


class EventSourceType(Enum):
    """Types of event sources."""
    WEBHOOK = "webhook"
    WEBSOCKET = "websocket"
    MESSAGE_QUEUE = "message_queue"
    INTERNAL = "internal"
    USER_INPUT = "user_input"


@dataclass
class Event:
    """Represents an event in the system."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    source_type: EventSourceType = EventSourceType.INTERNAL
    event_type: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None


@dataclass
class EventSubscription:
    """Represents a subscription to events."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subscriber_id: str = ""  # Agent or component ID
    event_pattern: str = ""  # Pattern to match events
    filter: Optional[Dict[str, Any]] = None
    transform: Optional[Dict[str, Any]] = None
    callbacks: List['Callback'] = field(default_factory=list)
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CallbackTrigger:
    """Defines when a callback should be triggered."""
    event_type: str
    condition: Optional[str] = None  # JSONPath or expression


@dataclass
class CallbackAction:
    """Defines what action to take when callback is triggered."""
    action_type: str  # spawn_agent, update_state, call_api, etc.
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallbackConstraints:
    """Constraints for callback execution."""
    rate_limit_calls: Optional[int] = None
    rate_limit_window: Optional[str] = None  # e.g., "1h", "10m"
    max_parallel: Optional[int] = None
    timeout_seconds: Optional[int] = None


@dataclass
class Callback:
    """Represents a callback action for an event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger: CallbackTrigger = field(default_factory=CallbackTrigger)
    actions: List[CallbackAction] = field(default_factory=list)
    constraints: CallbackConstraints = field(default_factory=CallbackConstraints)


@dataclass
class CallbackResult:
    """Result of executing a callback."""
    callback_id: str
    success: bool
    execution_time_ms: float
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class EventSource:
    """Configuration for an event source."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_type: EventSourceType = EventSourceType.INTERNAL
    config: Dict[str, Any] = field(default_factory=dict)
    authentication: Optional[Dict[str, Any]] = None
    active: bool = True


@dataclass
class RawEvent:
    """Raw event data before validation and normalization."""
    source_id: str
    data: Any
    headers: Optional[Dict[str, str]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class EventBusInterface(ABC):
    """Core Event Bus interface for publishing and subscribing to events."""
    
    @abstractmethod
    async def publish(self, event: Event) -> bool:
        """
        Publish an event to the bus.
        
        Args:
            event: The event to publish
            
        Returns:
            bool: True if event was published successfully
        """
        pass
    
    @abstractmethod
    async def subscribe(self, subscription: EventSubscription) -> str:
        """
        Register an event subscription.
        
        Args:
            subscription: The subscription configuration
            
        Returns:
            str: Subscription ID
        """
        pass
    
    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove an event subscription.
        
        Args:
            subscription_id: The subscription to remove
            
        Returns:
            bool: True if unsubscribed successfully
        """
        pass
    
    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> Optional[EventSubscription]:
        """
        Get a subscription by ID.
        
        Args:
            subscription_id: The subscription ID
            
        Returns:
            Optional[EventSubscription]: The subscription if found
        """
        pass
    
    @abstractmethod
    async def list_subscriptions(self, subscriber_id: Optional[str] = None) -> List[EventSubscription]:
        """
        List all subscriptions, optionally filtered by subscriber.
        
        Args:
            subscriber_id: Optional filter by subscriber
            
        Returns:
            List[EventSubscription]: List of subscriptions
        """
        pass


class EventGatewayInterface(ABC):
    """Interface for receiving and validating external events."""
    
    @abstractmethod
    async def register_source(self, source: EventSource) -> bool:
        """
        Register a new event source.
        
        Args:
            source: Event source configuration
            
        Returns:
            bool: True if registered successfully
        """
        pass
    
    @abstractmethod
    async def validate_event(self, event: RawEvent) -> Event:
        """
        Validate and normalize an incoming event.
        
        Args:
            event: Raw event data
            
        Returns:
            Event: Validated and normalized event
            
        Raises:
            EventValidationError: If event is invalid
        """
        pass
    
    @abstractmethod
    async def authenticate_source(self, source_id: str, credentials: Dict[str, Any]) -> bool:
        """
        Authenticate an event source.
        
        Args:
            source_id: The source identifier
            credentials: Authentication credentials
            
        Returns:
            bool: True if authenticated successfully
        """
        pass


class CallbackEngineInterface(ABC):
    """Interface for executing event callbacks."""
    
    @abstractmethod
    async def execute_callback(self, callback: Callback, event: Event) -> CallbackResult:
        """
        Execute a callback action.
        
        Args:
            callback: The callback to execute
            event: The triggering event
            
        Returns:
            CallbackResult: Result of callback execution
        """
        pass
    
    @abstractmethod
    async def validate_constraints(self, callback: Callback) -> bool:
        """
        Check if callback constraints allow execution.
        
        Args:
            callback: The callback to validate
            
        Returns:
            bool: True if callback can be executed
        """
        pass
    
    @abstractmethod
    async def get_callback_metrics(self, callback_id: str) -> Dict[str, Any]:
        """
        Get execution metrics for a callback.
        
        Args:
            callback_id: The callback identifier
            
        Returns:
            Dict[str, Any]: Callback execution metrics
        """
        pass


class EventValidationError(Exception):
    """Raised when event validation fails."""
    pass


class EventPublishError(Exception):
    """Raised when event publishing fails."""
    pass


class SubscriptionError(Exception):
    """Raised when subscription operations fail."""
    pass