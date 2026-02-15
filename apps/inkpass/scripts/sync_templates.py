#!/usr/bin/env python3
"""
CLI tool for syncing permission templates.

Usage:
    python scripts/sync_templates.py sync          # Sync templates from code to DB
    python scripts/sync_templates.py status        # Show sync status
    python scripts/sync_templates.py propagate ID  # Propagate template to all orgs
    python scripts/sync_templates.py migrate       # Migrate existing orgs (dry run)
    python scripts/sync_templates.py migrate --apply  # Migrate existing orgs (apply)

Run inside Docker:
    docker compose exec inkpass python scripts/sync_templates.py sync
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.services.admin_template_sync_service import AdminTemplateSyncService
from src.config import settings


def get_db_session():
    """Create a database session."""
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def cmd_sync(args):
    """Sync templates from code to database."""
    print("Syncing templates from code to database...")
    db = get_db_session()
    try:
        service = AdminTemplateSyncService(db)
        result = service.sync_templates_from_code()
        db.commit()

        print("\n=== Sync Results ===")
        print(f"Created: {len(result.created)}")
        for name in result.created:
            print(f"  + {name}")

        print(f"Updated: {len(result.updated)}")
        for name in result.updated:
            print(f"  ~ {name}")

        print(f"Unchanged: {len(result.unchanged)}")
        for name in result.unchanged:
            print(f"  = {name}")

        if result.errors:
            print(f"Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"  ! {error}")
            return 1

        print("\nSync completed successfully!")
        return 0
    finally:
        db.close()


def cmd_status(args):
    """Show sync status."""
    print("Checking template sync status...")
    db = get_db_session()
    try:
        service = AdminTemplateSyncService(db)
        status = service.get_sync_status()

        print("\n=== Template Sync Status ===")
        print(f"Needs Sync: {'Yes' if status.needs_sync else 'No'}")
        print("\nTemplates:")
        for template in status.templates:
            icon = "!" if template["needs_update"] else "="
            db_ver = template.get("db_version", "N/A")
            code_ver = template["code_version"]
            print(f"  {icon} {template['name']}: DB v{db_ver} -> Code v{code_ver}")

        return 0
    finally:
        db.close()


def cmd_propagate(args):
    """Propagate template to all organizations using it."""
    template_id = args.template_id
    print(f"Propagating template {template_id} to all organizations...")
    db = get_db_session()
    try:
        service = AdminTemplateSyncService(db)
        result = service.propagate_template(template_id)
        db.commit()

        print("\n=== Propagation Results ===")
        print(f"Template: {result.template_name}")
        print(f"Organizations Updated: {result.orgs_updated}")
        print(f"Permissions Added: {result.permissions_added}")

        if result.errors:
            print(f"Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"  ! {error}")
            return 1

        print("\nPropagation completed successfully!")
        return 0
    finally:
        db.close()


def cmd_migrate(args):
    """Migrate existing organizations to template system."""
    dry_run = not args.apply
    mode = "DRY RUN" if dry_run else "APPLYING CHANGES"
    print(f"Migrating existing organizations... ({mode})")

    db = get_db_session()
    try:
        service = AdminTemplateSyncService(db)
        result = service.migrate_existing_orgs(dry_run=dry_run)
        if not dry_run:
            db.commit()

        print("\n=== Migration Results ===")
        print(f"Dry Run: {result.dry_run}")
        print(f"Organizations Migrated: {result.orgs_migrated}")

        if result.details:
            print("\nDetails:")
            for detail in result.details:
                org_name = detail.get("organization_name", "Unknown")
                action = detail.get("action", "unknown")
                error = detail.get("error")
                if error:
                    print(f"  ! {org_name}: {action} - {error}")
                else:
                    print(f"  + {org_name}: {action}")

        if result.errors:
            print(f"\nErrors: {len(result.errors)}")
            for error in result.errors:
                print(f"  ! {error}")
            return 1

        if dry_run:
            print("\nDry run complete. Use --apply to apply changes.")
        else:
            print("\nMigration completed successfully!")
        return 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for managing permission templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync templates from code to DB")
    sync_parser.set_defaults(func=cmd_sync)

    # status command
    status_parser = subparsers.add_parser("status", help="Show sync status")
    status_parser.set_defaults(func=cmd_status)

    # propagate command
    prop_parser = subparsers.add_parser("propagate", help="Propagate template to orgs")
    prop_parser.add_argument("template_id", help="Template ID to propagate")
    prop_parser.set_defaults(func=cmd_propagate)

    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Migrate existing orgs")
    migrate_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry run)",
    )
    migrate_parser.set_defaults(func=cmd_migrate)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
