"""The writer of rows that every area of the builders shares (TEST-05, TEST-14).

It connects as the owner, because `supportiq_app` cannot insert admin accounts, customer
accounts, or commerce data. IDs and times come from one counter, so a test run is
deterministic.
"""

from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from itertools import count
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql import Executable

from tests.unit.platform.fakes import FAKE_CLOCK_START


class RowWriter:
    """Write rows as the owner, each call in its own committed transaction."""

    def __init__(self, owner_engine: AsyncEngine) -> None:
        """Keep the owner engine and start the counter of IDs and times.

        Args:
            owner_engine: An engine that connects as the owner.
        """
        self._engine = owner_engine
        self._counter = count(1)

    def next_number(self) -> int:
        """Return the next number of the counter, for unique test values."""
        return next(self._counter)

    def next_uuid(self) -> UUID:
        """Return the next deterministic UUID."""
        return UUID(int=self.next_number())

    def next_time(self) -> datetime:
        """Return a time one minute after the previous one, in UTC."""
        return FAKE_CLOCK_START + timedelta(minutes=self.next_number())

    def begin(self) -> AbstractAsyncContextManager[AsyncConnection]:
        """Start a transaction as the owner, for statements that need the result of another."""
        return self._engine.begin()

    async def execute(self, *statements: Executable) -> None:
        """Run write statements as the owner in one transaction."""
        async with self._engine.begin() as connection:
            for statement in statements:
                await connection.execute(statement)

    async def scalar(self, statement: str, **parameters: object) -> object:
        """Run one read statement as the owner and return its first value.

        Args:
            statement: The SQL text with bound parameters.
            **parameters: The parameters.
        """
        async with self._engine.connect() as connection:
            return await connection.scalar(text(statement), parameters)
