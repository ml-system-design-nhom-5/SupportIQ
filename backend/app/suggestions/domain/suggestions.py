"""Suggestions and their two parts (contracts v1 design, Suggestion lifecycle).

A suggestion is everything the AI produced for a ticket in one run. Its analysis and its
draft each have their own status, because the two calls return at different times.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType, assert_never

from app.accounts import AccountId
from app.platform import TraceId
from app.suggestions.domain.ai_results import (
    Analysis,
    DraftOutcome,
    DraftReady,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OrderContext,
)
from app.suggestions.domain.errors import (
    NoIntentKnownError,
    NothingToRetryError,
    SuggestionPendingError,
)
from app.suggestions.domain.labels import AiReasonCode, IntentLabel

# A suggestion, as a canonical UUID text. Internal.
SuggestionId = NewType("SuggestionId", str)
# The ticket of a suggestion, such as `TCK-1042`. Internal.
SuggestionTicketId = NewType("SuggestionTicketId", str)


class SuggestionTrigger(StrEnum):
    """Why a suggestion was created (contracts v1 design, Suggestion lifecycle)."""

    TICKET_CREATED = "ticket_created"
    INTENT_OVERRIDE = "intent_override"
    KB_VERSION_CHANGED = "kb_version_changed"
    RETRY = "retry"


class SuggestionPart(StrEnum):
    """The two parts of a suggestion."""

    ANALYSIS = "analysis"
    DRAFT = "draft"


class PartStatus(StrEnum):
    """Every status a part can have, as `suggestion_parts.status` holds it."""

    PENDING = "pending"
    READY = "ready"
    DRAFT_READY = "draft_ready"
    ABSTAINED = "abstained"
    ESCALATION_RECOMMENDED = "escalation_recommended"
    LLM_UNAVAILABLE = "llm_unavailable"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PendingPart:
    """A part that waits for its result."""


@dataclass(frozen=True, slots=True)
class CancelledPart:
    """A part of a superseded suggestion; set only by backend and never shown."""


@dataclass(frozen=True, slots=True)
class UnavailablePart:
    """A part that backend could not get from ai-service.

    Attributes:
        reason_code: `ai_service_unavailable` or `pseudonymization_failed`.
    """

    reason_code: AiReasonCode


type AnalysisState = PendingPart | Analysis | UnavailablePart | CancelledPart
type DraftState = PendingPart | DraftOutcome | UnavailablePart | CancelledPart


@dataclass(frozen=True, slots=True, repr=False)
class Suggestion:
    """One suggestion of a ticket, with the state of both parts.

    Attributes:
        suggestion_id: The identifier.
        ticket_id: The ticket.
        trigger: Why it was created.
        intent_override: The intent that staff chose, when they chose one.
        requested_by: The account that asked for it; absent for `ticket_created`.
        created_at: When it was created.
        trace_id: The trace of its job.
        analysis: The analysis part.
        draft: The draft part.
        sent_order_context: The order context sent to ai-service; absent before the request
            was stored, or for a ticket without an order. Confidential.
    """

    suggestion_id: SuggestionId
    ticket_id: SuggestionTicketId
    trigger: SuggestionTrigger
    intent_override: IntentLabel | None
    requested_by: AccountId | None
    created_at: datetime
    trace_id: TraceId
    analysis: AnalysisState
    draft: DraftState
    sent_order_context: OrderContext | None

    @property
    def has_pending_part(self) -> bool:
        """Tell whether a part still waits for its result."""
        return isinstance(self.analysis, PendingPart) or isinstance(self.draft, PendingPart)

    @property
    def known_intent(self) -> IntentLabel | None:
        """Return the intent that staff can correct: the override, or the analysed intent.

        An intent is known when the analysis is ready or the suggestion already carries an
        override (contracts v1 design, Authority rule).
        """
        if self.intent_override is not None:
            return self.intent_override
        if isinstance(self.analysis, Analysis):
            return self.analysis.intent.label
        return None

    @property
    def predicted_intent(self) -> ModelIntent | None:
        """Return the model's intent of a ready analysis, when the model chose it."""
        if isinstance(self.analysis, Analysis) and isinstance(self.analysis.intent, ModelIntent):
            return self.analysis.intent
        return None

    @property
    def ready_draft(self) -> DraftReady | None:
        """Return the draft outcome when its draft is ready."""
        return self.draft if isinstance(self.draft, DraftReady) else None

    @property
    def kb_version(self) -> str | None:
        """Return the KB version that produced the suggestion, once a part has a result."""
        if isinstance(self.analysis, Analysis):
            return self.analysis.versions.kb_version
        if isinstance(self.draft, DraftReady | NoDraft):
            return self.draft.details.versions.kb_version
        return None

    @property
    def staff_note(self) -> str | None:
        """Return the staff note of the draft outcome, with placeholders, when it has one."""
        if isinstance(self.draft, DraftReady | NoDraft):
            return self.draft.details.staff_note
        return None

    @property
    def can_retry(self) -> bool:
        """Tell whether staff can retry the AI (contracts v1 design, Retry after an AI failure).

        A part is `unavailable` with `ai_service_unavailable`, or the draft is
        `llm_unavailable`, and nothing is pending. A suggestion that failed pseudonymization is
        never retried, because pseudonymization is deterministic.
        """
        if self.has_pending_part:
            return False
        return (
            _is_ai_service_unavailable(self.analysis)
            or _is_ai_service_unavailable(self.draft)
            or (
                isinstance(self.draft, NoDraft)
                and self.draft.status is NoDraftStatus.LLM_UNAVAILABLE
            )
        )


