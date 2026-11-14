"""Fixtures of the tests of the ai-service client, which use no database.

The client talks to an in-memory `httpx` transport, so these tests replace the autouse
fixture that empties the tables of the worker database: they run without PostgreSQL.
"""

import pytest


@pytest.fixture(autouse=True)
def empty_tables() -> None:
    """Replace the cleanup of the database tables: these tests have none."""
