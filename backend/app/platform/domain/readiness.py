"""The readiness port: whether the dependencies of backend answer (ERR-18)."""

from typing import Protocol


class ReadinessProbe(Protocol):
    """Check that a dependency answers within its timeout."""

    async def check(self) -> None:
        """Check the dependency once.

        Raises:
            DatabaseUnavailableError: The dependency did not answer within its timeout.
        """
        ...
