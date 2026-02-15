#!/usr/bin/env python3
"""CLI tool for managing Tentackl authentication."""

import asyncio
import click
import json
from datetime import datetime, timedelta
from typing import Optional, List
import os

from src.api.auth_middleware import (
    auth_middleware, Scopes,
    READONLY_SCOPES, OPERATOR_SCOPES, DEVELOPER_SCOPES, ADMIN_SCOPES,
    create_access_token
)


@click.group()
def auth():
    """Manage Tentackl authentication and API keys."""
    pass


@auth.command()
@click.option('--service-name', '-s', required=True, help='Name of the service')
@click.option('--scope', '-S', multiple=True, help='Scopes to grant (can be specified multiple times)')
@click.option('--permission-group', '-p', 
              type=click.Choice(['readonly', 'operator', 'developer', 'admin']),
              help='Pre-defined permission group')
@click.option('--expires-days', '-e', type=int, help='Days until expiration (omit for no expiration)')
def create_api_key(service_name: str, scope: tuple, permission_group: Optional[str], expires_days: Optional[int]):
    """Create a new API key for service authentication."""
    
    # Determine scopes
    scopes = []
    if permission_group:
        if permission_group == 'readonly':
            scopes = READONLY_SCOPES
        elif permission_group == 'operator':
            scopes = OPERATOR_SCOPES
        elif permission_group == 'developer':
            scopes = DEVELOPER_SCOPES
        elif permission_group == 'admin':
            scopes = ADMIN_SCOPES
    elif scope:
        scopes = list(scope)
    else:
        click.echo("Error: Either --scope or --permission-group must be specified", err=True)
        return
    
    async def create():
        try:
            api_key = await auth_middleware.create_api_key(
                service_name=service_name,
                scopes=scopes,
                expires_in_days=expires_days
            )
            
            click.echo("\n✅ API Key created successfully!")
            click.echo(f"Service: {service_name}")
            click.echo(f"Scopes: {', '.join(scopes)}")
            if expires_days:
                expiry = datetime.utcnow() + timedelta(days=expires_days)
                click.echo(f"Expires: {expiry.isoformat()}")
            click.echo(f"\n🔑 API Key: {api_key}")
            click.echo("\n⚠️  Store this key securely - it won't be shown again!")
            
        except Exception as e:
            click.echo(f"Error creating API key: {e}", err=True)
    
    asyncio.run(create())


@auth.command()
@click.argument('api_key')
def revoke_api_key(api_key: str):
    """Revoke an existing API key."""
    
    async def revoke():
        try:
            success = await auth_middleware.revoke_api_key(api_key)
            if success:
                click.echo("✅ API key revoked successfully")
            else:
                click.echo("❌ API key not found", err=True)
        except Exception as e:
            click.echo(f"Error revoking API key: {e}", err=True)
    
    asyncio.run(revoke())


@auth.command()
@click.option('--username', '-u', required=True, help='Username')
@click.option('--user-id', '-i', help='User ID (defaults to username)')
@click.option('--scope', '-s', multiple=True, help='Scopes to grant')
@click.option('--permission-group', '-p',
              type=click.Choice(['readonly', 'operator', 'developer', 'admin']),
              help='Pre-defined permission group')
@click.option('--expires-minutes', '-e', type=int, default=30, help='Minutes until expiration')
def create_token(username: str, user_id: Optional[str], scope: tuple, 
                permission_group: Optional[str], expires_minutes: int):
    """Create a JWT access token for testing."""
    
    # Determine scopes
    scopes = []
    if permission_group:
        if permission_group == 'readonly':
            scopes = READONLY_SCOPES
        elif permission_group == 'operator':
            scopes = OPERATOR_SCOPES
        elif permission_group == 'developer':
            scopes = DEVELOPER_SCOPES
        elif permission_group == 'admin':
            scopes = ADMIN_SCOPES
    elif scope:
        scopes = list(scope)
    
    async def create():
        try:
            token = await create_access_token(
                user_id=user_id or username,
                username=username,
                scopes=scopes,
                expires_delta=timedelta(minutes=expires_minutes)
            )
            
            click.echo("\n✅ Access token created!")
            click.echo(f"Username: {username}")
            click.echo(f"User ID: {user_id or username}")
            click.echo(f"Scopes: {', '.join(scopes) if scopes else 'none'}")
            click.echo(f"Expires in: {expires_minutes} minutes")
            click.echo(f"\n🎫 Token: {token}")
            
        except Exception as e:
            click.echo(f"Error creating token: {e}", err=True)
    
    asyncio.run(create())


@auth.command()
def list_scopes():
    """List all available API scopes."""
    click.echo("\n📋 Available API Scopes:\n")
    
    click.echo("WORKFLOW:")
    click.echo(f"  - {Scopes.WORKFLOW_READ}: Read workflow data")
    click.echo(f"  - {Scopes.WORKFLOW_WRITE}: Create and modify workflows")
    click.echo(f"  - {Scopes.WORKFLOW_DELETE}: Delete workflows")
    click.echo(f"  - {Scopes.WORKFLOW_EXECUTE}: Execute workflows")
    click.echo(f"  - {Scopes.WORKFLOW_CONTROL}: Control workflow state")
    
    click.echo("\nAGENT:")
    click.echo(f"  - {Scopes.AGENT_READ}: Read agent data")
    click.echo(f"  - {Scopes.AGENT_WRITE}: Create and modify agents")
    click.echo(f"  - {Scopes.AGENT_EXECUTE}: Execute agents")
    
    click.echo("\nEVENT:")
    click.echo(f"  - {Scopes.EVENT_READ}: Read events")
    click.echo(f"  - {Scopes.EVENT_PUBLISH}: Publish events")
    click.echo(f"  - {Scopes.WEBHOOK_PUBLISH}: Publish webhook events")
    
    click.echo("\nOTHER:")
    click.echo(f"  - {Scopes.METRICS_READ}: Read metrics data")
    click.echo(f"  - {Scopes.ADMIN}: Full administrative access")
    
    click.echo("\n👥 Permission Groups:")
    click.echo(f"  - readonly: {', '.join(READONLY_SCOPES)}")
    click.echo(f"  - operator: {', '.join(OPERATOR_SCOPES)}")
    click.echo(f"  - developer: {', '.join(DEVELOPER_SCOPES)}")
    click.echo(f"  - admin: {', '.join(ADMIN_SCOPES)}")


@auth.command()
@click.option('--output', '-o', type=click.Path(), help='Output file for environment variables')
def generate_env(output: Optional[str]):
    """Generate environment variables for authentication."""
    import secrets
    
    env_vars = f"""# Tentackl Authentication Configuration
# Generated on {datetime.utcnow().isoformat()}

# Secret key for JWT signing (change in production!)
TENTACKL_SECRET_KEY={secrets.token_urlsafe(32)}

# Token expiration time in minutes
TENTACKL_TOKEN_EXPIRE_MINUTES=30

# Redis URL for API key storage
REDIS_URL=redis://redis:6379
"""
    
    if output:
        with open(output, 'w') as f:
            f.write(env_vars)
        click.echo(f"✅ Environment variables written to {output}")
    else:
        click.echo(env_vars)


if __name__ == '__main__':
    auth()