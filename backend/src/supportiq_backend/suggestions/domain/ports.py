"""The ports of suggestions (ARCH-25, ARCH-26).

`tickets` implements `SuggestionTickets` and `TicketAuthority`, so suggestions reads and
changes ticket rows without importing tickets, which depends on it (backend ticket workflow
design, Feature modules).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from supportiq_backend.accounts import AccountId, CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import TraceId
from supportiq_backend.pseudonymization import MapTicketId, MessageToPseudonymize
from supportiq_backend.suggestions.domain.ai_results import (
    AssetVersions,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    SuggestionRequest,
)
from supportiq_backend.suggestions.domain.completions import PartCompletion
from supportiq_backend.suggestions.domain.jobs import ClaimedJob, LockedJob
from supportiq_backend.suggestions.domain.kb_documents import (
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionTag,
)
from supportiq_backend.suggestions.domain.labels import IntentLabel
from supportiq_backend.suggestions.domain.progress import SuggestionProgress
from supportiq_backend.suggestions.domain.suggestions import (
    Suggestion,
    SuggestionId,
    SuggestionTicketId,
    SuggestionTrigger,
)


@dataclass(frozen=True, slots=True)
class NewSuggestion:
    """A suggestion to insert with its two pending parts and its queued job.

    Attributes:
        suggestion_id: The identifier.
        ticket_id: The ticket.
        trigger: Why it is created.
        intent_override: The intent that staff chose, when they chose one.
        requested_by: The account that asked; absent for `ticket_created`.
        created_at: When it is created.
        trace_id: The trace of the request that created it.
    """

    suggestion_id: SuggestionId
    ticket_id: SuggestionTicketId
    trigger: SuggestionTrigger
    intent_override: IntentLabel | None
    requested_by: AccountId | None
    created_at: datetime
    trace_id: TraceId


@dataclass(frozen=True, slots=True, repr=False)
class TicketMessage:
    """What a job needs of its ticket. The message is Confidential.

    Attributes:
        ticket_id: The ticket.
        message: The customer's message, as written.
        created_at: When the customer asked; every suggestion uses it as `as_of`.
        customer_id: The customer.
        order_id: The ticket's order; absent for an imported ticket without one.
    """

    ticket_id: SuggestionTicketId
    message: str
    created_at: datetime
    customer_id: CustomerId
    order_id: OrderId | None


@dataclass(frozen=True, slots=True)
class TicketForSuggestion:
    """A ticket row locked with `SELECT ... FOR UPDATE`, as suggestions sees it.

    Attributes:
        current_suggestion_id: The current suggestion, when there is one.
        is_open: Whether the ticket is `open`.
        is_assisted: Whether its handling mode is `assisted`.
        status_name: The ticket status, for the detail of a refusal.
    """

    current_suggestion_id: SuggestionId | None
    is_open: bool
    is_assisted: bool
    status_name: str


class SuggestionTickets(Protocol):
    """The ticket rows that suggestions reads and links, implemented by tickets."""

    async def lock_ticket(self, ticket_id: SuggestionTicketId) -> TicketForSuggestion | None:
        """Lock a ticket row for the rest of the transaction.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.
        """
        ...

    async def read_ticket(self, ticket_id: SuggestionTicketId) -> TicketForSuggestion | None:
        """Read a ticket row without a lock, for the re-reads of a stream.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.
        """
        ...

    async def set_current_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Make a suggestion the ticket's current one.

        Args:
            ticket_id: The ticket, locked by the transaction.
            suggestion_id: The new suggestion.
        """
        ...

    async def load_ticket_message(self, ticket_id: SuggestionTicketId) -> TicketMessage | None:
        """Load what a job needs of its ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The message and its context, or None when the ticket is unknown.
        """
        ...


class TicketAuthority(Protocol):
    """Set the authority flag in the transaction that stores a result (FR-06)."""

    async def set_authority_required(self, ticket_id: SuggestionTicketId) -> None:
        """Set `is_authority_required`; it is never cleared.

        Args:
            ticket_id: The ticket, locked by the transaction.
        """
        ...


