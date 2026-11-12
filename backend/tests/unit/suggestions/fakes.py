"""In-memory fakes of the ports of suggestions (ARCH-27, TEST-09).

The fakes keep suggestions as domain values and apply the same rules as the PostgreSQL
adapters: a final part never changes, a request is written once, and a done job is never
claimed.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from supportiq_backend.platform import BackendError
from supportiq_backend.pseudonymization import MapTicketId, MessageToPseudonymize
from supportiq_backend.suggestions import (
    AiServiceUnavailableError,
    AnalysisState,
    AssetVersions,
    CancelledPart,
    ClaimedJob,
    DraftState,
    JobState,
    LockedJob,
    NewSuggestion,
    PartCompletion,
    PendingPart,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    Suggestion,
    SuggestionId,
    SuggestionPart,
    SuggestionRequest,
    SuggestionTicketId,
    TicketForSuggestion,
    TicketMessage,
    UnavailablePart,
)
from tests.unit.suggestions.builders import build_versions


@dataclass(slots=True)
class FakeJob:
    """A job of the fake job store.

    Attributes:
        ticket_id: The ticket of the suggestion.
        state: The state.
        attempt_number: The attempt of the latest claim.
    """

    ticket_id: SuggestionTicketId
    state: JobState = JobState.QUEUED
    attempt_number: int = 0


@dataclass(slots=True)
class FakeSuggestionData:
    """The suggestions and jobs that the fake stores share, like one database.

    Attributes:
        suggestions: The suggestions by ID.
        jobs: The jobs by suggestion ID.
        requests: The stored requests by suggestion ID.
        completions: Every completion that was written, in order.
        state_by_body: The state that a stored result body stands for, as the adapter would
            parse it; a test registers the bodies it stores.
    """

    suggestions: dict[SuggestionId, Suggestion] = field(
        default_factory=dict[SuggestionId, Suggestion]
    )
    jobs: dict[SuggestionId, FakeJob] = field(default_factory=dict[SuggestionId, FakeJob])
    requests: dict[SuggestionId, SuggestionRequest] = field(
        default_factory=dict[SuggestionId, SuggestionRequest]
    )
    completions: list[PartCompletion] = field(default_factory=list[PartCompletion])
    state_by_body: dict[str, AnalysisState | DraftState] = field(
        default_factory=dict[str, AnalysisState | DraftState]
    )

    def state_of(self, completion: PartCompletion) -> AnalysisState | DraftState:
        """Return the state that a completion writes."""
        if completion.result_body is None:
            return UnavailablePart(completion.reason_codes[0])
        return self.state_by_body[completion.result_body]

    def add(self, suggestion: Suggestion, *, state: JobState = JobState.QUEUED) -> None:
        """Add a stored suggestion and its job."""
        self.suggestions[suggestion.suggestion_id] = suggestion
        self.jobs[suggestion.suggestion_id] = FakeJob(suggestion.ticket_id, state)


@dataclass(slots=True)
class FakeSuggestionStore:
    """Implement `SuggestionStore` on the shared data, or fail with a given error."""

    data: FakeSuggestionData = field(default_factory=FakeSuggestionData)
    failure: BackendError | None = None

    async def cancel_pending_suggestions(
        self, ticket_id: SuggestionTicketId, completed_at: datetime
    ) -> tuple[SuggestionId, ...]:
        """Cancel the pending parts of the ticket's suggestions and end their jobs."""
        del completed_at
        self._fail_when_chosen()
        cancelled: list[SuggestionId] = []
        for suggestion_id, suggestion in tuple(self.data.suggestions.items()):
            if suggestion.ticket_id != ticket_id:
                continue
            self.data.jobs[suggestion_id].state = JobState.DONE
            if suggestion.has_pending_part:
                cancelled.append(suggestion_id)
                self.data.suggestions[suggestion_id] = replace(
                    suggestion,
                    analysis=_cancel(suggestion.analysis),
                    draft=_cancel(suggestion.draft),
                )
        return tuple(sorted(cancelled))

    async def insert_suggestion(self, suggestion: NewSuggestion) -> None:
        """Insert a suggestion with two pending parts and a queued job."""
        self._fail_when_chosen()
        self.data.add(
            Suggestion(
                suggestion_id=suggestion.suggestion_id,
                ticket_id=suggestion.ticket_id,
                trigger=suggestion.trigger,
                intent_override=suggestion.intent_override,
                requested_by=suggestion.requested_by,
                created_at=suggestion.created_at,
                trace_id=suggestion.trace_id,
                analysis=PendingPart(),
                draft=PendingPart(),
                sent_order_context=None,
            )
        )

    async def load_suggestion(self, suggestion_id: SuggestionId) -> Suggestion | None:
        """Load one suggestion."""
        self._fail_when_chosen()
        return self.data.suggestions.get(suggestion_id)

    async def load_suggestions(
        self, suggestion_ids: frozenset[SuggestionId]
    ) -> Mapping[SuggestionId, Suggestion]:
        """Load several suggestions."""
        self._fail_when_chosen()
        return {
            suggestion_id: suggestion
            for suggestion_id, suggestion in self.data.suggestions.items()
            if suggestion_id in suggestion_ids
        }

    def _fail_when_chosen(self) -> None:
        if self.failure is not None:
            raise self.failure


