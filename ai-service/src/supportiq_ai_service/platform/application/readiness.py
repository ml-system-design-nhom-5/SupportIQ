"""The readiness use case behind `GET /health/ready` (ERR-18)."""

from supportiq_ai_service.platform.domain import ReadinessProbe


class CheckReadiness:
    """Decide whether this instance can serve requests."""

    def __init__(self, probes: tuple[ReadinessProbe, ...]) -> None:
        """Keep the probes of everything that a request needs.

        Args:
            probes: One probe per need. Settings are valid by construction, because startup
                stops on invalid settings (ARCH-34). Readiness never depends on the LLM
                provider (ERR-19).
        """
        self._probes = probes

    def execute(self) -> None:
        """Check every probe in turn.

        Raises:
            AiServiceError: A probe failed, with the code `not-ready`.
        """
        for probe in self._probes:
            probe.check()
