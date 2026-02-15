"""Main FastAPI application for Mimic Notification Service"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from src.api.routes import auth, notifications, provider_keys, templates, workflows, logs, delivery, billing, webhooks, analytics
from src.api.routes import gateway_webhooks
from src.api.routes import integrations, providers
from src.database.database import engine, Base
from src.monitoring.sentry_config import init_sentry
from src.monitoring.metrics import router as metrics_router
from src.middleware.rate_limiting_middleware import RateLimitingMiddleware
from src.middleware.auth_middleware import AuthMiddleware
from src.config import settings

logger = structlog.get_logger()

# Initialize Sentry if DSN is provided
init_sentry()

app = FastAPI(
    title="Mimic Notification Service API",
    description="Notification workflow management platform with BYOK support",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Auth middleware (extracts user_id for rate limiting)
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware
app.add_middleware(RateLimitingMiddleware)

# Include routers
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(provider_keys.router, prefix="/api/v1", tags=["provider-keys"])
app.include_router(templates.router, prefix="/api/v1", tags=["templates"])
app.include_router(workflows.router, prefix="/api/v1", tags=["workflows"])
app.include_router(logs.router, prefix="/api/v1", tags=["logs"])
app.include_router(delivery.router, prefix="/api/v1", tags=["delivery"])
app.include_router(billing.router, prefix="/api/v1", tags=["billing"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])

# Webhook Gateway (versioned for future compatibility)
app.include_router(gateway_webhooks.router, prefix="/api/v1", tags=["webhook-gateway"])

# Integration System (INT-001 to INT-021)
app.include_router(integrations.router, prefix="/api/v1", tags=["integrations"])
app.include_router(integrations.gateway_router, prefix="/api/v1", tags=["integration-gateway"])
app.include_router(providers.router, prefix="/api/v1", tags=["providers"])
app.include_router(metrics_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mimic-notification-service"}


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Mimic Notification Service starting up")
    # Avoid touching the configured database at import time so unit tests can
    # override DB dependencies cleanly. In production environments, prefer
    # migrations; in development we can auto-create tables for convenience.
    if settings.APP_ENV != "test":
        Base.metadata.create_all(bind=engine)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Mimic Notification Service shutting down")