def choose_view_trigger(
    suggestion: Suggestion, *, is_first_view: bool, loaded_kb_version: str | None
) -> SuggestionTrigger | None:
    """Decide whether a view of an open, assisted ticket starts a suggestion.

    On the first view, a suggestion made with another KB version than the one ai-service
    has loaded is run again (`kb_version_changed`). On any view, a failure that a retry can
    fix is retried (`retry`). A pending suggestion blocks both, so opening the ticket again
    creates no duplicate (contracts v1 design, Retry after an AI failure).

    Args:
        suggestion: The ticket's current suggestion.
        is_first_view: Whether this view starts the handling clock.
        loaded_kb_version: The KB version that ai-service reports; None when it did not
            answer in time.

    Returns:
        The trigger of the suggestion to start, or None.
    """
    if suggestion.has_pending_part:
        return None
    used_kb_version = suggestion.kb_version
    if (
        is_first_view
        and loaded_kb_version is not None
        and used_kb_version is not None
        and used_kb_version != loaded_kb_version
    ):
        return SuggestionTrigger.KB_VERSION_CHANGED
    if suggestion.can_retry:
        return SuggestionTrigger.RETRY
    return None


def plan_requested_suggestion(
    current: Suggestion | None, intent_override: IntentLabel | None
) -> tuple[SuggestionTrigger, IntentLabel | None]:
    """Decide what `createSuggestion` starts, after the ticket checks passed.

    With an override, staff confirm or correct the intent, which needs a known intent. Without
    one, the request is a retry, which repeats the input of the failed suggestion, its
    override included (contracts v1 design, Retry after an AI failure).

    Args:
        current: The ticket's current suggestion, when it has one.
        intent_override: The intent of the request, when it has one.

    Returns:
        The trigger and the override of the new suggestion.

    Raises:
        SuggestionPendingError: No intent is known yet and a part is pending.
        NoIntentKnownError: No intent is known and nothing is pending.
        NothingToRetryError: A retry while nothing can be retried.
    """
    if intent_override is not None:
        if current is not None and current.known_intent is not None:
            return SuggestionTrigger.INTENT_OVERRIDE, intent_override
        if current is not None and current.has_pending_part:
            raise SuggestionPendingError
        raise NoIntentKnownError
    if current is None or not current.can_retry:
        raise NothingToRetryError
    return SuggestionTrigger.RETRY, current.intent_override


def get_part_status(state: AnalysisState | DraftState) -> PartStatus:
    """Return the stored status of a part state.

    Args:
        state: The state of an analysis or a draft part.

    Returns:
        The status.
    """
    match state:
        case PendingPart():
            status = PartStatus.PENDING
        case CancelledPart():
            status = PartStatus.CANCELLED
        case UnavailablePart():
            status = PartStatus.UNAVAILABLE
        case Analysis():
            status = PartStatus.READY
        case DraftReady():
            status = PartStatus.DRAFT_READY
        case NoDraft():
            status = PartStatus(state.status.value)
        case _:
            assert_never(state)
    return status


def _is_ai_service_unavailable(state: AnalysisState | DraftState) -> bool:
    return (
        isinstance(state, UnavailablePart)
        and state.reason_code is AiReasonCode.AI_SERVICE_UNAVAILABLE
    )
