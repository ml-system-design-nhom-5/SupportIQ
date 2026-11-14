"""The pipeline of an instance without a release manifest: ai-service is not ready."""

from supportiq_ai_service.release import LoadedRelease, ReleaseNotLoadedError
from supportiq_ai_service.suggestions.domain import Analysis, DraftOutcome, SuggestionInput


class UnavailablePipeline:
    """Implement the `SuggestionPipeline` port while no pipeline is wired to a release.

    ai-service has no fallback model (ADR-0021, Where the code of main goes), so it computes
    nothing and refuses with `503 not-ready`, and `backend` falls back to manual handling.
    """

    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        """Refuse the analysis.

        Args:
            request: The validated request.
            release: The loaded release.

        Raises:
            ReleaseNotLoadedError: Always.
        """
        del request, release
        raise ReleaseNotLoadedError

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        """Refuse the draft.

        Args:
            request: The validated request.
            release: The loaded release.

        Raises:
            ReleaseNotLoadedError: Always.
        """
        del request, release
        raise ReleaseNotLoadedError
