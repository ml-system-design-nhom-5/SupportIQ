"""The unit of work: database transactions that only the application layer commits (PY-41)."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class Transaction[StoresT](Protocol):
    """One open database transaction and the stores that work inside it.

    Leaving the transaction without `commit` rolls it back, whatever the reason, so every
    error path of a use case changes nothing.
    """

    @property
    def stores(self) -> StoresT:
        """Return the stores bound to this transaction."""
        ...

    async def commit(self) -> None:
        """Commit the transaction.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        ...


class TransactionRunner[StoresT](Protocol):
    """Open transactions for one use case, with the stores that the use case needs."""

    def begin(self) -> AbstractAsyncContextManager[Transaction[StoresT]]:
        """Open a transaction.

        Returns:
            A context manager that yields the transaction and rolls it back on exit unless
            it was committed.

        Raises:
            DatabaseUnavailableError: No connection could be obtained within the pool and
                connect timeouts.
        """
        ...
