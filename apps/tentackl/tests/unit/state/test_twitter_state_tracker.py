"""
Unit tests for Twitter State Tracker.

Tests the daily post count tracking functionality with Redis.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
import redis.asyncio as redis

from src.state.twitter_state_tracker import TwitterStateTracker


@pytest.fixture
async def tracker():
    """Create TwitterStateTracker instance for testing."""
    redis_url = "redis://redis:6379"
    tracker = TwitterStateTracker(
        redis_url=redis_url,
        db=14,  # Use DB 14 for Twitter tests
        key_prefix="test:twitter:posts:count",
        daily_limit=3
    )
    
    # Clean up test data
    redis_client = await redis.from_url(f"{redis_url}/14", decode_responses=True)
    await redis_client.flushdb()
    await redis_client.aclose()
    
    yield tracker
    
    # Cleanup
    await tracker.close()


@pytest.mark.asyncio
async def test_check_daily_limit_initially_allows(tracker):
    """Test that daily limit check initially allows posting."""
    can_post = await tracker.check_daily_limit()
    assert can_post is True


@pytest.mark.asyncio
async def test_get_post_count_initially_zero(tracker):
    """Test that initial post count is zero."""
    count = await tracker.get_post_count()
    assert count == 0


@pytest.mark.asyncio
async def test_get_remaining_posts_initially_full(tracker):
    """Test that remaining posts is initially at the limit."""
    remaining = await tracker.get_remaining_posts()
    assert remaining == 3


@pytest.mark.asyncio
async def test_increment_post_count(tracker):
    """Test incrementing post count."""
    count_before = await tracker.get_post_count()
    new_count = await tracker.increment_post_count()
    count_after = await tracker.get_post_count()
    
    assert new_count == count_before + 1
    assert count_after == new_count


@pytest.mark.asyncio
async def test_daily_limit_enforcement(tracker):
    """Test that daily limit is enforced after reaching limit."""
    # Increment to limit
    for i in range(3):
        await tracker.increment_post_count()
    
    # Should be at limit
    can_post = await tracker.check_daily_limit()
    assert can_post is False
    
    remaining = await tracker.get_remaining_posts()
    assert remaining == 0
    
    count = await tracker.get_post_count()
    assert count == 3


@pytest.mark.asyncio
async def test_remaining_posts_decreases(tracker):
    """Test that remaining posts decreases as count increases."""
    remaining1 = await tracker.get_remaining_posts()
    await tracker.increment_post_count()
    remaining2 = await tracker.get_remaining_posts()
    
    assert remaining2 == remaining1 - 1


@pytest.mark.asyncio
async def test_reset_count(tracker):
    """Test resetting post count."""
    await tracker.increment_post_count()
    await tracker.increment_post_count()
    
    count_before = await tracker.get_post_count()
    assert count_before == 2
    
    await tracker.reset_count()
    
    count_after = await tracker.get_post_count()
    assert count_after == 0


@pytest.mark.asyncio
async def test_date_key_generation(tracker):
    """Test that date keys are generated correctly."""
    today = datetime.utcnow()
    key = tracker._get_date_key(today)
    
    expected_date = today.strftime("%Y-%m-%d")
    assert expected_date in key
    assert tracker.key_prefix in key


@pytest.mark.asyncio
async def test_seconds_until_midnight(tracker):
    """Test calculation of seconds until midnight."""
    seconds = tracker._seconds_until_midnight()
    
    # Should be positive and less than 24 hours
    assert seconds > 0
    assert seconds <= 86400  # 24 hours in seconds


@pytest.mark.asyncio
async def test_different_dates_isolation(tracker):
    """Test that different dates have isolated counts."""
    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)
    
    # Increment today's count
    await tracker.increment_post_count(today)
    
    # Yesterday's count should still be 0
    count_yesterday = await tracker.get_post_count(yesterday)
    assert count_yesterday == 0
    
    # Today's count should be 1
    count_today = await tracker.get_post_count(today)
    assert count_today == 1

