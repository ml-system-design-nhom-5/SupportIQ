"""Waiting until concurrent requests wait for a lock of PostgreSQL, without a sleep (TEST-14)."""

import asyncio

import httpx
import pytest

from tests.integration.builders import DatabaseBuilder

# A wait for a row that another transaction holds is a wait for that transaction's ID.
ROW_LOCK_WAITS = """
    SELECT count(*)
    FROM pg_locks AS waiting
    JOIN pg_stat_activity AS activity USING (pid)
    WHERE NOT waiting.granted
      AND waiting.locktype = 'transactionid'
      AND activity.datname = current_database()
"""
ADVISORY_LOCK_WAITS = """
    SELECT count(*)
    FROM pg_locks AS waiting
    JOIN pg_stat_activity AS activity USING (pid)
    WHERE NOT waiting.granted
      AND waiting.locktype = 'advisory'
      AND activity.datname = current_database()
"""


async def wait_until_waiting(
    builder: DatabaseBuilder,
    lock_waits: str,
    count: int,
    *requests: asyncio.Task[httpx.Response],
) -> None:
    """Return once `count` requests wait for a lock of the kind that `lock_waits` counts.

    Each read is its own transaction, so it sees the current locks. The round trip to
    PostgreSQL gives the requests their turn, so the loop needs no sleep, and the lock timeout
    of the application ends a request that waits too long, which ends the loop.

    Args:
        builder: The test data builder, whose owner connection reads the locks.
        lock_waits: The query that counts the waits, `ROW_LOCK_WAITS` or `ADVISORY_LOCK_WAITS`.
        count: The number of waiting requests to wait for.
        *requests: The requests that must still run.
    """
    while not any(request.done() for request in requests):
        if await builder.scalar(lock_waits) == count:
            return
    pytest.fail("A request ended before the expected requests waited for the lock.")
