"""Main FastAPI application for inkPass"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
from src.config import settings
from src.database.database import engine, Base
from src.api.routes import (
    auth,
    organizations,
    users,
    groups,
    permissions,
    api_keys,
    plans,
    oauth,
    files,
    templates,
    roles,
    admin_templates,
    internal,
    invitations,
)
from src.middleware.rate_limiting import init_redis
from src.monitoring.metrics import router as metrics_router

logger = structlog.get_logger()

try:
    from src.api.routes import billing  # Optional (requires aios_stripe dependency)
except ImportError:  # pragma: no cover
    billing = None


def setup_dev_permissions():
    """
    Set up development permissions based on environment variables.

    Reads INKPASS_DEV_PERMISSIONS and INKPASS_DEV_USER_EMAIL from config
    and seeds/assigns permissions accordingly.
    """
    if not settings.DEV_PERMISSIONS:
        return

    if settings.APP_ENV not in ("development", "test"):
        logger.warning(
            "DEV_PERMISSIONS is set but APP_ENV is not development/test, skipping",
            app_env=settings.APP_ENV,
        )
        return

    logger.info(
        "Setting up development permissions",
        preset=settings.DEV_PERMISSIONS,
        user_email=settings.DEV_USER_EMAIL,
    )

    from src.database.database import SessionLocal
    from src.database.models import User, Permission, Organization
    from src.services.permission_service import PermissionService

    # Import permission definitions
    try:
        from scripts.seed_all_permissions import (
            TENTACKL_PERMISSIONS,
            MIMIC_PERMISSIONS,
            AIOS_PERMISSIONS,
        )
        ALL_NEW_PERMISSIONS = TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS
    except ImportError:
        logger.warning("Could not import permission definitions from seed script")
        return

    session = SessionLocal()
    try:
        # Find the user
        user = session.query(User).filter(User.email == settings.DEV_USER_EMAIL).first()
        if not user:
            logger.warning("Dev user not found", email=settings.DEV_USER_EMAIL)
            return

        org_id = user.organization_id

        # Get existing permissions
        existing = {
            (p.resource, p.action)
            for p in session.query(Permission).filter(Permission.organization_id == org_id).all()
        }

        # Create missing permissions
        created = 0
        for resource, action in ALL_NEW_PERMISSIONS:
            if (resource, action) not in existing:
                try:
                    PermissionService.create_permission(
                        db=session,
                        organization_id=org_id,
                        resource=resource,
                        action=action,
                    )
                    created += 1
                except Exception as e:
                    logger.warning("Failed to create permission", resource=resource, action=action, error=str(e))
                    session.rollback()

        if created > 0:
            logger.info("Created dev permissions", count=created)

        # Assign all permissions to user based on preset
        # For now, "admin" preset means all permissions
        if settings.DEV_PERMISSIONS == "admin":
            all_perms = session.query(Permission).filter(Permission.organization_id == org_id).all()
            assigned = 0
            for perm in all_perms:
                if perm not in user.user_permissions:
                    user.user_permissions.append(perm)
                    assigned += 1
            if assigned > 0:
                session.commit()
                logger.info("Assigned dev permissions to user", user=settings.DEV_USER_EMAIL, count=assigned)

    except Exception as e:
        logger.error("Failed to set up dev permissions", error=str(e))
        session.rollback()
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("inkPass service starting up")
    # Initialize Redis for rate limiting
    init_redis()
    # Create database tables
    Base.metadata.create_all(bind=engine)
    # Register default OAuth providers
    from src.services.oauth.provider_factory import register_default_providers
    register_default_providers()
    logger.info("OAuth providers registered")
    # Set up development permissions if configured
    setup_dev_permissions()

    yield

    # Shutdown
    logger.info("inkPass service shutting down")


app = FastAPI(
    title="inkPass API",
    description="Authentication and Authorization Service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(oauth.router, prefix="/api/v1", tags=["oauth"])
app.include_router(organizations.router, prefix="/api/v1/organizations", tags=["organizations"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(groups.router, prefix="/api/v1/groups", tags=["groups"])
app.include_router(permissions.router, prefix="/api/v1/permissions", tags=["permissions"])
app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["api-keys"])
app.include_router(plans.router, prefix="/api/v1/plans", tags=["plans"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
if billing is not None:
    app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
else:
    logger.info("Billing routes disabled (optional dependency missing)")
app.include_router(templates.router, prefix="/api/v1/templates", tags=["templates"])
app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
app.include_router(admin_templates.router, prefix="/api/v1/admin/templates", tags=["admin-templates"])
app.include_router(internal.router, prefix="/api/v1/internal", tags=["internal"])
app.include_router(invitations.router, prefix="/api/v1/invitations", tags=["invitations"])
app.include_router(metrics_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "inkpass"}
