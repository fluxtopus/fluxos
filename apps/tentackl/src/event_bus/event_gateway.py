"""Event Gateway implementation for receiving and validating external events."""

import asyncio
import json
import hashlib
import hmac
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass
import uuid

from src.interfaces.event_bus import (
    EventGatewayInterface, EventSource, RawEvent, Event,
    EventSourceType, EventValidationError
)
from src.interfaces.database import Database
from src.database.external_event_models import ExternalPublisher
from src.core.config import settings
import redis.asyncio as redis

logger = structlog.get_logger()


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    max_requests: int
    window_seconds: int
    

class EventGateway(EventGatewayInterface):
    """
    Event Gateway for receiving and validating external events.
    
    This component:
    - Authenticates event sources
    - Validates incoming events
    - Applies rate limiting
    - Normalizes events for the Event Bus
    """
    
    def __init__(
        self,
        database: Optional[Database] = None,
        redis_url: Optional[str] = None,
        key_prefix: str = "tentackl:gateway"
    ):
        self._db = database
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis_client: Optional[redis.Redis] = None
        self._key_prefix = key_prefix
        self._sources: Dict[str, EventSource] = {}
        self._rate_limits: Dict[str, RateLimitConfig] = {}
        self._allowed_domains: Set[str] = set()
        self._initialized = False
        
    async def initialize(self):
        """Initialize the gateway."""
        if self._initialized:
            return
            
        # Initialize Redis connection
        self._redis_client = await redis.from_url(
            self._redis_url,
            decode_responses=True
        )
        
        # Initialize database if needed
        if not self._db:
            self._db = Database()
            await self._db.connect()
            
        # Load configuration
        await self._load_configuration()
        
        self._initialized = True
        logger.info("Event Gateway initialized")
        
    async def _load_configuration(self):
        """Load gateway configuration from settings."""
        # Load allowed domains
        if hasattr(settings, 'EVENT_GATEWAY_ALLOWED_DOMAINS'):
            self._allowed_domains = set(settings.EVENT_GATEWAY_ALLOWED_DOMAINS)
        
        # Default rate limits
        self._rate_limits['global'] = RateLimitConfig(
            max_requests=1000,
            window_seconds=60
        )
        self._rate_limits['per_source'] = RateLimitConfig(
            max_requests=100,
            window_seconds=60
        )
    
    async def register_source(self, source: EventSource) -> bool:
        """Register a new event source."""
        try:
            await self._ensure_initialized()
            
            # Validate source configuration
            if not source.name or not source.id:
                raise ValueError("Source must have name and id")
            
            # Store source configuration
            source_key = f"{self._key_prefix}:source:{source.id}"
            source_data = {
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type.value,
                "config": json.dumps(source.config),
                "authentication": json.dumps(source.authentication) if source.authentication else "",
                "active": str(source.active),
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self._redis_client.hset(
                source_key,
                mapping=source_data
            )
            
            # Cache in memory
            self._sources[source.id] = source
            
            # Set up rate limiting for this source
            if source.config.get('rate_limit'):
                self._rate_limits[source.id] = RateLimitConfig(
                    max_requests=source.config['rate_limit'].get('max_requests', 100),
                    window_seconds=source.config['rate_limit'].get('window_seconds', 60)
                )
            
            logger.info(
                f"Registered event source: {source.name} (id={source.id}, type={source.source_type.value})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register source: {e}")
            return False
    
    async def validate_event(self, raw_event: RawEvent) -> Event:
        """Validate and normalize an incoming event."""
        await self._ensure_initialized()
        
        # Get source configuration
        source = await self._get_source(raw_event.source_id)
        if not source:
            raise EventValidationError(f"Unknown source: {raw_event.source_id}")
        
        if not source.active:
            raise EventValidationError(f"Source {raw_event.source_id} is not active")
        
        # Check rate limits
        if not await self._check_rate_limit(raw_event.source_id):
            raise EventValidationError(f"Rate limit exceeded for source {raw_event.source_id}")
        
        # Validate event structure based on source type
        validated_data = await self._validate_event_data(source, raw_event)
        
        # Create normalized event
        event = Event(
            source=source.name,
            source_type=source.source_type,
            event_type=validated_data.get('event_type', 'external.event'),
            data=validated_data.get('data', {}),
            metadata={
                'source_id': source.id,
                'raw_headers': raw_event.headers,
                'received_at': raw_event.timestamp.isoformat()
            }
        )
        
        # Add workflow/agent context if provided
        if 'workflow_id' in validated_data:
            event.workflow_id = validated_data['workflow_id']
        if 'agent_id' in validated_data:
            event.agent_id = validated_data['agent_id']
        
        logger.info(
            f"Validated event - id: {event.id}, source: {source.id}, type: {event.event_type}"
        )
        
        return event
    
    async def authenticate_source(self, source_id: str, credentials: Dict[str, Any]) -> bool:
        """Authenticate an event source."""
        await self._ensure_initialized()
        
        logger.info(f"Authenticating source {source_id} with credentials: {list(credentials.keys())}")
        
        # Get source configuration
        source = await self._get_source(source_id)
        if not source:
            logger.warning(f"Source {source_id} not found")
            return False
        if not source.authentication:
            logger.warning(f"Source {source_id} has no authentication configured")
            return False
        
        auth_type = source.authentication.get('type')
        logger.info(f"Source {source_id} uses {auth_type} authentication")
        
        if auth_type == 'api_key':
            return await self._authenticate_api_key(source, credentials)
        elif auth_type == 'bearer_token':
            return await self._authenticate_bearer_token(source, credentials)
        elif auth_type == 'hmac':
            return await self._authenticate_hmac(source, credentials)
        elif auth_type == 'oauth2':
            return await self._authenticate_oauth2(source, credentials)
        else:
            logger.warning(f"Unknown authentication type: {auth_type}")
            return False
    
    async def _authenticate_api_key(self, source: EventSource, credentials: Dict[str, Any]) -> bool:
        """Authenticate using API key."""
        provided_key = credentials.get('api_key', '')
        expected_key = source.authentication.get('api_key', '')
        
        logger.info(f"API key auth - provided key: {provided_key[:10]}... (truncated)")
        logger.info(f"Source type: {source.source_type}")
        
        # For external publishers, check database
        if source.source_type == EventSourceType.WEBHOOK:
            async with self._db.get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(ExternalPublisher).where(
                        ExternalPublisher.api_key_hash == self._hash_api_key(provided_key),
                        ExternalPublisher.is_active == True
                    )
                )
                publisher = result.scalar_one_or_none()
                
                if publisher:
                    # Update last used timestamp
                    publisher.last_used_at = datetime.utcnow()
                    await session.commit()
                    return True
                    
        # Simple comparison for internal sources
        return provided_key == expected_key
    
    async def _authenticate_bearer_token(self, source: EventSource, credentials: Dict[str, Any]) -> bool:
        """Authenticate using bearer token."""
        provided_token = credentials.get('bearer_token', '')
        expected_token = source.authentication.get('bearer_token', '')
        
        # Could integrate with OAuth provider here
        return provided_token == expected_token
    
    async def _authenticate_hmac(self, source: EventSource, credentials: Dict[str, Any]) -> bool:
        """Authenticate using HMAC signature."""
        provided_signature = credentials.get('signature', '')
        payload = credentials.get('payload', '')
        secret = source.authentication.get('secret', '')
        
        if not all([provided_signature, payload, secret]):
            return False
        
        # Calculate expected signature
        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (constant time)
        return hmac.compare_digest(provided_signature, expected_signature)
    
    async def _authenticate_oauth2(self, source: EventSource, credentials: Dict[str, Any]) -> bool:
        """Authenticate using OAuth2."""
        # Would integrate with OAuth2 provider
        # For now, return False
        return False
    
    async def _get_source(self, source_id: str) -> Optional[EventSource]:
        """Get source configuration."""
        # Check memory cache
        if source_id in self._sources:
            return self._sources[source_id]
        
        # Load from Redis
        source_key = f"{self._key_prefix}:source:{source_id}"
        source_data = await self._redis_client.hgetall(source_key)
        
        if not source_data:
            return None
        
        # Reconstruct source
        source = EventSource(
            id=source_data['id'],
            name=source_data['name'],
            source_type=EventSourceType(source_data['source_type']),
            config=json.loads(source_data['config']) if source_data.get('config') else {},
            authentication=json.loads(source_data['authentication']) if source_data.get('authentication') else None,
            active=source_data.get('active', 'True') == 'True'
        )
        
        # Cache in memory
        self._sources[source_id] = source
        
        return source
    
    async def _check_rate_limit(self, source_id: str) -> bool:
        """Check if source is within rate limits."""
        # Check global rate limit
        if not await self._check_single_rate_limit('global', self._rate_limits['global']):
            return False
        
        # Check per-source rate limit
        limit_config = self._rate_limits.get(source_id, self._rate_limits['per_source'])
        if not await self._check_single_rate_limit(source_id, limit_config):
            return False
        
        return True
    
    async def _check_single_rate_limit(self, key: str, config: RateLimitConfig) -> bool:
        """Check a single rate limit."""
        rate_key = f"{self._key_prefix}:rate:{key}"
        current_time = int(datetime.utcnow().timestamp())
        window_start = current_time - config.window_seconds
        
        # Use Redis sorted set for sliding window
        pipe = self._redis_client.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(rate_key, 0, window_start)
        
        # Count current entries
        pipe.zcard(rate_key)
        
        # Add current request
        pipe.zadd(rate_key, {str(uuid.uuid4()): current_time})
        
        # Set expiry
        pipe.expire(rate_key, config.window_seconds + 60)
        
        results = await pipe.execute()
        current_count = results[1]
        
        # Check if within limit
        return current_count < config.max_requests
    
    async def _validate_event_data(self, source: EventSource, raw_event: RawEvent) -> Dict[str, Any]:
        """Validate event data based on source type."""
        if source.source_type == EventSourceType.WEBHOOK:
            return await self._validate_webhook_data(source, raw_event)
        elif source.source_type == EventSourceType.WEBSOCKET:
            return await self._validate_websocket_data(source, raw_event)
        elif source.source_type == EventSourceType.MESSAGE_QUEUE:
            return await self._validate_message_queue_data(source, raw_event)
        else:
            # Default validation
            if isinstance(raw_event.data, dict):
                return raw_event.data
            else:
                return {'data': raw_event.data}
    
    async def _validate_webhook_data(self, source: EventSource, raw_event: RawEvent) -> Dict[str, Any]:
        """Validate webhook event data."""
        # Parse JSON body
        if isinstance(raw_event.data, str):
            try:
                data = json.loads(raw_event.data)
            except json.JSONDecodeError:
                raise EventValidationError("Invalid JSON in webhook body")
        elif isinstance(raw_event.data, dict):
            data = raw_event.data
        else:
            raise EventValidationError("Webhook data must be JSON")
        
        # Validate required fields from source config
        required_fields = source.config.get('required_fields', [])
        for field in required_fields:
            if field not in data:
                raise EventValidationError(f"Missing required field: {field}")
        
        # Apply schema validation if configured
        if 'schema' in source.config:
            # Would use jsonschema or similar here
            pass
        
        return data
    
    async def _validate_websocket_data(self, source: EventSource, raw_event: RawEvent) -> Dict[str, Any]:
        """Validate WebSocket event data."""
        # Similar to webhook but may have different format
        return await self._validate_webhook_data(source, raw_event)
    
    async def _validate_message_queue_data(self, source: EventSource, raw_event: RawEvent) -> Dict[str, Any]:
        """Validate message queue event data."""
        # Message queues might have envelope format
        if isinstance(raw_event.data, dict):
            return raw_event.data
        else:
            return {'message': raw_event.data}
    
    def _hash_api_key(self, api_key: str) -> str:
        """Hash an API key for storage/comparison."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    async def _ensure_initialized(self):
        """Ensure gateway is initialized."""
        if not self._initialized:
            await self.initialize()
    
    async def cleanup(self):
        """Cleanup resources."""
        if self._redis_client:
            await self._redis_client.aclose()
        self._initialized = False
        logger.info("Event Gateway cleaned up")
