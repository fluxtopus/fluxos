#!/usr/bin/env python3
"""
Seed development users for testing.

Creates test accounts:
1. admin@fluxtopus.com - Admin user (full access in dev when DEV_PERMISSIONS=admin)
2. free@example.com - Free user (no subscription)
3. plus@example.com - Plus user (active subscription)

Each user gets their own organization and Tentackl platform permissions.

Run with:
    docker compose exec inkpass python scripts/seed_dev_users.py
"""

import os
import sys
from typing import Set, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.database import SessionLocal
from src.database.models import User, Organization, Permission
from src.services.auth_service import AuthService
from src.services.permission_service import PermissionService
from src.templates.permission_templates import (
    INKPASS_CORE_PERMISSIONS,
    TENTACKL_PERMISSIONS,
    MIMIC_PERMISSIONS,
    AIOS_PERMISSIONS,
)


DEV_USERS = [
    {
        "email": "admin@fluxtopus.com",
        "password": "AiosAdmin123!",
        "organization_name": "AIOS",
        "subscription_status": "active",
        "subscription_tier": "aios",
    },
    {
        "email": "free@example.com",
        "password": "FreeUser123!",
        "organization_name": "Free Org",
        "subscription_status": "none",
        "subscription_tier": "free",
    },
    {
        "email": "plus@example.com",
        "password": "PlusUser123!",
        "organization_name": "Plus Org",
        "subscription_status": "active",
        "subscription_tier": "plus",
    },
]


def seed_permissions_for_org(session, org_id: str, permissions: Set[Tuple[str, str]]) -> int:
    """Seed permission tuples into an organization."""
    existing = {
        (p.resource, p.action)
        for p in session.query(Permission).filter(Permission.organization_id == org_id).all()
    }

    created = 0
    for resource, action in sorted(permissions):
        if (resource, action) in existing:
            continue
        try:
            PermissionService.create_permission(
                db=session,
                organization_id=org_id,
                resource=resource,
                action=action,
            )
            created += 1
        except Exception:
            session.rollback()

    return created


def assign_all_permissions_to_user(session, user: User, org_id: str) -> int:
    """Assign all org permissions to a user (dev convenience)."""
    perms = session.query(Permission).filter(Permission.organization_id == org_id).all()
    added = 0
    for perm in perms:
        if perm not in user.user_permissions:
            user.user_permissions.append(perm)
            added += 1
    return added


def seed_user(session, user_data: dict) -> bool:
    """Seed a single user if they don't exist. Also seeds org permissions."""
    existing = session.query(User).filter(User.email == user_data["email"]).first()

    if existing:
        # User exists — ensure their org has permissions and the user has them assigned.
        is_admin = existing.email == "admin@fluxtopus.com"
        perms_to_seed = (
            INKPASS_CORE_PERMISSIONS | TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS
            if is_admin
            else TENTACKL_PERMISSIONS
        )
        perm_count = seed_permissions_for_org(session, str(existing.organization_id), perms_to_seed)
        assigned = assign_all_permissions_to_user(session, existing, str(existing.organization_id))
        if perm_count > 0 or assigned > 0:
            session.commit()
        if perm_count > 0:
            print(f"  [PERMS] {user_data['email']}: added {perm_count} permissions to org")
        else:
            print(f"  [SKIP] {user_data['email']} already exists (permissions OK)")
        if assigned > 0:
            print(f"  [ASSIGN] {user_data['email']}: added {assigned} user permissions")
        return False

    try:
        result = AuthService.register_user(
            db=session,
            email=user_data["email"],
            password=user_data["password"],
            organization_name=user_data["organization_name"],
        )

        # Activate the user (skip email verification for dev)
        user = session.query(User).filter(User.id == result["user_id"]).first()
        user.status = "active"

        # Update organization subscription status
        org = session.query(Organization).filter(Organization.id == result["organization_id"]).first()
        org.subscription_status = user_data["subscription_status"]
        org.subscription_tier = user_data["subscription_tier"]

        session.commit()

        # Seed permissions into the new org
        created_user = session.query(User).filter(User.id == result["user_id"]).first()
        org_id = str(result["organization_id"])
        is_admin = created_user.email == "admin@fluxtopus.com"
        perms_to_seed = (
            INKPASS_CORE_PERMISSIONS | TENTACKL_PERMISSIONS | MIMIC_PERMISSIONS | AIOS_PERMISSIONS
            if is_admin
            else TENTACKL_PERMISSIONS
        )
        perm_count = seed_permissions_for_org(session, org_id, perms_to_seed)
        assigned = assign_all_permissions_to_user(session, created_user, org_id)
        session.commit()

        print(f"  [CREATE] {user_data['email']} (tier: {user_data['subscription_tier']}, org: {org_id}, {perm_count} permissions, {assigned} assigned)")
        return True

    except ValueError as e:
        print(f"  [SKIP] {user_data['email']}: {e}")
        return False
    except Exception as e:
        print(f"  [ERROR] {user_data['email']}: {e}")
        session.rollback()
        return False


def main():
    """Seed all development users."""
    print("\n=== Seeding Development Users ===\n")

    created = 0
    skipped = 0

    session = SessionLocal()
    try:
        for user_data in DEV_USERS:
            if seed_user(session, user_data):
                created += 1
            else:
                skipped += 1
    finally:
        session.close()

    print(f"\n=== Done: {created} created, {skipped} skipped ===")
    print("\nTest accounts:")
    print("  Admin: admin@fluxtopus.com / AiosAdmin123!")
    print("  Free:  free@example.com / FreeUser123!")
    print("  Plus:  plus@example.com / PlusUser123!")
    print()


if __name__ == "__main__":
    main()
