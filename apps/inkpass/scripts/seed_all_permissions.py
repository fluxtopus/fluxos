#!/usr/bin/env python3
"""
Seed all platform permissions for development.

Creates all Tentackl, Mimic, and platform permissions in the database.
This script is designed to be idempotent - running it multiple times
will not create duplicate permissions.

Usage:
    # Seed for platform org (admin@fluxtopus.com)
    docker compose exec inkpass python scripts/seed_all_permissions.py

    # Seed for a specific organization
    docker compose exec inkpass python scripts/seed_all_permissions.py --org-id <org_id>

    # Dry run (show what would be created)
    docker compose exec inkpass python scripts/seed_all_permissions.py --dry-run
"""

import argparse
import os
import sys
from typing import Set, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database.database import SessionLocal
from src.database.models import Permission, Organization, User
from src.services.permission_service import PermissionService

# Type alias
PermissionTuple = Tuple[str, str]


# =============================================================================
# PERMISSION DEFINITIONS (synced with inkpass_sdk.dev_permissions)
# =============================================================================

TENTACKL_PERMISSIONS: Set[PermissionTuple] = {
    # Workflows
    ("workflows", "view"),
    ("workflows", "create"),
    ("workflows", "update"),
    ("workflows", "execute"),
    ("workflows", "delete"),
    ("workflows", "control"),
    # Workflow Specs
    ("workflow_specs", "view"),
    ("workflow_specs", "create"),
    ("workflow_specs", "update"),
    ("workflow_specs", "delete"),
    ("workflow_specs", "share"),
    # Workflow Runs
    ("workflow_runs", "view"),
    ("workflow_runs", "execute"),
    # Agents
    ("agents", "view"),
    ("agents", "create"),
    ("agents", "update"),
    ("agents", "delete"),
    ("agents", "execute"),
    ("agents", "search"),
    # Tasks
    ("tasks", "view"),
    ("tasks", "create"),
    ("tasks", "update"),
    ("tasks", "delete"),
    ("tasks", "execute"),
    ("tasks", "assign"),
    # Checkpoints
    ("checkpoints", "view"),
    ("checkpoints", "resolve"),
    # Preferences
    ("preferences", "view"),
    ("preferences", "create"),
    ("preferences", "delete"),
    # Events
    ("events", "view"),
    ("events", "publish"),
    ("events", "subscribe"),
    # Webhooks
    ("webhooks", "view"),
    ("webhooks", "create"),
    ("webhooks", "delete"),
    # Workspace
    ("workspace", "view"),
    ("workspace", "create"),
    ("workspace", "update"),
    ("workspace", "delete"),
    ("workspace", "query"),
    # Workspace Types
    ("workspace_types", "view"),
    ("workspace_types", "create"),
    # Audit
    ("audit", "view"),
    # Metrics
    ("metrics", "view"),
    ("metrics", "admin"),
}

MIMIC_PERMISSIONS: Set[PermissionTuple] = {
    # Notifications
    ("notifications", "send"),
    ("notifications", "view"),
    # Templates
    ("templates", "view"),
    ("templates", "create"),
    ("templates", "update"),
    ("templates", "delete"),
    # Mimic Workflows
    ("mimic_workflows", "view"),
    ("mimic_workflows", "create"),
    ("mimic_workflows", "update"),
    ("mimic_workflows", "delete"),
    ("mimic_workflows", "trigger"),
    # Provider Keys
    ("provider_keys", "view"),
    ("provider_keys", "create"),
    ("provider_keys", "update"),
    ("provider_keys", "delete"),
    ("provider_keys", "test"),
    # Delivery Logs
    ("delivery_logs", "view"),
    # Analytics
    ("analytics", "view"),
    # Mimic Webhooks
    ("mimic_webhooks", "configure"),
    ("mimic_webhooks", "view"),
    # Gateway
    ("gateway", "view"),
    ("gateway", "admin"),
}

AIOS_PERMISSIONS: Set[PermissionTuple] = {
    # Jobs
    ("jobs", "view"),
    ("jobs", "update"),
    ("jobs", "delete"),
    ("jobs", "retry"),
    ("jobs", "cancel"),
    # Customers
    ("customers", "view"),
    ("customers", "create"),
    ("customers", "update"),
    ("customers", "delete"),
    # Credits
    ("credits", "view"),
    ("credits", "create"),
    ("credits", "spend"),
    # Cells
    ("cells", "view"),
    ("cells", "create"),
    ("cells", "manage"),
    ("cells", "delete"),
    ("cells", "provision"),
    ("cells", "restart"),
    # Usage
    ("usage", "view"),
    ("usage", "admin"),
    # Marketplace
    ("marketplace", "view"),
    ("marketplace", "create"),
    ("marketplace", "update"),
    ("marketplace", "delete"),
    ("marketplace", "publish"),
    ("marketplace", "purchase"),
    ("marketplace", "download"),
    ("marketplace", "review"),
    ("marketplace", "admin"),
}

