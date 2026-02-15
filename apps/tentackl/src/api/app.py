# REVIEW:
# - Large global singleton surface + module-level dependency injection across routers; hard to test and easy to drift.
# - setup_api_routes/setup_api_routes_sync/update_route_dependencies repeat wiring + router lists; inconsistencies are likely.
# - Lifespan owns DB, event bus, workers, monitoring, audit, plugins; consider decomposing into smaller lifecycle components.
"""FastAPI application for Tentackl tasks, inbox, integrations, and agent management."""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from src.api.cors_config import configure_cors
import logging
from typing import Optional

from src.database.conversation_store import ConversationStore
from src.interfaces.database import Database
from src.event_bus import RedisEventBus
from src.event_bus.event_gateway import EventGateway

logger = logging.getLogger(__name__)

# Global instances
conversation_store: Optional[ConversationStore] = None
db: Optional[Database] = None
event_bus: Optional[RedisEventBus] = None
event_gateway: Optional[EventGateway] = None


def get_database() -> Database:
    """Get the database instance."""
    if not db:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global conversation_store, db, event_bus, event_gateway

    event_trigger_worker = None
    task_trigger_registry = None

    # SEC-003: Validate JWT/secret keys at startup
    from src.core.config import validate_secrets
    validate_secrets()

    # SEC-010: Validate and warn about DEV_AUTH_BYPASS configuration
    from src.core.config import validate_dev_auth_bypass
    validate_dev_auth_bypass()

    # Initialize database
    try:
        db = Database()
        await db.connect()
        conversation_store = ConversationStore(db)
        logger.info("Database and conversation store initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        db = None
        conversation_store = None

    # Initialize Event Bus (lightweight)
    event_bus = RedisEventBus()
    await event_bus.start()

    # Initialize Event Gateway
    if db:
        event_gateway = EventGateway(database=db)
        await event_gateway.initialize()
        logger.info("Event Gateway initialized")
    else:
        event_gateway = None
        logger.warning("Event Gateway not initialized due to missing database")

    # Update router dependencies
    await update_route_dependencies(
        database=db,
        conversation_store=conversation_store,
        event_bus=event_bus,
        event_gateway=event_gateway,
    )

    # Initialize TaskTriggerRegistry for event-driven task execution
    try:
        from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry
        task_trigger_registry = TaskTriggerRegistry()
        await task_trigger_registry.initialize()
        trigger_count = await task_trigger_registry.load_all_triggers()
        logger.info("TaskTriggerRegistry initialized", triggers_loaded=trigger_count)
    except Exception as e:
        logger.error("Failed to initialize TaskTriggerRegistry", error=str(e))
        task_trigger_registry = None

    # Start Event Trigger Worker (handles webhook -> task execution)
    try:
        from src.application.triggers import TriggerUseCases
        from src.infrastructure.triggers.trigger_registry_adapter import TriggerRegistryAdapter
        from src.workers.event_trigger_worker import EventTriggerWorker

        trigger_use_cases = None
        if task_trigger_registry:
            trigger_use_cases = TriggerUseCases(
                registry=TriggerRegistryAdapter(task_trigger_registry)
            )

        event_trigger_worker = EventTriggerWorker(
            event_bus,
            trigger_use_cases=trigger_use_cases,
        )
        await event_trigger_worker.start()
        logger.info("EventTriggerWorker started")
    except Exception as e:
        logger.error(f"Failed to start EventTriggerWorker: {e}", exc_info=True)

    # Register additional plugins (HTTP, etc.)
    try:
        import src.plugins.http_plugin  # noqa: F401
        logger.info("HTTP plugin registered")
    except Exception as e:
        logger.warning(f"Failed to register HTTP plugin: {e}")

    # Start resource monitoring
    from src.monitoring.resource_monitor import start_resource_monitoring
    await start_resource_monitoring(interval=10)
    logger.info("Resource monitoring started")

    # Start error monitoring
    from src.monitoring.error_monitor import start_error_monitoring
    error_monitor = await start_error_monitoring(check_interval=10)
    logger.info("Error monitoring started")

    # Start alert manager
    from src.monitoring.alert_manager import start_alert_manager
    alert_manager = await start_alert_manager()

    # Connect error monitor to alert manager
    error_monitor.add_alert_callback(alert_manager.handle_alert)
    logger.info("Alert management started")

    # Start audit logging
    from src.audit import get_audit_logger, AuditEventType
    audit_logger = await get_audit_logger()

    # Log system startup
    await audit_logger.log_workflow_event(
        workflow_id="system",
        event_type=AuditEventType.SYSTEM_STARTUP,
        description="Tentackl API started",
        details={
            "version": "1.0.0",
            "environment": "development"
        }
    )
    logger.info("Audit logging started")

    logger.info("API services initialized")

    yield

    # Cleanup
    # Stop resource monitoring
    from src.monitoring.resource_monitor import stop_resource_monitoring
    await stop_resource_monitoring()
    logger.info("Resource monitoring stopped")

    # Stop error monitoring
    from src.monitoring.error_monitor import stop_error_monitoring
    await stop_error_monitoring()
    logger.info("Error monitoring stopped")

    # Stop alert manager
    from src.monitoring.alert_manager import stop_alert_manager
    await stop_alert_manager()
    logger.info("Alert management stopped")

    # Stop audit logging
    from src.audit import stop_audit_logger, get_audit_logger, AuditEventType
    audit_logger = await get_audit_logger()

    # Log system shutdown
    await audit_logger.log_workflow_event(
        workflow_id="system",
        event_type=AuditEventType.SYSTEM_SHUTDOWN,
        description="Tentackl API shutting down",
        details={}
    )

    await stop_audit_logger()
    logger.info("Audit logging stopped")

    # Stop event trigger worker
    try:
        if event_trigger_worker:
            await event_trigger_worker.stop()
    except Exception as e:
        logger.error(f"Error stopping EventTriggerWorker: {e}")

    # Cleanup task trigger registry
    if task_trigger_registry:
        try:
            await task_trigger_registry.cleanup()
        except Exception as e:
            logger.error("Error cleaning up TaskTriggerRegistry", error=str(e))

    # Stop event gateway
    if event_gateway:
        await event_gateway.cleanup()

    # Stop event bus
    if event_bus:
        await event_bus.stop()

    # Cleanup database connection
    if db:
        try:
            await db.disconnect()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")

    logger.info("API services shut down")


async def update_route_dependencies(**dependencies):
    """
    Update dependencies in already-registered routes with real services.

    Args:
        **dependencies: Real services from main.py lifespan
    """
    # Update the module-level db variable so get_database() works
    global db

    # Extract dependencies
    db = dependencies.get('database')
    conversation_store = dependencies.get('conversation_store')
    event_bus = dependencies.get('event_bus')
    event_gateway = dependencies.get('event_gateway')

    # Update event bus router dependencies
    from src.api.routers import event_bus as event_bus_module
    event_bus_module.event_bus = event_bus
    event_bus_module.conversation_store = conversation_store
    event_bus_module.event_bus_use_cases = None

    # Update external events router dependencies
    from src.api.routers import external_events as external_events_module
    external_events_module.event_bus = event_bus
    external_events_module.event_gateway = event_gateway
    external_events_module.database = db

    # Update agents router dependencies
    from src.api.routers import agents as agents_module
    agents_module.conversation_store = conversation_store
    agents_module.database = db

    # Update preferences router dependencies
    from src.api.routers import preferences as preferences_module
    preferences_module.database = db

    # Update workspace router dependencies
    from src.api.routers import workspace as workspace_module
    workspace_module.database = db

    # Update allowed hosts router dependencies
    from src.api.routers import allowed_hosts as allowed_hosts_module
    allowed_hosts_module.database = db

    # Update automations router dependencies
    from src.api.routers import automations as automations_module
    automations_module.database = db

    # Update capabilities router dependencies
    from src.api.routers import capabilities as capabilities_module
    capabilities_module.database = db

    # Update inbox router dependencies
    from src.api.routers import inbox as inbox_module
    from src.infrastructure.inbox.use_case_factory import reset_inbox_service
    inbox_module.conversation_store = conversation_store
    # Reset cached service so it picks up new conversation_store
    reset_inbox_service()

    # Update memories router dependencies
    from src.api.routers import memories as memories_module
    from src.infrastructure.memory import build_memory_use_cases
    memories_module.database = db
    if db:
        memories_module.memory_use_cases = build_memory_use_cases(db)

    # Update integrations router dependencies (optional)
    try:
        from src.api.routers import integrations as integrations_module
        from src.application.integrations import (
            IntegrationEventStreamUseCases,
            IntegrationUseCases,
        )
        from src.infrastructure.integrations import (
            MimicIntegrationAdapter,
            RedisIntegrationEventStreamAdapter,
        )
        integrations_module.integration_use_cases = IntegrationUseCases(
            integration_ops=MimicIntegrationAdapter()
        )
        integrations_module.integration_event_stream_use_cases = IntegrationEventStreamUseCases(
            event_stream_ops=RedisIntegrationEventStreamAdapter()
        )
    except ImportError:
        pass

    # Update integrations OAuth router dependencies (optional)
    try:
        from src.api.routers import integrations_oauth as integrations_oauth_module
        from src.application.integrations import IntegrationOAuthUseCases
        from src.infrastructure.integrations import MimicIntegrationAdapter, OAuthRegistryAdapter
        from src.infrastructure.integrations.oauth_state_adapter import IntegrationOAuthStateAdapter
        integrations_oauth_module.oauth_use_cases = IntegrationOAuthUseCases(
            integration_ops=MimicIntegrationAdapter(),
            oauth_registry=OAuthRegistryAdapter(),
            oauth_state=IntegrationOAuthStateAdapter(),
        )
    except ImportError:
        pass

    logger.info("Route dependencies updated with real services")


def setup_api_routes_sync(app: FastAPI, **dependencies):
    """
    Setup all API routes with standardized /api prefixes and proper dependencies (synchronous version).

    Args:
        app: FastAPI application instance
        **dependencies: Core services from main.py (database, conversation_store, event_bus, etc.)
    """
    # Extract dependencies
    db = dependencies.get('database')
    conversation_store = dependencies.get('conversation_store')
    event_bus = dependencies.get('event_bus')
    event_gateway = dependencies.get('event_gateway')

    # Inject dependencies into router modules
    from src.api.routers import event_bus as event_bus_module
    from src.api.routers import external_events as external_events_module
    from src.api.routers import agents as agents_module
    from src.api.routers import auth_management as auth_management_module
    from src.api.routers import organizations_proxy as organizations_proxy_module
    from src.api.routers import metrics as metrics_module
    from src.api.routers import monitoring as monitoring_module
    from src.api.routers import audit as audit_module

    # Event bus router dependencies
    event_bus_module.event_bus = event_bus
    event_bus_module.conversation_store = conversation_store
    event_bus_module.event_bus_use_cases = None

    # External events router dependencies
    external_events_module.event_bus = event_bus
    external_events_module.event_gateway = event_gateway
    external_events_module.database = db

    # Agents router dependencies
    agents_module.conversation_store = conversation_store
    agents_module.database = db

    # Add health endpoint under /api/health
    @app.get("/api/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "tentackl"}

    # Register core API routers (they already have /api prefix)
    app.include_router(event_bus_module.router, tags=["event-bus"])
    app.include_router(external_events_module.router, tags=["external-events"])
    app.include_router(agents_module.router, tags=["agents"])
    app.include_router(auth_management_module.router, tags=["authentication"])
    app.include_router(organizations_proxy_module.router, tags=["organizations"])
    app.include_router(metrics_module.router, tags=["metrics"])
    app.include_router(monitoring_module.router, tags=["monitoring"])
    app.include_router(audit_module.router, tags=["audit"])

    # Register evaluations router (prompt quality gate)
    from src.api.routers import evaluations as evaluations_module
    app.include_router(evaluations_module.router, tags=["evaluations"])
    logger.info("Prompt evaluation endpoints registered")

    # Register allowed hosts router
    from src.api.routers import allowed_hosts as allowed_hosts_module
    allowed_hosts_module.database = db
    app.include_router(allowed_hosts_module.router, tags=["allowed-hosts"])
    logger.info("Allowed hosts endpoints registered")

    # Register tasks router (NL goal + execution plan system)
    from src.api.routers import tasks as tasks_module
    app.include_router(tasks_module.router, tags=["tasks"])
    logger.info("Task endpoints registered")

    # Register checkpoints router
    from src.api.routers import checkpoints as checkpoints_module
    app.include_router(checkpoints_module.router, tags=["checkpoints"])
    logger.info("Checkpoint endpoints registered")

    # Register preferences router
    from src.api.routers import preferences as preferences_module
    preferences_module.database = db
    app.include_router(preferences_module.router, tags=["preferences"])
    logger.info("Preference endpoints registered")

    # Register workspace router (flexible object storage)
    from src.api.routers import workspace as workspace_module
    workspace_module.database = db
    app.include_router(workspace_module.router, tags=["workspace"])
    logger.info("Workspace endpoints registered")

    # Register agent storage router (admin-only)
    from src.api.routers import agent_storage as agent_storage_module
    app.include_router(agent_storage_module.router, tags=["admin", "agent-storage"])
    logger.info("Agent storage endpoints registered")

    # Register Google OAuth router
    from src.api.routers.oauth import google_router
    app.include_router(google_router, tags=["google-oauth"])
    logger.info("Google OAuth endpoints registered")

    # Register platform webhooks router (support automation, etc.)
    from src.api.routers import platform_webhooks as platform_webhooks_module
    app.include_router(platform_webhooks_module.router, tags=["platform-webhooks"])
    logger.info("Platform webhook endpoints registered")

    # Register automations router (scheduled tasks)
    from src.api.routers import automations as automations_module
    automations_module.database = db
    app.include_router(automations_module.router, tags=["automations"])
    logger.info("Automation endpoints registered")

    # Register capabilities router (unified capability system)
    from src.api.routers import capabilities as capabilities_module
    capabilities_module.database = db
    app.include_router(capabilities_module.router, tags=["capabilities"])
    logger.info("Capabilities endpoints registered")

    # Register catalog router (plugins/agents discovery)
    from src.api.routers import catalog as catalog_module
    app.include_router(catalog_module.router, tags=["catalog"])
    logger.info("Catalog endpoints registered")

    # Register integrations router (INT-018: proxies to Mimic) — optional
    try:
        from src.api.routers import integrations as integrations_module
        from src.application.integrations import (
            IntegrationEventStreamUseCases,
            IntegrationUseCases,
        )
        from src.infrastructure.integrations import (
            MimicIntegrationAdapter,
            RedisIntegrationEventStreamAdapter,
        )
        integrations_module.integration_use_cases = IntegrationUseCases(
            integration_ops=MimicIntegrationAdapter()
        )
        integrations_module.integration_event_stream_use_cases = IntegrationEventStreamUseCases(
            event_stream_ops=RedisIntegrationEventStreamAdapter()
        )
        app.include_router(integrations_module.router, tags=["integrations"])
        app.include_router(integrations_module.internal_router, tags=["internal"])
        logger.info("Integrations endpoints registered (including internal event receiver)")
    except ImportError:
        logger.info("Integrations router not available (Mimic SDK not installed)")

    # Register integrations OAuth router (generic OAuth 2.0 connect flow) — optional
    try:
        from src.api.routers import integrations_oauth as integrations_oauth_module
        from src.application.integrations import IntegrationOAuthUseCases
        from src.infrastructure.integrations import MimicIntegrationAdapter, OAuthRegistryAdapter
        from src.infrastructure.integrations.oauth_state_adapter import IntegrationOAuthStateAdapter
        integrations_oauth_module.oauth_use_cases = IntegrationOAuthUseCases(
            integration_ops=MimicIntegrationAdapter(),
            oauth_registry=OAuthRegistryAdapter(),
            oauth_state=IntegrationOAuthStateAdapter(),
        )
        app.include_router(integrations_oauth_module.router, tags=["integrations-oauth"])
        logger.info("Integrations OAuth endpoints registered")
    except ImportError:
        logger.info("Integrations OAuth router not available (Mimic SDK not installed)")

    # Register inbox router (Agent Inbox)
    from src.api.routers import inbox as inbox_module
    inbox_module.conversation_store = conversation_store
    app.include_router(inbox_module.router, tags=["inbox"])
    logger.info("Inbox endpoints registered")

    # Register memories router (Memory Service)
    from src.api.routers import memories as memories_module
    from src.infrastructure.memory import build_memory_use_cases
    memories_module.database = db
    if db:
        memories_module.memory_use_cases = build_memory_use_cases(db)
    app.include_router(memories_module.router, tags=["memories"])
    logger.info("Memory endpoints registered")

    # Register triggers router (Task Triggers)
    from src.api.routers import triggers as triggers_module
    app.include_router(triggers_module.router, tags=["triggers"])
    logger.info("Triggers endpoints registered")

    # Register conditional routers
    try:
        from .configurable_agent_endpoints import router as configurable_agent_router
        app.include_router(configurable_agent_router, tags=["configurable-agent"])
        logger.info("ConfigurableAgent endpoints registered")
    except ImportError as e:
        logger.warning(f"Could not import ConfigurableAgent endpoints: {e}")

    logger.info("All API routes registered with /api prefix")


async def setup_api_routes(app: FastAPI, **dependencies):
    """
    Setup all API routes with standardized /api prefixes and proper dependencies.

    Args:
        app: FastAPI application instance
        **dependencies: Core services from main.py (database, conversation_store, event_bus, etc.)
    """
    setup_api_routes_sync(app, **dependencies)


app = FastAPI(
    title="Tentackl API",
    description="Tasks, inbox (Flux), integrations, and agent management for Tentackl",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
configure_cors(app)

# Configure rate limiting middleware
from src.api.rate_limiter import RateLimitMiddleware
app.add_middleware(
    RateLimitMiddleware,
    default_max_requests=100,
    default_window_seconds=60,
    exclude_paths={"/health", "/metrics", "/docs", "/openapi.json", "/api/health"},
    strict_paths={
        # Evaluation endpoints are expensive (LLM calls) - stricter limits
        "/api/evaluations": (20, 60),
    }
)

# Note: All API routes are now registered via setup_api_routes() function
# This app instance is used by main.py for delegation
