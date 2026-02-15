from fastapi import FastAPI
from contextlib import asynccontextmanager
import structlog
from redis import asyncio as aioredis
from src.core.config import settings
from src.interfaces.database import Database
from src.mcp.registry import MCPRegistry
from src.agents.registry import register_default_agents
from src.api.cors_config import configure_cors
from src.integrations.posthog_client import posthog_client

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Tentackl application", env=settings.APP_ENV)
    logger.info("PostHog analytics", enabled=posthog_client.enabled)

    # Initialize database
    db = Database()
    await db.connect()

    # Initialize workspace plugin with database
    from src.plugins.workspace_plugin import set_database
    set_database(db)
    logger.info("Workspace plugin initialized with database")

    # Initialize workspace CSV plugin with database
    from src.plugins.workspace_csv_plugin import set_database as set_workspace_csv_db
    set_workspace_csv_db(db)

    # Sync in-memory plugins to capability DB for discoverability
    from src.capabilities.plugin_sync import sync_plugins_to_db
    synced = await sync_plugins_to_db(db)
    logger.info("Plugin capabilities synced to DB", count=synced)

    # Register agents
    register_default_agents()

    # Initialize MCP
    await MCPRegistry.initialize()

    # Conversation store
    from src.database.conversation_store import ConversationStore
    conversation_store = ConversationStore(db)

    # Initialize Event Bus and Event Gateway
    from src.event_bus import RedisEventBus
    from src.event_bus.event_gateway import EventGateway

    event_bus = RedisEventBus()
    await event_bus.start()

    event_gateway = EventGateway(database=db)
    await event_gateway.initialize()
    logger.info("Event Gateway initialized")

    # Initialize TaskTriggerRegistry for event-driven task execution
    from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry
    task_trigger_registry = TaskTriggerRegistry()
    await task_trigger_registry.initialize()
    trigger_count = await task_trigger_registry.load_all_triggers()
    logger.info("TaskTriggerRegistry initialized", triggers_loaded=trigger_count)

    # Start Event Trigger Worker (singleton across all Gunicorn workers)
    # Uses Redis distributed lock to ensure only one worker runs across all processes.
    # Note: EventTriggerWorker also has per-event deduplication, so multiple workers
    # won't cause duplicate processing - this is an optimization to reduce CPU usage.
    event_trigger_worker = None
    event_trigger_lock = None
    event_trigger_redis = None
    try:
        event_trigger_redis = aioredis.from_url(event_bus.redis_url, decode_responses=True)
        lock_key = f"{event_bus.key_prefix}:locks:event_trigger_worker"
        event_trigger_lock = event_trigger_redis.lock(
            lock_key,
            timeout=60,  # Short timeout for faster recovery on crash
            blocking=False,
        )
        acquired = await event_trigger_lock.acquire(blocking=False)
        if acquired:
            from src.application.triggers import TriggerUseCases
            from src.infrastructure.triggers.trigger_registry_adapter import TriggerRegistryAdapter
            from src.workers.event_trigger_worker import EventTriggerWorker

            trigger_use_cases = TriggerUseCases(
                registry=TriggerRegistryAdapter(task_trigger_registry)
            )
            event_trigger_worker = EventTriggerWorker(
                event_bus,
                trigger_use_cases=trigger_use_cases,
            )
            await event_trigger_worker.start()
            logger.info("EventTriggerWorker started as singleton", lock_key=lock_key)
        else:
            logger.info("EventTriggerWorker already running in another process", lock_key=lock_key)
    except Exception as e:
        # Graceful degradation: log error but don't crash the app
        # Event processing will be handled by another worker or on next restart
        logger.error(
            "Failed to start EventTriggerWorker - event processing may be delayed",
            error=str(e),
            exc_info=True
        )
        # Clean up lock if we acquired it before failure
        if event_trigger_lock:
            try:
                await event_trigger_lock.release()
            except Exception:
                pass
        event_trigger_lock = None
        event_trigger_worker = None

    logger.info("Core services initialized")

    # Update dependencies in already-registered routes with real services
    from src.api.app import update_route_dependencies
    await update_route_dependencies(
        database=db,
        conversation_store=conversation_store,
        event_bus=event_bus,
        event_gateway=event_gateway,
    )

    yield

    # Cleanup
    # Stop event trigger worker and release lock
    try:
        if event_trigger_worker:
            await event_trigger_worker.stop()
            logger.info("EventTriggerWorker stopped")
    except Exception as e:
        logger.error(f"Error stopping EventTriggerWorker: {e}")
    finally:
        # Release the distributed lock
        if event_trigger_lock:
            try:
                await event_trigger_lock.release()
                logger.info("Released EventTriggerWorker lock")
            except Exception as e:
                logger.warning("Failed to release EventTriggerWorker lock", error=str(e))
        # Close the Redis client used for locking
        if event_trigger_redis:
            try:
                await event_trigger_redis.close()
            except Exception:
                pass

    # Cleanup task trigger registry
    if task_trigger_registry:
        await task_trigger_registry.cleanup()
        logger.info("TaskTriggerRegistry cleaned up")

    # Stop event gateway
    if event_gateway:
        await event_gateway.cleanup()
        logger.info("Event Gateway stopped")

    # Stop event bus
    if event_bus:
        await event_bus.stop()
        logger.info("Event bus stopped")

    await db.disconnect()
    posthog_client.shutdown()
    logger.info("Shutting down Tentackl application")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    # Configure OpenAPI security schemes for Swagger UI
    openapi_tags=[
        {
            "name": "authentication",
            "description": "Authentication and authorization endpoints",
        },
        {
            "name": "tasks",
            "description": "Task creation and execution endpoints",
        },
        {
            "name": "inbox",
            "description": "Flux inbox endpoints",
        },
        {
            "name": "integrations",
            "description": "Integration and trigger endpoints",
        },
    ],
)

# Configure CORS
configure_cors(app)

# Setup API routes immediately - this is the single source of truth
from unittest.mock import AsyncMock, MagicMock

def setup_routes_synchronously():
    """Setup API routes with minimal dependencies for immediate availability."""
    from src.api.app import setup_api_routes_sync
    
    # Create minimal mock dependencies for immediate setup
    conversation_store_mock = AsyncMock()
    conversation_store_mock.search_conversations.return_value = []

    setup_api_routes_sync(
        app=app,
        database=MagicMock(),
        conversation_store=conversation_store_mock,
        event_bus=MagicMock(),
        event_gateway=MagicMock(),
    )

# Run the setup synchronously
try:
    setup_routes_synchronously()
    logger.info("API routes set up immediately")
except Exception as e:
    logger.error(f"Failed to setup API routes immediately: {e}")


# Configure OpenAPI security schemes for Swagger UI
def setup_openapi_security(app: FastAPI):
    """Configure OpenAPI security schemes so they appear in Swagger UI."""
    from src.api.auth_middleware import API_KEY_HEADER
    
    # Override openapi_schema to add security schemes
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        from fastapi.openapi.utils import get_openapi
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT Bearer token authentication. Get a token from /api/auth/token"
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": API_KEY_HEADER,
                "description": "API Key authentication. Include your API key in the X-API-Key header"
            }
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi


# Setup OpenAPI security after routes are registered
setup_openapi_security(app)
