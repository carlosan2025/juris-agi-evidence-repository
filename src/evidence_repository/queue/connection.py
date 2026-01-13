"""Redis connection and queue management."""

from functools import lru_cache

from redis import Redis
from rq import Queue

from evidence_repository.config import get_settings


@lru_cache
def get_redis_connection() -> Redis:
    """Get Redis connection instance.

    Returns:
        Redis connection (cached singleton).
    """
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,  # RQ needs bytes
    )


@lru_cache
def get_queue(name: str | None = None) -> Queue:
    """Get RQ queue instance.

    Args:
        name: Optional queue name. Uses default from settings if not provided.

    Returns:
        RQ Queue instance.
    """
    settings = get_settings()
    queue_name = name or settings.redis_queue_name

    return Queue(
        name=queue_name,
        connection=get_redis_connection(),
        default_timeout=settings.redis_job_timeout,
    )


def get_high_priority_queue() -> Queue:
    """Get high priority queue for urgent jobs."""
    settings = get_settings()
    return Queue(
        name=f"{settings.redis_queue_name}_high",
        connection=get_redis_connection(),
        default_timeout=settings.redis_job_timeout,
    )


def get_low_priority_queue() -> Queue:
    """Get low priority queue for batch jobs."""
    settings = get_settings()
    return Queue(
        name=f"{settings.redis_queue_name}_low",
        connection=get_redis_connection(),
        default_timeout=settings.redis_job_timeout * 2,  # Longer timeout for batch
    )


def clear_all_queues() -> dict[str, int]:
    """Clear all queues. Use with caution.

    Returns:
        Dict with queue names and number of jobs cleared.
    """
    settings = get_settings()
    results = {}

    for queue in [get_queue(), get_high_priority_queue(), get_low_priority_queue()]:
        count = queue.count
        queue.empty()
        results[queue.name] = count

    return results
