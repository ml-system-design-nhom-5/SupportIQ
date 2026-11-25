"""Public API of suggestions: `createAnalysis` and `createDraft` (ARCH-17).

suggestions is an interim feature named after the contract's tag. It holds the use cases,
the port of the pipeline, and the types of its results, until the `ai-service` pipeline
design splits the pipeline into its features (README.md, Open questions).
"""

from app.suggestions.application import (
    CreateAnalysis,
    CreateDraft,
    PipelinePorts,
    PipelineValues,
    ReleasePipeline,
)
from app.suggestions.domain import (
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
    "PipelinePorts",
    "PipelineValues",
    "ReleasePipeline",
    "SuggestionInput",
    "SuggestionPipeline",
    "UnknownKbVersionError",
]
