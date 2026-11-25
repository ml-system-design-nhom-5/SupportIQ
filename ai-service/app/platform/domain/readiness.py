"""The readiness port: whether what a request needs is loaded and verified (ERR-18)."""

from typing import Protocol


class ReadinessProbe(Protocol):
    """Check that one thing a request needs is available."""

    def check(self) -> None:
        """Check it once.

        Raises:
            AiServiceError: It is not available, with the code `not-ready`.
        """
        ...