# All new permissions (excluding InkPass core which already exists)
ALL_NEW_PERMISSIONS = TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS


# =============================================================================
# SEED FUNCTIONS
# =============================================================================


def get_platform_org_id(session) -> str | None:
    """Get the platform organization ID from admin user."""
    admin = session.query(User).filter(User.email == "admin@fluxtopus.com").first()
    if admin:
        return admin.organization_id
    return None


def get_existing_permissions(session, org_id: str) -> Set[PermissionTuple]:
    """Get all existing permissions for an organization."""
    permissions = session.query(Permission).filter(
        Permission.organization_id == org_id
    ).all()
    return {(p.resource, p.action) for p in permissions}


def seed_permissions(
    session,
    org_id: str,
    permissions: Set[PermissionTuple],
    dry_run: bool = False
) -> tuple[int, int]:
    """
    Seed permissions for an organization.

    Returns:
        Tuple of (created_count, skipped_count)
    """
    existing = get_existing_permissions(session, org_id)
    created = 0
    skipped = 0

    for resource, action in sorted(permissions):
        if (resource, action) in existing:
            print(f"  [SKIP] {resource}:{action} (already exists)")
            skipped += 1
            continue

        if dry_run:
            print(f"  [WOULD CREATE] {resource}:{action}")
            created += 1
            continue

        try:
            PermissionService.create_permission(
                db=session,
                organization_id=org_id,
                resource=resource,
                action=action,
            )
            print(f"  [CREATE] {resource}:{action}")
            created += 1
        except Exception as e:
            print(f"  [ERROR] {resource}:{action}: {e}")
            session.rollback()

    return created, skipped


def assign_all_permissions_to_user(session, user_email: str, dry_run: bool = False) -> int:
    """Assign all permissions to a user."""
    user = session.query(User).filter(User.email == user_email).first()
    if not user:
        print(f"  [ERROR] User {user_email} not found")
        return 0

    permissions = session.query(Permission).filter(
        Permission.organization_id == user.organization_id
    ).all()

    assigned = 0
    for perm in permissions:
        if perm not in user.user_permissions:
            if not dry_run:
                user.user_permissions.append(perm)
            assigned += 1

    if not dry_run:
        session.commit()

    return assigned


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed platform permissions")
    parser.add_argument(
        "--org-id",
        help="Organization ID to seed permissions for (defaults to platform org)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making changes",
    )
    parser.add_argument(
        "--service",
        choices=["tentackl", "mimic", "aios", "all"],
        default="all",
        help="Which service permissions to seed (default: all)",
    )
    parser.add_argument(
        "--assign-to",
        help="Email of user to assign all permissions to after seeding",
    )

    args = parser.parse_args()

    print("\n=== Seeding Platform Permissions ===\n")

    if args.dry_run:
        print("  [DRY RUN MODE - No changes will be made]\n")

    session = SessionLocal()
    try:
        # Determine organization ID
        org_id = args.org_id
        if not org_id:
            org_id = get_platform_org_id(session)
            if not org_id:
                print("[ERROR] Could not find platform organization. Please provide --org-id")
                sys.exit(1)
            print(f"Using platform organization: {org_id}\n")

        # Verify organization exists
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            print(f"[ERROR] Organization {org_id} not found")
            sys.exit(1)

        # Determine which permissions to seed
        permissions_to_seed: Set[PermissionTuple] = set()

        if args.service in ("tentackl", "all"):
            print(f"Tentackl permissions ({len(TENTACKL_PERMISSIONS)}):")
            c, s = seed_permissions(session, org_id, TENTACKL_PERMISSIONS, args.dry_run)
            print(f"  Created: {c}, Skipped: {s}\n")
            permissions_to_seed |= TENTACKL_PERMISSIONS

        if args.service in ("mimic", "all"):
            print(f"Mimic permissions ({len(MIMIC_PERMISSIONS)}):")
            c, s = seed_permissions(session, org_id, MIMIC_PERMISSIONS, args.dry_run)
            print(f"  Created: {c}, Skipped: {s}\n")
            permissions_to_seed |= MIMIC_PERMISSIONS

        if args.service in ("aios", "all"):
            print(f"Platform permissions ({len(AIOS_PERMISSIONS)}):")
            c, s = seed_permissions(session, org_id, AIOS_PERMISSIONS, args.dry_run)
            print(f"  Created: {c}, Skipped: {s}\n")
            permissions_to_seed |= AIOS_PERMISSIONS

        # Assign permissions to user if requested
        if args.assign_to:
            print(f"Assigning all permissions to {args.assign_to}...")
            assigned = assign_all_permissions_to_user(session, args.assign_to, args.dry_run)
            print(f"  Assigned: {assigned} permissions\n")

        print(f"=== Done: {len(permissions_to_seed)} total permissions processed ===\n")

    finally:
        session.close()


if __name__ == "__main__":
    main()