class SuggestionStore(Protocol):
    """Insert suggestions and read them back, for the operations of the console."""

    async def cancel_pending_suggestions(
        self, ticket_id: SuggestionTicketId, completed_at: datetime
    ) -> tuple[SuggestionId, ...]:
        """Cancel every pending part of the ticket's suggestions and end their jobs.

        Args:
            ticket_id: The ticket, locked by the transaction.
            completed_at: When the parts were cancelled.

        Returns:
            The suggestions that had a pending part.
        """
        ...

    async def insert_suggestion(self, suggestion: NewSuggestion) -> None:
        """Insert a suggestion, its two pending parts, and its queued job.

        Args:
            suggestion: The suggestion.
        """
        ...

    async def load_suggestion(self, suggestion_id: SuggestionId) -> Suggestion | None:
        """Load one suggestion with both parts.

        Args:
            suggestion_id: The suggestion.

        Returns:
            The suggestion, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored part breaks an invariant, a stored text is no value
                of its enum, or a stored result no longer matches the contract: a defect.
        """
        ...

    async def load_progress(self, suggestion_id: SuggestionId) -> SuggestionProgress | None:
        """Load the part statuses of one suggestion, and nothing else.

        Args:
            suggestion_id: The suggestion.

        Returns:
            The statuses, or None when the suggestion is unknown.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        ...

    async def load_suggestions(
        self, suggestion_ids: frozenset[SuggestionId]
    ) -> Mapping[SuggestionId, Suggestion]:
        """Load several suggestions in a fixed number of queries.

        Args:
            suggestion_ids: The suggestions.

        Returns:
            Each known suggestion by its ID.

        Raises:
            UnexpectedFailureError: A stored part breaks an invariant, a stored text is no value
                of its enum, or a stored result no longer matches the contract: a defect.
        """
        ...


class SuggestionJobStore(Protocol):
    """Claim jobs and store their results, each in its own transaction (ADR-0011)."""

    async def claim_next(self, now: datetime, lease_expires_at: datetime) -> ClaimedJob | None:
        """Claim the oldest claimable job in one statement, with `FOR UPDATE SKIP LOCKED`.

        A job is claimable when it is `queued`, or `running` with an expired lease. The claim
        sets it `running`, adds one to its attempt number, and sets its lease.

        Args:
            now: The current time.
            lease_expires_at: When the new lease expires.

        Returns:
            The claimed job, or None when nothing is claimable.
        """
        ...

    async def lock_job(self, suggestion_id: SuggestionId) -> LockedJob | None:
        """Lock a job row for the rest of the transaction.

        Args:
            suggestion_id: The suggestion of the job.

        Returns:
            The job, or None when it is unknown.

        Raises:
            UnexpectedFailureError: The stored state is no value of `JobState`: a defect.
        """
        ...

    async def save_request(self, suggestion_id: SuggestionId, request: SuggestionRequest) -> None:
        """Write the request of a suggestion when it is still absent; it is written once.

        A later attempt sends the same request, because pseudonymization reuses the stored map
        and commerce data is read-only, so keeping the first one loses nothing.

        Args:
            suggestion_id: The suggestion.
            request: The request.
        """
        ...

    async def complete_part(self, suggestion_id: SuggestionId, completion: PartCompletion) -> bool:
        """Write the final state of a part that is still `pending`.

        Args:
            suggestion_id: The suggestion.
            completion: What to write.

        Returns:
            True when the part was pending and is now final; false when it was already final.
        """
        ...

    async def finish_job(self, suggestion_id: SuggestionId, now: datetime) -> None:
        """Set a job `done`.

        Args:
            suggestion_id: The suggestion of the job.
            now: The current time.
        """
        ...


class AiService(Protocol):
    """The calls of backend to ai-service, through its contract 1.0.0 (ARCH-02)."""

    async def analyze(self, request: SuggestionRequest) -> ReceivedAnalysis:
        """Run the pipeline up to routing (`createAnalysis`).

        Args:
            request: The request.

        Returns:
            The analysis as received.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        ...

    async def draft(self, request: SuggestionRequest) -> ReceivedDraftOutcome:
        """Run the whole pipeline (`createDraft`).

        Args:
            request: The request.

        Returns:
            The draft outcome as received.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        ...

    async def fetch_asset_versions(self) -> AssetVersions:
        """Read the versions of the release that ai-service serves (`getAssetVersions`).

        Returns:
            The versions.

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: A `4xx`, or a response outside the contract.
        """
        ...

    async def fetch_kb_document_version(
        self, document_id: KbDocumentId, version: KbDocumentVersionTag
    ) -> KbDocumentVersion | None:
        """Read one version of a KB document in full (`getKbDocumentVersion`).

        Args:
            document_id: The KB document.
            version: The version of the document.

        Returns:
            The document version, or None when the loaded KB has no such version (`404`).

        Raises:
            AiServiceUnavailableError: A timeout, a connection error, or a `5xx`.
            AiServiceContractError: Another `4xx`, or a response outside the contract.
        """
        ...


class MessagePseudonymizer(Protocol):
    """The first function of the public API of pseudonymization (ADR-0010, item 6)."""

    async def pseudonymize(self, message: MessageToPseudonymize) -> str:
        """Return the pseudonymized text of a ticket's message.

        Args:
            message: The message and its records.

        Returns:
            The pseudonymized text.

        Raises:
            PseudonymizationError: Pseudonymization failed; nothing may be sent.
            DatabaseUnavailableError: A storage error, which is no pseudonymization failure.
        """
        ...


class PseudonymRestorer(Protocol):
    """The second function of the public API of pseudonymization."""

    async def restore(self, ticket_id: MapTicketId, texts: tuple[str, ...]) -> tuple[str, ...]:
        """Restore the pseudonyms of a ticket in some texts.

        Args:
            ticket_id: The ticket.
            texts: AI texts with placeholders.

        Returns:
            The restored texts, in the same order.
        """
        ...


class SuggestionQueue(Protocol):
    """Tell the claim loop of this replica that a new job waits (ARCH-41)."""

    def notify_new_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Wake the claim loop and cancel the running calls of the ticket's older suggestions.

        The wake-up holds no state: if it is lost, the next poll finds the job.

        Args:
            ticket_id: The ticket.
            suggestion_id: Its new current suggestion, committed already.
        """
        ...


class ProgressNotifier(Protocol):
    """Wake the streams of a ticket on this replica after a commit (ADR-0022, statement 4)."""

    def notify_progress(self, ticket_id: SuggestionTicketId) -> None:
        """Wake every stream of the ticket; a lost wake-up only waits for the next re-read.

        Args:
            ticket_id: The ticket whose suggestion or part statuses changed, committed already.
        """
        ...
