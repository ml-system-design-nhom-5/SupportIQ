"""Public API of suggestions: `createAnalysis` and `createDraft` (ARCH-17).

suggestions is an interim feature named after the contract's tag. It holds the use cases,
the port of the pipeline, and the types of its results, until the `ai-service` pipeline
design splits the pipeline into its features (README.md, Open questions).
"""

from supportiq_ai_service.suggestions.application import CreateAnalysis, CreateDraft
from supportiq_ai_service.suggestions.domain import (
    Analysis,
    DraftOutcome,
    SuggestionInput,
    SuggestionPipeline,
    UnknownKbVersionError,
)

__all__ = [
    "Analysis",
    "CreateAnalysis",
    "CreateDraft",
    "DraftOutcome",
    "SuggestionInput",
    "SuggestionPipeline",
    "UnknownKbVersionError",
]
