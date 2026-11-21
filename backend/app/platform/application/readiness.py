"""The readiness use case behind `GET /health/ready` (ERR-18)."""

from app.platform.domain import ReadinessProbe


class CheckReadiness:
    """Decide whether this instance can serve requests."""

    def __init__(self, probes: tuple[ReadinessProbe, ...]) -> None:
        """Keep the probes of every dependency that a request needs.

        Args:
            probes: One probe per dependency. Settings are valid by construction, because
                startup stops on invalid settings (ARCH-34).
        """
        self._probes = probes

    async def execute(self) -> None:
        """Check every dependency in turn.

        Raises:
            DatabaseUnavailableError: A dependency did not answer within its timeout.
        """
        for probe in self._probes:
            await probe.check()
