"""Fixtures of the tests that run the application: the cleanup of the worker database.

The tests of the ai-service client in the folder above use no database, so their conftest
replaces the cleanup of the tables. These tests read sessions from PostgreSQL, so they start
from empty tables again, as every other integration test does (TEST-17).
"""

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
