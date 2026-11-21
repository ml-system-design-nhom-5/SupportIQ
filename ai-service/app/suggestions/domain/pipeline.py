"""The port of the pipeline that computes analyses and drafts, and the errors of suggestions."""

from typing import Protocol

from app.platform import InvalidRequestError
from app.release import LoadedRelease
from app.suggestions.domain.analysis import Analysis
from app.suggestions.domain.draft import DraftOutcome
from app.suggestions.domain.request import SuggestionInput


class SuggestionPipeline(Protocol):
    """Run the pipeline of one loaded release (ADR-0005)."""

    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        """Run the pipeline up to routing, without the LLM.

        Args:
            request: The validated request.
            release: The loaded release whose assets the pipeline uses.

        Returns:
            The analysis.
        """
        ...

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        """Run the whole pipeline, with the LLM when the routing allows a draft.

        Args:
            request: The validated request.
            release: The loaded release whose assets the pipeline uses.

        Returns:
            The draft outcome. A failure of the LLM step is an outcome, never an error.
        """
        ...


class UnknownKbVersionError(InvalidRequestError):
    """The request names a KB version other than the loaded one (DATA-56)."""

    def __init__(self) -> None:
        """Build the error with the detail of the contract's example."""
        super().__init__("The kb_version is not the KB version that ai-service has loaded.")
