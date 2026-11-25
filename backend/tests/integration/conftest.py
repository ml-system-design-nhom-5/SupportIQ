"""Fixtures of the integration layer."""

import asyncio

import pytest

from tests.integration.database import WorkerDatabase, empty_every_table


@pytest.fixture(autouse=True)
def empty_tables(worker_database: WorkerDatabase) -> None:
    """Start every test from empty tables, so no test sees the data of another (TEST-17).

    Args:
        worker_database: The database of the worker.
    """
    asyncio.run(empty_every_table(worker_database))
