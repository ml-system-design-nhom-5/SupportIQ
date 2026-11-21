"""Use cases of suggestions: starting suggestions, the claim loop, the job runner, and reads."""

from app.suggestions.application.ai_service_failures import (
    AiServiceOperation,
    record_ai_service_failure,
)
from app.suggestions.application.ai_service_reads import (
    AiServiceReadPorts,
    GetAdminVersions,
    GetConsoleKbDocumentVersion,
    VersionsInUse,
)
from app.suggestions.application.claim_loop import ClaimLoop, ClaimStores, JobRunner
from app.suggestions.application.create import (
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
)
from app.suggestions.application.job_runner import (
    JobRunnerPorts,
    JobStores,
    SuggestionJobRunner,
)
from app.suggestions.application.start import (
    StartedSuggestion,
    SuggestionStart,
    SuggestionStarter,
    SuggestionStarterPorts,
)
from app.suggestions.application.suggestion_progress import (
    ProgressSignals,
    ProgressStores,
    WatchProgressPorts,
    WatchSuggestionProgress,
)

__all__ = [
    "AiServiceOperation",
    "AiServiceReadPorts",
    "ClaimLoop",
    "ClaimStores",
    "CreateSuggestion",
    "CreateSuggestionPorts",
    "CreateSuggestionStores",
    "GetAdminVersions",
    "GetConsoleKbDocumentVersion",
    "JobRunner",
    "JobRunnerPorts",
    "JobStores",
    "ProgressSignals",
    "ProgressStores",
    "StartedSuggestion",
    "SuggestionJobRunner",
    "SuggestionStart",
    "SuggestionStarter",
    "SuggestionStarterPorts",
    "VersionsInUse",
    "WatchProgressPorts",
    "WatchSuggestionProgress",
    "record_ai_service_failure",
]
