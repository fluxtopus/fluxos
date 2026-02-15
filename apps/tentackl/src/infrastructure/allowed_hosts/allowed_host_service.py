# REVIEW: DNS resolution is done inline per request; no caching and potential
# REVIEW: latency/SSRF races.
"""Service for managing and checking allowed HTTP hosts with denylist and SSRF protection."""

from typing import List, Set, Optional
from urllib.parse import urlparse
from datetime import datetime
import ipaddress
import socket
import structlog
from src.database.allowed_host_models import AllowedHost, Environment
from src.interfaces.database import Database
from src.core.config import settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Hardcoded denylist - exact hosts that are NEVER allowed
DENYLISTED_HOSTS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # AWS metadata service
    "metadata.google.internal",  # GCP metadata service
    "169.254.169.254",  # Azure metadata service
}

# Private IP ranges (RFC 1918, link-local, loopback, etc.)
PRIVATE_IP_RANGES = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),  # Link-local
    ipaddress.IPv4Network("224.0.0.0/4"),  # Multicast
]


class AllowedHostService:
    """Service for checking if a host is allowed for HTTP requests."""
    
    def __init__(self, database: Optional[Database] = None):
        self.database = database or Database()
    
    async def is_host_allowed(
        self, url: str, environment: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a host is allowed for HTTP requests.

        Args:
            url: The URL to check
            environment: Environment to check against. If None, uses settings.APP_ENV.
                        Pass explicitly for admin APIs that need to check other environments.

        Returns:
            (is_allowed, error_message)
            - is_allowed: True if host is allowed, False otherwise
            - error_message: Human-readable error if not allowed, None if allowed
        """
        env = environment or settings.APP_ENV
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""

            # 1. Check HTTPS requirement
            if parsed.scheme != "https":
                return False, f"Only HTTPS URLs are allowed (got {parsed.scheme})"

            # 2. Check for IP literals (not allowed)
            if self._is_ip_literal(host):
                return False, f"IP literal addresses are not allowed (use hostname): {host}"

            # 3. Check denylist first (denylist always wins)
            if host.lower() in DENYLISTED_HOSTS:
                return False, f"Host '{host}' is in the denylist and cannot be allowed"

            # 4. Check if host resolves to private IP (SSRF protection)
            try:
                resolved_ip = socket.gethostbyname(host)
                if self._is_private_ip(resolved_ip):
                    return False, f"Host '{host}' resolves to private IP '{resolved_ip}' (SSRF protection)"
            except socket.gaierror:
                # DNS resolution failed - we'll allow it but log a warning
                logger.warning("DNS resolution failed for host", host=host)

            # 5. Check allowlist in database
            env_enum = Environment(env)
            async with self.database.get_session() as session:
                stmt = select(AllowedHost).where(
                    AllowedHost.host == host,
                    AllowedHost.environment == env_enum,
                    AllowedHost.enabled == True
                )
                result = await session.execute(stmt)
                allowed_host = result.scalar_one_or_none()

                if allowed_host is None:
                    return False, f"Host '{host}' is not in the allowlist for environment '{env}'"

            return True, None

        except Exception as e:
            logger.error("Error checking host allowlist", url=url, error=str(e))
            return False, f"Error checking host allowlist: {str(e)}"
    
    def _is_ip_literal(self, host: str) -> bool:
        """Check if host is an IP literal (IPv4 or IPv6)."""
        try:
            # Try to parse as IPv4
            ipaddress.IPv4Address(host)
            return True
        except ValueError:
            try:
                # Try to parse as IPv6
                ipaddress.IPv6Address(host)
                return True
            except ValueError:
                return False
    
    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if an IP address is in a private/reserved range."""
        try:
            ip = ipaddress.IPv4Address(ip_str)
            for network in PRIVATE_IP_RANGES:
                if ip in network:
                    return True
            return False
        except ValueError:
            # Not a valid IPv4 address
            return False
    
    async def get_allowed_hosts(self, environment: Optional[str] = None) -> List[AllowedHost]:
        """
        Get all allowed hosts for an environment.

        Args:
            environment: Environment to filter by. If None, uses settings.APP_ENV.
                        Pass explicitly for admin APIs that need to query other environments.
        """
        env = environment or settings.APP_ENV
        async with self.database.get_session() as session:
            env_enum = Environment(env)
            stmt = (
                select(AllowedHost)
                .where(AllowedHost.enabled == True)
                .where(AllowedHost.environment == env_enum)
                .order_by(AllowedHost.host)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def add_allowed_host(
        self,
        host: str,
        environment: str,
        created_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> AllowedHost:
        """Add a new allowed host."""
        # Validate host format (should be hostname, not URL)
        if "/" in host or ":" in host and not host.startswith("["):  # Allow IPv6 brackets
            raise ValueError(f"Invalid host format: '{host}'. Use hostname only (e.g., 'api.example.com')")
        
        # Check denylist
        if host.lower() in DENYLISTED_HOSTS:
            raise ValueError(f"Host '{host}' is in the denylist and cannot be added")
        
        env_enum = Environment(environment)
        
        async with self.database.get_session() as session:
            # Check if already exists
            stmt = select(AllowedHost).where(
                AllowedHost.host == host,
                AllowedHost.environment == env_enum
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing entry
                existing.enabled = True
                existing.notes = notes or existing.notes
                existing.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(existing)
                return existing
            
            # Create new entry
            allowed_host = AllowedHost(
                host=host,
                environment=env_enum,
                enabled=True,
                created_by=created_by,
                notes=notes
            )
            session.add(allowed_host)
            await session.commit()
            await session.refresh(allowed_host)
            return allowed_host
    
    async def remove_allowed_host(
        self,
        host: str,
        environment: str
    ) -> bool:
        """Disable an allowed host (soft delete by setting enabled=False)."""
        env_enum = Environment(environment)
        
        async with self.database.get_session() as session:
            stmt = select(AllowedHost).where(
                AllowedHost.host == host,
                AllowedHost.environment == env_enum
            )
            result = await session.execute(stmt)
            allowed_host = result.scalar_one_or_none()
            
            if not allowed_host:
                return False
            
            allowed_host.enabled = False
            await session.commit()
            return True
