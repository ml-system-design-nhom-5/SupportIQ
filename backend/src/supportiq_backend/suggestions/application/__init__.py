"""Use cases of suggestions: starting suggestions, the claim loop, and the job runner."""

from supportiq_backend.suggestions.application.ai_service_failures import (
    AiServiceOperation,
    record_ai_service_failure,
)
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
    "AiServiceOperation",
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
    "record_ai_service_failure",
]