@dataclass(slots=True)
class FakeSuggestionJobStore:
    """Implement `SuggestionJobStore` on the shared data."""

    data: FakeSuggestionData = field(default_factory=FakeSuggestionData)
    claim_failure: Exception | None = None

    async def claim_next(self, now: datetime, lease_expires_at: datetime) -> ClaimedJob | None:
        """Claim the first queued job, in insertion order."""
        del now, lease_expires_at
        if self.claim_failure is not None:
            raise self.claim_failure
        for suggestion_id, job in self.data.jobs.items():
            if job.state is JobState.QUEUED:
                job.state = JobState.RUNNING
                job.attempt_number += 1
                return ClaimedJob(suggestion_id, job.ticket_id, job.attempt_number)
        return None

    async def lock_job(self, suggestion_id: SuggestionId) -> LockedJob | None:
        """Return the job."""
        job = self.data.jobs.get(suggestion_id)
        return None if job is None else LockedJob(job.state, job.attempt_number)

    async def save_request(self, suggestion_id: SuggestionId, request: SuggestionRequest) -> None:
        """Keep the first request of a suggestion."""
        self.data.requests.setdefault(suggestion_id, request)

    async def complete_part(self, suggestion_id: SuggestionId, completion: PartCompletion) -> bool:
        """Write a pending part, as the adapter does with the parsed result."""
        suggestion = self.data.suggestions[suggestion_id]
        current = (
            suggestion.analysis if completion.part is SuggestionPart.ANALYSIS else suggestion.draft
        )
        if not isinstance(current, PendingPart):
            return False
        self.data.completions.append(completion)
        state = self.data.state_of(completion)
        self.data.suggestions[suggestion_id] = (
            replace(suggestion, analysis=state)
            if completion.part is SuggestionPart.ANALYSIS
            else replace(suggestion, draft=state)
        )
        return True

    async def finish_job(self, suggestion_id: SuggestionId, now: datetime) -> None:
        """Set the job done."""
        del now
        self.data.jobs[suggestion_id].state = JobState.DONE


