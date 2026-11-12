"""Use cases of suggestions: starting suggestions, the claim loop, and the job runner."""

from supportiq_backend.suggestions.application.claim_loop import ClaimLoop, ClaimStores, JobRunner
from supportiq_backend.suggestions.application.create import (
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
)
from supportiq_backend.suggestions.application.job_runner import (
    JobRunnerPorts,
    JobStores,
    SuggestionJobRunner,
)
from supportiq_backend.suggestions.application.start import (
    StartedSuggestion,
    SuggestionStart,
    SuggestionStarter,
    SuggestionStarterPorts,
)

__all__ = [
    "ClaimLoop",
    "ClaimStores",
    "CreateSuggestion",
    "CreateSuggestionPorts",
    "CreateSuggestionStores",
    "JobRunner",
    "JobRunnerPorts",
    "JobStores",
    "StartedSuggestion",
    "SuggestionJobRunner",
    "SuggestionStart",
    "SuggestionStarter",
    "SuggestionStarterPorts",
]
