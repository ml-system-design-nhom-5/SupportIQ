"""The use cases of `createAnalysis` and `createDraft` (ADR-0005, DATA-56).

Each one needs a verified release, refuses a KB version other than the loaded one, and then
runs the pipeline of that release. Neither has a side effect, so `backend` may repeat a call.
"""

from supportiq_ai_service.release import LoadedRelease, ReleaseSource, require_release
from supportiq_ai_service.suggestions.domain import (
    Analysis,
    DraftOutcome,
    SuggestionInput,
    SuggestionPipeline,
    UnknownKbVersionError,
)


class CreateAnalysis:
    """Run the pipeline up to routing, without the LLM (`createAnalysis`)."""

    def __init__(self, release_source: ReleaseSource, pipeline: SuggestionPipeline) -> None:
        """Keep the source of the loaded release and the pipeline.

        Args:
            release_source: Where the loaded release comes from.
            pipeline: The pipeline that computes the analysis.
        """
        self._release_source = release_source
        self._pipeline = pipeline

    async def execute(self, request: SuggestionInput) -> Analysis:
        """Analyze the customer's message.

        Args:
            request: The validated request.

        Returns:
            The analysis.

        Raises:
            ReleaseNotLoadedError: No verified release is loaded.
            UnknownKbVersionError: The request names another KB version.
        """
        release = _release_for(request, self._release_source)
        return await self._pipeline.analyze(request, release)


class CreateDraft:
    """Run the whole pipeline (`createDraft`)."""

    def __init__(self, release_source: ReleaseSource, pipeline: SuggestionPipeline) -> None:
        """Keep the source of the loaded release and the pipeline.

        Args:
            release_source: Where the loaded release comes from.
            pipeline: The pipeline that computes the draft outcome.
        """
        self._release_source = release_source
        self._pipeline = pipeline

    async def execute(self, request: SuggestionInput) -> DraftOutcome:
        """Analyze the customer's message and draft a reply when the routing allows it.

        Args:
            request: The validated request.

        Returns:
            The draft outcome.

        Raises:
            ReleaseNotLoadedError: No verified release is loaded.
            UnknownKbVersionError: The request names another KB version.
        """
        release = _release_for(request, self._release_source)
        return await self._pipeline.draft(request, release)


def _release_for(request: SuggestionInput, release_source: ReleaseSource) -> LoadedRelease:
    release = require_release(release_source)
    if request.kb_version is not None and request.kb_version != release.versions.kb_version:
        raise UnknownKbVersionError
    return release
