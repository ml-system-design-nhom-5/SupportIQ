"""Stored texts that no enum of backend has, for the adapter tests of PY-20.

Backend stores only values of its enums, so a stored text that no member has is a defect of
backend: each store reads it as an unexpected failure whose cause is the `ValueError` (ERR-05).
A check constraint refuses an unknown value, so the owner drops the check in the transaction of
the read, as a later migration that allows a new value would, and the rollback restores it.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from tests.integration.database import WorkerDatabase, create_owner_engine

# A value of a later release, which no enum of this code has.
UNKNOWN_VALUE = "value_of_a_later_release"
# The check of the handling mode of a ticket, which the stores of tickets and reports read.
DROP_HANDLING_MODE_CHECK = "ALTER TABLE tickets DROP CONSTRAINT tickets_handling_mode_check"


@asynccontextmanager
async def session_without_check(
    worker_database: WorkerDatabase, drop_check: str, write: Executable
) -> AsyncGenerator[AsyncSession]:
    """Drop a check and store a value that it refuses, in a transaction that is rolled back.

    Args:
        worker_database: The database of the worker; the owner may drop the check.
        drop_check: The DDL statement, a constant of the test module (PY-42).
        write: The statement that stores the unknown value.

    Yields:
        A session in that transaction, for the store under test.
    """
    engine = create_owner_engine(worker_database)
    try:
        async with engine.connect() as connection:
            try:
                await connection.execute(text(drop_check))
                await connection.execute(write)
                async with AsyncSession(connection) as session:
                    yield session
            finally:
                await connection.rollback()
    finally:
        await engine.dispose()