@dataclass(slots=True)
class FakeTicketLinks:
    """Implement `SuggestionTickets` and `TicketAuthority` for a few tickets."""

    tickets: dict[SuggestionTicketId, TicketForSuggestion] = field(
        default_factory=dict[SuggestionTicketId, TicketForSuggestion]
    )
    messages: dict[SuggestionTicketId, TicketMessage] = field(
        default_factory=dict[SuggestionTicketId, TicketMessage]
    )
    authority_required: set[SuggestionTicketId] = field(default_factory=set[SuggestionTicketId])

    async def lock_ticket(self, ticket_id: SuggestionTicketId) -> TicketForSuggestion | None:
        """Return the ticket."""
        return self.tickets.get(ticket_id)

    async def set_current_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Make the suggestion current."""
        ticket = self.tickets.get(ticket_id) or TicketForSuggestion(None, True, True, "open")
        self.tickets[ticket_id] = replace(ticket, current_suggestion_id=suggestion_id)

    async def load_ticket_message(self, ticket_id: SuggestionTicketId) -> TicketMessage | None:
        """Return the message of the ticket."""
        return self.messages.get(ticket_id)

    async def set_authority_required(self, ticket_id: SuggestionTicketId) -> None:
        """Set the flag."""
        self.authority_required.add(ticket_id)


@dataclass(slots=True)
class RecordingSuggestionQueue:
    """Keep the notifications of the claim loop."""

    notifications: list[tuple[SuggestionTicketId, SuggestionId]] = field(
        default_factory=list[tuple[SuggestionTicketId, SuggestionId]]
    )

    def notify_new_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Keep the notification."""
        self.notifications.append((ticket_id, suggestion_id))


@dataclass(slots=True)
class FakeAiService:
    """Answer with chosen results or errors, and keep every request it received.

    A test that leaves a result unset gets the default error, so no call can succeed by
    accident.
    """

    analysis_result: ReceivedAnalysis | BackendError = field(
        default_factory=AiServiceUnavailableError
    )
    draft_result: ReceivedDraftOutcome | BackendError = field(
        default_factory=AiServiceUnavailableError
    )
    versions: AssetVersions | BackendError = field(default_factory=build_versions)
    analysis_requests: list[SuggestionRequest] = field(default_factory=list[SuggestionRequest])
    draft_requests: list[SuggestionRequest] = field(default_factory=list[SuggestionRequest])
    version_reads: int = 0

    @property
    def requests(self) -> tuple[SuggestionRequest, ...]:
        """Return every request of both calls."""
        return (*self.analysis_requests, *self.draft_requests)

    async def analyze(self, request: SuggestionRequest) -> ReceivedAnalysis:
        """Answer the analysis call."""
        self.analysis_requests.append(request)
        if isinstance(self.analysis_result, BackendError):
            raise self.analysis_result
        return self.analysis_result

    async def draft(self, request: SuggestionRequest) -> ReceivedDraftOutcome:
        """Answer the draft call."""
        self.draft_requests.append(request)
        if isinstance(self.draft_result, BackendError):
            raise self.draft_result
        return self.draft_result

    async def fetch_asset_versions(self) -> AssetVersions:
        """Count the read of the loaded versions and answer it."""
        self.version_reads += 1
        if isinstance(self.versions, BackendError):
            raise self.versions
        return self.versions


@dataclass(slots=True)
class FakePseudonymizer:
    """Pseudonymize by replacing chosen values, or fail with a given error."""

    replacements: Mapping[str, str] = field(default_factory=dict[str, str])
    failure: BackendError | None = None
    messages: list[MessageToPseudonymize] = field(default_factory=list[MessageToPseudonymize])

    async def pseudonymize(self, message: MessageToPseudonymize) -> str:
        """Return the message with each chosen value replaced."""
        self.messages.append(message)
        if self.failure is not None:
            raise self.failure
        text = message.message
        for original, pseudonym in self.replacements.items():
            text = text.replace(original, pseudonym)
        return text


@dataclass(slots=True)
class FakeRestorer:
    """Restore pseudonyms from a fixed map."""

    original_by_pseudonym: Mapping[str, str] = field(default_factory=dict[str, str])

    async def restore(self, ticket_id: MapTicketId, texts: tuple[str, ...]) -> tuple[str, ...]:
        """Replace each pseudonym of the map."""
        del ticket_id
        restored: list[str] = []
        for text in texts:
            for pseudonym, original in self.original_by_pseudonym.items():
                text = text.replace(pseudonym, original)  # noqa: PLW2901  # a fake restorer
            restored.append(text)
        return tuple(restored)


def _cancel(state: AnalysisState | DraftState) -> AnalysisState | DraftState:
    return CancelledPart() if isinstance(state, PendingPart) else state
