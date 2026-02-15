# REVIEW:
# - day_of_week conversion only handles simple numeric values; lists/ranges/names may be incorrect.
"""Utilities for parsing and validating cron expressions."""

from typing import Optional, Tuple
from datetime import datetime
import structlog
from croniter import croniter
from celery.schedules import crontab
import pytz

logger = structlog.get_logger()


class CronParseError(Exception):
    """Raised when a cron string cannot be parsed or is invalid."""
    pass


def validate_cron_string(cron_string: str) -> bool:
    """
    Validate that a cron string is in valid 5-field format.
    
    Args:
        cron_string: Standard 5-field cron expression (minute hour day month weekday)
        
    Returns:
        True if valid, False otherwise
        
    Examples:
        "0 4 15 * *" - 15th of month at 4 AM
        "*/5 * * * *" - Every 5 minutes
        "0 9 * * 1" - Every Monday at 9 AM
    """
    if not cron_string or not isinstance(cron_string, str):
        return False
    
    # Check basic format: should have 5 fields separated by spaces
    parts = cron_string.strip().split()
    if len(parts) != 5:
        return False
    
    # Try to create a croniter instance to validate
    try:
        croniter(cron_string)
        return True
    except Exception:
        return False


def parse_cron_string(cron_string: str, timezone: str = "UTC") -> crontab:
    """
    Parse a 5-field cron string into a Celery crontab schedule.
    
    Args:
        cron_string: Standard 5-field cron expression
        timezone: Timezone string (e.g., "UTC", "America/New_York")
        
    Returns:
        Celery crontab object configured with the schedule
        
    Raises:
        CronParseError: If cron string is invalid
        
    Examples:
        >>> parse_cron_string("0 4 15 * *", "UTC")
        crontab(minute=0, hour=4, day_of_month=15, month_of_year='*', day_of_week='*')
    """
    if not validate_cron_string(cron_string):
        raise CronParseError(f"Invalid cron string: {cron_string}")
    
    try:
        # Parse the cron string into components
        parts = cron_string.strip().split()
        minute, hour, day_of_month, month_of_year, day_of_week = parts
        
        # Convert day_of_week: cron uses 0-6 (0=Sunday), Celery uses 0-6 (0=Monday)
        # We need to adjust: cron 0=Sunday, Celery 0=Monday
        # So cron 0 -> Celery 6, cron 1-6 -> Celery 0-5
        if day_of_week != '*':
            try:
                cron_dow = int(day_of_week)
                # Convert: cron 0 (Sunday) -> Celery 6, cron 1-6 -> Celery 0-5
                celery_dow = (cron_dow + 1) % 7 if cron_dow != '*' else '*'
            except ValueError:
                # Handle ranges and lists
                celery_dow = day_of_week
        else:
            celery_dow = '*'
        
        # Get timezone object (for calculating next run, not for crontab)
        # Note: Celery crontab doesn't accept tz parameter directly
        # Timezone is handled at the app level in celery_app.py
        # We store timezone in database for reference and next_run calculation
        
        # Create Celery crontab
        # Celery crontab accepts None to mean "every", but we need to handle it properly
        # Build kwargs, only including non-wildcard fields
        crontab_kwargs = {}
        
        if minute != '*':
            crontab_kwargs['minute'] = minute
        if hour != '*':
            crontab_kwargs['hour'] = hour
        if day_of_month != '*':
            crontab_kwargs['day_of_month'] = day_of_month
        if month_of_year != '*':
            crontab_kwargs['month_of_year'] = month_of_year
        if celery_dow != '*':
            crontab_kwargs['day_of_week'] = celery_dow
        
        return crontab(**crontab_kwargs)
    except Exception as e:
        raise CronParseError(f"Failed to parse cron string '{cron_string}': {str(e)}") from e


def calculate_next_run(cron_string: str, timezone: str = "UTC", start_time: Optional[datetime] = None) -> datetime:
    """
    Calculate the next run time for a cron expression.
    
    Args:
        cron_string: Standard 5-field cron expression
        timezone: Timezone string
        start_time: Starting time (defaults to now)
        
    Returns:
        Next scheduled run time as datetime
        
    Raises:
        CronParseError: If cron string is invalid
    """
    if not validate_cron_string(cron_string):
        raise CronParseError(f"Invalid cron string: {cron_string}")
    
    try:
        # Get timezone object
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone {timezone}, defaulting to UTC")
            tz = pytz.UTC
        
        # Use current time if not provided
        if start_time is None:
            start_time = datetime.now(tz)
        elif start_time.tzinfo is None:
            # If naive datetime, assume it's in the specified timezone
            start_time = tz.localize(start_time)
        
        # Create croniter instance and get next run
        cron = croniter(cron_string, start_time)
        next_run = cron.get_next(datetime)
        
        return next_run
    except Exception as e:
        raise CronParseError(f"Failed to calculate next run for '{cron_string}': {str(e)}") from e
