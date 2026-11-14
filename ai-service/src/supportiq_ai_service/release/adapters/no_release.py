"""The release source while no release manifest is configured: ai-service is not ready."""

from supportiq_ai_service.release.domain import LoadedRelease


class NoReleaseSource:
    """Implement the `ReleaseSource` port for an instance without a release manifest.

    ai-service has no fallback model (ADR-0021, Where the code of main goes), so without a
    verified release it answers `503 not-ready`, and `backend` falls back to manual handling.
    """

    def current(self) -> LoadedRelease | None:
        """Return None: no release is loaded."""
        return None
